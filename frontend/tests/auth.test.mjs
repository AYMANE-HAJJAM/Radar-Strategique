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
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
  const compiledModule = { exports: {} };
  new Function("require", "exports", "module", code)(name => mocks[name] ?? require(name), compiledModule.exports, compiledModule);
  return compiledModule.exports;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
const user = { id: 1, name: "Admin", role: "ADMIN" };
const { ApiError } = load("../lib/api.ts");

// Exercise the real component's hooks, requests, rendered output and navigation
// without requiring a running API or adding a browser/test framework dependency.
function shell(context, initialPath = "/login") {
  const previousWindow = globalThis.window;
  const listeners = new Map();
  globalThis.window = {
    addEventListener: (name, fn) => { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); },
    removeEventListener: (name, fn) => listeners.get(name)?.delete(fn),
  };
  let path = initialPath, cursor = 0;
  const slots = [], pending = [], requests = [], redirects = [];
  const logoutRequest = deferred();
  const router = { replace: value => redirects.push(value), refresh: () => {} };
  const hooks = {
    ...React,
    useState(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: initial };
      return [slots[index].value, value => { slots[index].value = value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!slots[index]) slots[index] = { value: { current: initial } };
      return slots[index].value;
    },
    useEffect(fn, deps) {
      const index = cursor++;
      const old = slots[index];
      if (!old || deps.some((dep, i) => dep !== old.deps[i])) {
        old?.cleanup?.();
        slots[index] = { deps };
        pending.push(() => { slots[index].cleanup = fn(); });
      }
    },
  };
  const { AppShell } = load("../components/app-shell.tsx", {
    react: hooks,
    "next/navigation": { usePathname: () => path, useRouter: () => router },
    "@/lib/api": { ApiError, AUTH_CHANGE_KEY: "radar-auth-change", AUTH_EXPIRED_EVENT: "radar-auth-expired", auth: {
      me: () => { const request = deferred(); requests.push(request); return request.promise; },
      logout: () => logoutRequest.promise,
    } },
    "@/components/state": { State: ({ children }) => React.createElement("main", null, children) },
    "@/components/sidebar": { Sidebar: () => React.createElement("aside", null, "Sidebar") },
    "@/components/main-content": { MainContent: ({ children }) => children },
  });
  function render() { cursor = 0; return AppShell({ children: React.createElement("form", null, path === "/login" ? "Login form" : "Dashboard") }); }
  function effects() { while (pending.length) pending.shift()(); }
  function markup() { return renderToStaticMarkup(render()); }
  context.after(() => { for (const slot of slots) slot?.cleanup?.(); globalThis.window = previousWindow; });
  render(); effects();
  return { requests, redirects, logoutRequest, render, effects, markup,
    navigate(value) { path = value; const html = markup(); effects(); return html; },
    event(name, event = {}) { for (const fn of listeners.get(name) ?? []) fn(event); },
  };
}

test("authenticated /login never renders the form and replaces history with dashboard", async context => {
  const h = shell(context);
  assert.doesNotMatch(h.markup(), /Login form/);
  h.requests[0].resolve({ user }); await flush();
  assert.doesNotMatch(h.markup(), /Login form/);
  assert.deepEqual(h.redirects, ["/"]);
  h.navigate("/");
  h.requests[1].resolve({ user }); await flush();
  assert.match(h.markup(), /Dashboard/);
  assert.deepEqual(h.redirects, ["/"], "No redirect loop on dashboard");
});

test("anonymous /login displays form only after authoritative 401", async context => {
  const h = shell(context);
  assert.doesNotMatch(h.markup(), /Login form/);
  h.requests[0].reject(new ApiError("UNAUTHENTICATED", "Login required", 401)); await flush();
  assert.match(h.markup(), /Login form/);
  assert.deepEqual(h.redirects, []);
});

test("API failure does not pretend to be anonymous or redirect in a loop", async context => {
  const h = shell(context);
  h.requests[0].reject(new Error("API unavailable")); await flush();
  assert.match(h.markup(), /API unavailable/);
  assert.doesNotMatch(h.markup(), /Login form/);
  assert.deepEqual(h.redirects, []);
});

test("new tab with valid cookie opens app; new tab after logout requires login", async context => {
  const h = shell(context, "/");
  h.requests[0].resolve({ user }); await flush();
  assert.match(h.markup(), /Dashboard/);
  h.event("storage", { key: "radar-auth-change" });
  assert.doesNotMatch(h.markup(), /Dashboard/);
  h.requests[1].reject(new ApiError("UNAUTHENTICATED", "Login required", 401)); await flush();
  assert.deepEqual(h.redirects, ["/login"]);
  assert.doesNotMatch(h.markup(), /Dashboard/);
});

test("back/forward navigation and restored pages revalidate session", async context => {
  const h = shell(context, "/");
  h.requests[0].resolve({ user }); await flush();
  assert.doesNotMatch(h.navigate("/login"), /Login form/);
  h.requests[1].resolve({ user }); await flush();
  assert.deepEqual(h.redirects, ["/"]);
  h.navigate("/"); h.requests[2].resolve({ user }); await flush();
  const count = h.requests.length;
  h.event("focus"); h.event("pageshow", { persisted: false });
  assert.equal(h.requests.length, count, "Ordinary focus does not reload auth");
  assert.match(h.markup(), /Dashboard/);
  h.event("pageshow", { persisted: true });
  assert.match(h.markup(), /Dashboard/, "BFCache recheck preserves known page");
  h.requests.at(-1).reject(new ApiError("UNAUTHENTICATED", "Login required", 401)); await flush();
  assert.equal(h.redirects.at(-1), "/login");
});

test("out-of-order session checks cannot restore stale authentication", async context => {
  const h = shell(context, "/");
  h.event("storage", { key: "radar-auth-change" });
  h.requests[1].reject(new ApiError("UNAUTHENTICATED", "Login required", 401)); await flush();
  h.requests[0].resolve({ user }); await flush();
  assert.doesNotMatch(h.markup(), /Dashboard/);
  assert.deepEqual(h.redirects, ["/login"]);
});

test("logout waits for backend completion, hides app and ignores stale checks", async context => {
  const h = shell(context, "/");
  h.requests[0].resolve({ user }); await flush();
  const tree = h.render();
  h.event("storage", { key: "radar-auth-change" });
  const operation = tree.props.children[1].props.onLogout();
  assert.doesNotMatch(h.markup(), /Dashboard/);
  assert.deepEqual(h.redirects, []);
  h.event("focus");
  assert.equal(h.requests.length, 2, "No session checks during logout");
  h.logoutRequest.resolve(); await operation;
  h.requests[1].resolve({ user }); await flush();
  assert.deepEqual(h.redirects, ["/login"]);
  assert.doesNotMatch(h.markup(), /Dashboard/);
});

test("API client uses cookies and no-store, not tab-local credentials; logout clears CSRF", async context => {
  const oldFetch = globalThis.fetch, oldWindow = globalThis.window;
  context.after(() => { globalThis.fetch = oldFetch; globalThis.window = oldWindow; });
  const requests = [], notifications = [];
  globalThis.window = { localStorage: { setItem: (key, value) => notifications.push({ key, value }) } };
  globalThis.fetch = async (url, init) => {
    requests.push({ url, init });
    return new Response(url.endsWith("logout") ? null : JSON.stringify({ user, csrf_token: "csrf-test" }), { status: url.endsWith("logout") ? 204 : 200 });
  };
  const { auth } = load("../lib/api.ts");
  await auth.me();
  assert.equal(requests[0].init.credentials, "include");
  assert.equal(requests[0].init.cache, "no-store");
  await auth.logout();
  assert.equal(requests[1].init.method, "POST");
  assert.equal(requests[1].init.headers.get("X-CSRF-Token"), "csrf-test");
  await auth.me();
  assert.equal(requests[2].init.headers.has("X-CSRF-Token"), false);
  assert.equal(notifications[0].key, "radar-auth-change");
  await auth.access("ABCD-EFGH-JK");
  assert.deepEqual(JSON.parse(requests[3].init.body), { access_code: "ABCD-EFGH-JK" });
  assert.equal(notifications.length, 2);
});


test("focus preserves shell and child identity without an auth request or loading flash", async context => {
  const h = shell(context, "/radars/1");
  h.requests[0].resolve({ user }); await flush();
  const before = h.markup();
  for (let i = 0; i < 3; i++) h.event("focus");
  assert.equal(h.markup(), before);
  assert.equal(h.requests.length, 1);
  assert.doesNotMatch(h.markup(), /Connexion au serveur/);
  assert.equal(h.render().props.className, "app-shell", "Shell remains mounted");
});

test("protected API 401 redirects without an unnecessary auth refetch", async context => {
  const h = shell(context, "/radars/1");
  h.requests[0].resolve({ user }); await flush();
  h.event("radar-auth-expired");
  assert.deepEqual(h.redirects, ["/login"]);
  assert.equal(h.requests.length, 1);
  assert.doesNotMatch(h.markup(), /Dashboard/);
});
