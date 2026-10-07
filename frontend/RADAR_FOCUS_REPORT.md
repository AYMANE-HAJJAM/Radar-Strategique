# Radar tab focus diagnosis and fix

## Root cause

The shared AppShell registered window focus and pageshow listeners that called auth.me(). Every check first set the known session to null. That switched the shell to the full-page “Connexion au serveur…” branch and removed its children, unmounting RadarPage. When the session response arrived, RadarPage mounted again, fetched results and the latest run, and recreated its polling timer. This reset local page state and looked like a reconnect.

The previous auth change introduced this behavior. There was no browser reload on focus, no focus-triggered router.refresh(), and no Radar visibilitychange handler. Radar's polling effect also depended on the entire running object, so each status response recreated its interval. The launch POST was exclusively in the user launch handler; mounting, focus, and polling did not invoke it.

## Backend continuity

Backend run ownership was already correct for tab inactivity. launch_radar reserves the SearchRun and submits AgentOrchestrator.execute(run_id) to LocalJobRunner's ThreadPoolExecutor. Execution does not depend on browser polling, component lifetime, or tab visibility. No Radar backend business logic was changed.

A new regression launches through the authenticated web API, allows the worker to finish with no browser polling, and confirms the original run ID is completed and exactly one SearchRun exists. The 17 backend job tests pass. This verifies local code and test execution; no production browser/network recording or production run logs were consulted.

## Final behavior

- Ordinary focus never resets or refetches auth. Initial/path checks, cross-tab auth notifications, explicit logout, and persisted browser page restoration retain session safeguards. Protected API 401 responses redirect to login without a redundant auth fetch.
- Radar remains mounted and rendered when hidden or restored. Hidden tabs pause status observation; backend execution continues.
- Visible/focus restoration silently GETs the existing run ID and refreshes results for the current view. Paired visibilitychange/focus events are coalesced. Requests are serialized, with a restore queued if a poll is already in flight.
- Active runs continue polling every three seconds using the same reserved ID. Status, stage and completion counts update in place. Completed runs stop issuing polling GETs.
- Completion refresh preserves the URL, filters, sort, pagination, history/backlog view and selected run. It no longer forces navigation to an unfiltered pending view.
- Existing results remain visible throughout refresh and background errors; errors appear inline and active-run polling retries. Initial unknown sessions still use the loading guard.
- The observer only issues GET requests. A double click plus repeated hide/show transitions produces exactly one launch POST in the regression test.

## Files changed in this follow-up

Runtime:
- components/app-shell.tsx — remove ordinary-focus auth resets; silently revalidate persisted pages; handle authenticated API expiry.
- lib/api.ts — notify the shell when a protected request returns 401.
- lib/radar-run-sync.ts — serialized visibility-aware observer, deduplicated restores and stable polling cadence.
- components/use-radar-run-sync.ts — keep current run/view callbacks without remounting the observer on each status response.
- app/radars/[radarId]/page.tsx — integrate silent refresh, retain current view and results, display status and connection errors in place.
- components/run-history.tsx — silently refresh existing history without replacing it with a loading state.

Tests:
- tests/auth.test.mjs — focus preserves the shell; persisted pages and expired sessions retain auth protections.
- tests/radar-focus.test.mjs — active/completed restores, same-ID polling, filter/history preservation, exactly one launch POST, no loading flash, in-flight restore and background failure recovery.
- ../backend/tests/integration/test_jobs_api.py — worker completion without browser polling.

Documentation:
- RADAR_FOCUS_REPORT.md — this report.

Earlier login/logout changes remain in the working tree and are not Radar business changes.

## Validation

- Frontend tests: 30 passed.
- TypeScript typecheck: passed.
- ESLint: passed.
- Optimized Next.js production build: passed (all pages generated).
- Backend job/API integration tests: 17 passed.
