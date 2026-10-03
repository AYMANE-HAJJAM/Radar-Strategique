import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(path) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const compiledModule = { exports: {} };
  new Function("require", "exports", "module", code)(require, compiledModule.exports, compiledModule);
  return compiledModule.exports;
}
const { submitResultReview, afterConfirmedReview, reviewRefreshHref, scheduleReviewToastDismiss } = load("../lib/review-feedback.ts");
const { ResultActions } = load("../components/result-actions.tsx");
const { ReviewToast } = load("../components/review-toast.tsx");
const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props));
const row = { id: 47, title: "Offre", version: "abc123", url: "https://example.com", review_status: "PENDING", discovery_status: "NEW" };

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness(item = row, requestResult = deferred(), refreshResult = deferred()) {
  const model = {
    page: { items: [item], total: 1, page: 1, page_size: 20, pages: 1, pending_total: 7, run_total: 1 },
    busy: new Map(), notifications: [], requests: [], refreshes: 0,
  };
  const inFlight = new Set();
  function submit(decision) {
    return submitResultReview({
      item, decision, inFlight,
      request: (path, init) => { model.requests.push({ path, init }); return requestResult.promise; },
      pending: (id, action) => { if (action) model.busy.set(id, action); else model.busy.delete(id); },
      notify: (kind, message) => model.notifications.push({ kind, message }),
      confirmed: id => { model.page = afterConfirmedReview(model.page, id); },
      refresh: () => { model.refreshes++; return refreshResult.promise; },
    });
  }
  return { model, submit, requestResult, refreshResult, inFlight };
}

for (const decision of ["approve", "reject"]) {
  for (const discovery_status of ["NEW", "UPDATED"]) {
    test(`${decision} ${discovery_status}: immediate feedback, confirmation, row and counts`, async () => {
      const h = harness({ ...row, discovery_status });
      const originalPage = h.model.page;
      const operation = h.submit(decision);
      assert.equal(h.model.busy.get(row.id), decision);
      assert.equal(h.model.page, originalPage, "No removal before confirmation");
      assert.equal(h.model.notifications.length, 0);
      const markup = render(ResultActions, { item: row, radarId: "1", status: "pending", reviewing: decision, onReview: () => {} });
      assert.equal((markup.match(/disabled=""/g) || []).length, 2);
      assert.match(markup, /aria-busy="true"/);
      assert.match(markup, decision === "approve" ? /Validation\.\.\./ : /Rejet\.\.\./);
      h.requestResult.resolve({ review_status: decision === "approve" ? "APPROVED" : "REJECTED" });
      await Promise.resolve();
      assert.deepEqual(h.model.page.items, []);
      assert.equal(h.model.page.total, 0);
      assert.equal(h.model.page.pending_total, 6);
      assert.equal(h.model.page.run_total, 0);
      assert.equal(h.model.refreshes, 1);
      assert.deepEqual(h.model.notifications, [{ kind: "success", message: decision === "approve" ? "Offre validée avec succès" : "Offre rejetée" }]);
      assert.deepEqual(JSON.parse(h.model.requests[0].init.body), { version: row.version });
      h.refreshResult.resolve();
      await operation;
      assert.equal(h.model.busy.size, 0);
      assert.equal(h.inFlight.size, 0);
    });
  }

  test(`${decision} API error: keep row and counts, restore actions and allow retry`, async () => {
    const h = harness();
    const originalPage = h.model.page;
    const operation = h.submit(decision);
    h.requestResult.reject(new Error("API unavailable"));
    await operation;
    assert.equal(h.model.page, originalPage);
    assert.equal(h.model.refreshes, 0, "Failed review must not reload or remove the row");
    assert.equal(h.model.busy.size, 0);
    assert.equal(h.inFlight.size, 0);
    assert.deepEqual(h.model.notifications, [{ kind: "error", message: decision === "approve" ? "Impossible de valider l’offre" : "Impossible de rejeter l’offre" }]);
    const markup = render(ResultActions, { item: row, radarId: "1", status: "pending", onReview: () => {} });
    assert.doesNotMatch(markup, /disabled=""/);
    assert.match(markup, /Valider/);
    assert.match(markup, /Rejeter/);
    await h.submit(decision);
    assert.equal(h.model.requests.length, 2, "Failure releases the synchronous guard");
  });
}

test("double click and opposite action submit only once, including during refresh", async () => {
  const h = harness();
  const operation = h.submit("approve");
  await h.submit("approve");
  await h.submit("reject");
  assert.equal(h.model.requests.length, 1);
  h.requestResult.resolve();
  await Promise.resolve();
  await h.submit("approve");
  assert.equal(h.model.requests.length, 1);
  h.refreshResult.resolve();
  await operation;
});

test("refresh failure cannot undo a confirmed review or call it a failed validation", async () => {
  const h = harness();
  const operation = h.submit("approve");
  h.requestResult.resolve();
  await Promise.resolve();
  h.refreshResult.reject(new Error("GET unavailable"));
  await operation;
  assert.equal(h.model.page.items.length, 0);
  assert.equal(h.model.notifications[0].kind, "success");
  assert.doesNotMatch(h.model.notifications[1].message, /Impossible de valider/);
  assert.equal(h.inFlight.size, 0);
});

test("history pagination correction preserves current view, tab, run, filters and return state", () => {
  const search = new URLSearchParams("view=history&run_id=47&status=pending&page=3&q=architecture&sort=estimate&return=status%3Dapproved%26page%3D2");
  const result = { items: [], pages: 2 };
  const href = reviewRefreshHref(search, result);
  const actual = new URLSearchParams(href.slice(1));
  assert.equal(actual.get("page"), "2");
  for (const key of ["view", "run_id", "status", "q", "sort", "return"]) assert.equal(actual.get(key), search.get(key));
  assert.equal(search.get("page"), "3", "Do not mutate the active URL");
  assert.equal(reviewRefreshHref(search, { items: [row], pages: 3 }), null);
  assert.equal(reviewRefreshHref(new URLSearchParams("status=approved&q=architecture"), { items: [], pages: 1 }), null);
});

test("confirmed removal is idempotent and preserves unrelated rows and nullable counts", () => {
  const page = { items: [row, { ...row, id: 48 }], total: 2, page: 1, page_size: 20, pages: 1, run_total: null };
  const next = afterConfirmedReview(page, row.id);
  assert.deepEqual(next.items.map(item => item.id), [48]);
  assert.equal(next.total, 1);
  assert.equal(next.run_total, null);
  assert.equal(afterConfirmedReview(next, row.id), next);
  assert.equal(page.items.length, 2);
});

test("toast has persistent polite and assertive live regions and an accessible dismissal", () => {
  const empty = render(ReviewToast, { notification: null, dismiss: () => {} });
  assert.match(empty, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(empty, /role="alert" aria-live="assertive" aria-atomic="true"/);
  for (const kind of ["success", "error"]) {
    const markup = render(ReviewToast, { notification: { id: 1, kind, message: "Review feedback" }, dismiss: () => {} });
    assert.equal((markup.match(/Review feedback/g) || []).length, 1);
    assert.match(markup, /aria-label="Fermer la notification"/);
  }
});

test("review controls are shared by all radars and absent from reviewed tabs", () => {
  for (const radarId of ["1", "2", "3", "4", "5"]) {
    const markup = render(ResultActions, { item: row, radarId, status: "pending", reviewing: "reject", onReview: () => {} });
    assert.match(markup, /Rejet\.\.\./);
    assert.equal((markup.match(/disabled=""/g) || []).length, 2);
  }
  for (const status of ["approved", "rejected"]) assert.doesNotMatch(
    render(ResultActions, { item: row, radarId: "1", status, onReview: () => {} }), /<button/);
});

test("toast auto-dismisses after 3.5 seconds and replacement cancels the older timer", context => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let dismissed = 0;
  const cancel = scheduleReviewToastDismiss(() => { dismissed++; });
  context.mock.timers.tick(3499);
  assert.equal(dismissed, 0);
  cancel();
  scheduleReviewToastDismiss(() => { dismissed++; });
  context.mock.timers.tick(1);
  assert.equal(dismissed, 0, "Older notification timer is cancelled");
  context.mock.timers.tick(3499);
  assert.equal(dismissed, 1);
});

test("simultaneous reviews on different rows keep independent loading states", async () => {
  const inFlight = new Set();
  const busy = new Map();
  const first = deferred(), second = deferred();
  const requests = [];
  const props = {
    inFlight, pending: (id, action) => { if (action) busy.set(id, action); else busy.delete(id); },
    request: (path) => { requests.push(path); return path.includes("/47/") ? first.promise : second.promise; },
    notify: () => {}, confirmed: () => {}, refresh: async () => {},
  };
  const one = submitResultReview({ ...props, item: row, decision: "approve" });
  const two = submitResultReview({ ...props, item: { ...row, id: 48 }, decision: "reject" });
  assert.equal(busy.get(47), "approve");
  assert.equal(busy.get(48), "reject");
  first.resolve();
  await one;
  assert.equal(busy.has(47), false);
  assert.equal(busy.get(48), "reject");
  await submitResultReview({ ...props, item: { ...row, id: 48 }, decision: "approve" });
  assert.equal(requests.length, 2);
  second.resolve();
  await two;
  assert.equal(busy.size, 0);
});
