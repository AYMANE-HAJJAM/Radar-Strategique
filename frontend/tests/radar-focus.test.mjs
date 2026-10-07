import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
function load(path, mocks = {}) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const compiledModule = { exports: {} };
  new Function("require", "exports", "module", code)(name => mocks[name] ?? require(name), compiledModule.exports, compiledModule);
  return compiledModule.exports;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function surface(extra = {}) {
  const listeners = new Map();
  return { ...extra,
    addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
    removeEventListener(name, fn) { listeners.get(name)?.delete(fn); },
    emit(name, event = {}) { for (const fn of listeners.get(name) ?? []) fn(event); },
  };
}
const activeRun = { id: 42, status: "running", current_stage: "SEARCHING", started_at: "2026-10-07T10:00:00Z", finished_at: null, new_results_count: 0, updated_results_count: 0 };
const row = { id: 1, title: "Architecture existante", institution: "Ministère", reference: "AO-1", version: "v1", review_status: "PENDING", discovery_status: "NEW" };

// Run the actual Radar page and synchronization hook with controlled browser
// events and API responses. Hook slots retain state across every rerender.
function radar(context, params = "status=pending&q=Architecture&sort=estimate&page=1", initialRun = activeRun) {
  context.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const oldWindow = globalThis.window, oldDocument = globalThis.document;
  const window = surface(), document = surface({ visibilityState: "visible" });
  globalThis.window = window; globalThis.document = document;
  let cursor = 0;
  const slots = [], pending = [], requests = [], redirects = [];
  const model = { run: initialRun ? { ...initialRun } : null, items: [row], runRequest: null, launchRequest: null, runError: null };
  const search = new URLSearchParams(params);
  const router = { replace: href => redirects.push(href) };
  const hooks = { ...React,
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: typeof initial === "function" ? initial() : initial };
      return [slots[index].value, value => { slots[index].value = typeof value === "function" ? value(slots[index].value) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: { current: initial } };
      return slots[index].value;
    },
    useMemo(fn, deps) {
      const index = cursor++;
      if (!slots[index] || deps.some((dep, i) => dep !== slots[index].deps[i])) slots[index] = { deps, value: fn() };
      return slots[index].value;
    },
    useCallback(fn, deps) { return hooks.useMemo(() => fn, deps); },
    useEffect(fn, deps) {
      const index = cursor++;
      const old = slots[index];
      if (!old || deps.some((dep, i) => dep !== old.deps[i])) {
        old?.cleanup?.(); slots[index] = { deps };
        pending.push(() => { slots[index].cleanup = fn(); });
      }
    },
  };
  class ApiError extends Error {}
  const api = (path, init = {}) => {
    requests.push({ path, method: init.method ?? "GET", cache: init.cache });
    if (init.method === "POST") return model.launchRequest.promise;
    if (path.startsWith("/runs/")) {
      if (model.runError) return Promise.reject(model.runError);
      return model.runRequest?.promise ?? Promise.resolve({ ...model.run });
    }
    if (path.includes("/results?")) return Promise.resolve({ items: model.items, total: model.items.length, pages: 1, page: 1, page_size: 20 });
    if (path.includes("/runs?")) return Promise.resolve({ items: model.run ? [{ ...model.run }] : [] });
    throw new Error("Unexpected request: " + path);
  };
  const apiModule = { api, ApiError };
  const sync = load("../lib/radar-run-sync.ts");
  const syncHook = load("../components/use-radar-run-sync.ts", { react: hooks, "@/lib/api": apiModule, "@/lib/radar-run-sync": sync });
  const stub = name => function Stub(props) { return React.createElement("div", { "data-component": name }, props.children); };
  const page = load("../app/radars/[radarId]/page.tsx", {
    react: hooks,
    "next/navigation": { useParams: () => ({ radarId: "1" }), useRouter: () => router, useSearchParams: () => search },
    "next/link": { default: ({ children, ...props }) => React.createElement("a", props, children), __esModule: true },
    "@/lib/api": apiModule,
    "@/components/use-radar-run-sync": syncHook,
    "@/components/run-status-banner": load("../components/run-status-banner.tsx"),
    "@/components/use-review-feedback": { useReviewFeedback: () => ({ review: () => {}, reviewing: {}, notification: null, dismiss: () => {} }) },
    "@/lib/review-feedback": load("../lib/review-feedback.ts"),
    "@/lib/radar-navigation": load("../lib/radar-navigation.ts"),
    "@/lib/format": load("../lib/format.ts"),
    "@/lib/radars": load("../lib/radars.ts"),
    "@/components/result-actions": { ResultActions: stub("ResultActions") },
    "@/components/review-toast": { ReviewToast: stub("ReviewToast") },
    "@/components/result-review-context": { PreviousReview: stub("PreviousReview"), ReviewChanges: stub("ReviewChanges") },
    "@/components/run-history": { RunHistory: stub("RunHistory") },
    "@/components/run-scope": { DiscoveryBadge: stub("DiscoveryBadge"), RunContext: stub("RunContext"), RunEmpty: stub("RunEmpty"), RunScopeSwitch: stub("RunScopeSwitch") },
    "@/components/status-badge": { StatusBadge: stub("StatusBadge") },
    "@/components/table-state": { EmptyResults: stub("EmptyResults"), ResultsError: stub("ResultsError"), TableSkeleton: stub("TableSkeleton") },
    "@/components/top-context-bar": { TopContextBar: ({ actions }) => React.createElement("header", null, actions) },
  }).default;
  function render() { cursor = 0; return page(); }
  function effects() { while (pending.length) pending.shift()(); }
  function markup() { return renderToStaticMarkup(render()); }
  async function settle() { for (let i = 0; i < 6; i++) { await Promise.resolve(); render(); effects(); } }
  context.after(() => { for (const slot of slots) slot?.cleanup?.(); globalThis.window = oldWindow; globalThis.document = oldDocument; });
  render(); effects();
  return { model, requests, redirects, search, render, markup, settle,
    hide() { document.visibilityState = "hidden"; document.emit("visibilitychange"); },
    show() { document.visibilityState = "visible"; document.emit("visibilitychange"); window.emit("focus"); },
    focus() { window.emit("focus"); },
    tick(ms) { context.mock.timers.tick(ms); },
    launch() { return render().props.children[0].props.actions.props.onClick(); },
  };
}

test("hidden then visible during active run preserves page, filters, run id and polling", async context => {
  const h = radar(context); await h.settle();
  assert.match(h.markup(), /Architecture existante/);
  const search = h.search.toString(), requestCount = h.requests.length;
  h.hide(); h.tick(10000); await h.settle();
  assert.equal(h.requests.length, requestCount, "Hidden tab pauses observation only");
  assert.match(h.markup(), /Architecture existante/);
  const next = deferred(); h.model.runRequest = next;
  h.show();
  assert.match(h.markup(), /Architecture existante/);
  assert.doesNotMatch(h.markup(), /TableSkeleton|Connexion au serveur/);
  assert.equal(h.requests.filter(r => r.path === "/runs/42").length, 1, "Paired focus and visibility events share one refresh");
  next.resolve({ ...activeRun, current_stage: "VALIDATING" }); h.model.runRequest = null;
  await h.settle();
  assert.match(h.markup(), /VALIDATING/);
  h.tick(3000); await h.settle();
  assert.equal(h.requests.filter(r => r.path === "/runs/42").length, 2);
  assert.equal(h.search.toString(), search);
  assert.deepEqual(h.redirects, []);
  assert.equal(h.requests.filter(r => r.method === "POST").length, 0);
});

test("completed while hidden updates status and results in place immediately", async context => {
  const h = radar(context); await h.settle();
  h.hide();
  h.model.run = { ...activeRun, status: "completed", current_stage: "COMPLETED", new_results_count: 2 };
  h.model.items = [row, { ...row, id: 2, title: "Architecture nouvelle" }];
  const search = h.search.toString();
  h.show();
  assert.match(h.markup(), /Architecture existante/);
  assert.doesNotMatch(h.markup(), /TableSkeleton|Connexion au serveur/);
  await h.settle();
  assert.match(h.markup(), /Terminée/);
  assert.match(h.markup(), /Architecture nouvelle/);
  const count = h.requests.length;
  h.tick(9000); await h.settle();
  assert.equal(h.requests.length, count, "Completed run is no longer polled");
  assert.equal(h.search.toString(), search);
  assert.deepEqual(h.redirects, []);
});

test("one user launch produces exactly one POST across repeated hide/show and double click", async context => {
  const h = radar(context, undefined, null); await h.settle();
  const launchRequest = deferred(); h.model.launchRequest = launchRequest;
  const launch = h.launch(); await h.launch();
  h.hide(); h.show(); await h.settle();
  h.model.run = { ...activeRun };
  launchRequest.resolve({ run_id: 42, status: "running" }); await launch; await h.settle();
  for (let i = 0; i < 3; i++) { h.hide(); h.tick(300); h.show(); await h.settle(); }
  h.tick(3000); await h.settle();
  assert.equal(h.requests.filter(r => r.method === "POST").length, 1);
  assert.equal(h.requests.find(r => r.method === "POST").path, "/radars/1/runs");
  assert.ok(h.requests.filter(r => r.path.startsWith("/runs/")).every(r => r.path === "/runs/42"));
});

test("background refresh failure preserves results and retries the same active run", async context => {
  const h = radar(context); await h.settle();
  h.hide(); h.model.runError = new Error("Backend unreachable"); h.show(); await h.settle();
  assert.match(h.markup(), /Backend unreachable/);
  assert.match(h.markup(), /Architecture existante/);
  assert.doesNotMatch(h.markup(), /TableSkeleton|Connexion au serveur/);
  h.model.runError = null; h.tick(3000); await h.settle();
  assert.doesNotMatch(h.markup(), /Backend unreachable/);
  assert.equal(h.requests.filter(r => r.method === "POST").length, 0);
});

test("completion refresh preserves history view and existing run selection", async context => {
  const h = radar(context, "view=history&status=pending&run_id=41&q=Architecture&sort=publication&page=2&return=status%3Dapproved");
  await h.settle(); const search = h.search.toString();
  h.hide(); h.model.run = { ...activeRun, status: "completed" }; h.show(); await h.settle();
  assert.equal(h.search.toString(), search);
  assert.deepEqual(h.redirects, []);
  const refreshed = h.requests.filter(r => r.path.includes("/results?"));
  assert.ok(refreshed.length >= 2);
  assert.ok(refreshed.every(r => r.path.includes("run_id=41") && r.path.includes("page=2")));
});

test("focus during an in-flight poll queues a fresh GET without concurrent polling", async context => {
  const h = radar(context); await h.settle();
  const pending = deferred(); h.model.runRequest = pending;
  h.tick(3000); h.hide(); h.tick(300); h.show();
  assert.equal(h.requests.filter(r => r.path === "/runs/42").length, 1);
  h.model.runRequest = null; h.model.run = { ...activeRun, status: "completed" };
  pending.resolve({ ...activeRun }); await h.settle();
  assert.equal(h.requests.filter(r => r.path === "/runs/42").length, 2);
  assert.match(h.markup(), /Terminée/);
});
