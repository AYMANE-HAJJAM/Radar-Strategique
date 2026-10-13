# Radar 1 final incremental PMMP workflow

User workflow: **one action — “Lancer une recherche”** — runs a bounded checkpointed PMMP refresh, then business processing over Neon. Outcomes are recorded separately. A successful refresh pass is **not** full catalogue coverage.

**Live success is not claimed here.** Fixture and isolated-DB tests pass. A later real launch must prove new PMMP listings enter Neon and reach the existing business pipeline.

## Goal

Collect changes from PMMP → compare against Neon by stable identity/fingerprint → process only NEW, materially UPDATED, pending, or retryable work → show relevant opportunities.

Do **not** re-filter the entire historical catalogue on every “Lancer une recherche”.

## User workflow

1. Click **Lancer une recherche** (web) or the equivalent Telegram launch.
2. Backend reserves a SearchRun (blocks overlapping launches).
3. Async job: **bounded refresh** (`run_refresh`, front+deep budgets, DB lease) → then **business** (`indexed_title_batch` over pending/NEW/UPDATED/retry).
4. UI shows refresh outcome and business progress separately. If refresh fails or the lease is held, the business phase may still run on the existing index, but the UI must not present that run as fully updated.

There is **no** separate “Actualiser PMMP” button. Operator CLI/API refresh remains available but is not required for the user path.

## Actual implementation changes

| Area | Change |
|---|---|
| Model/migration | `pmmp_refresh_checkpoint` singleton (`f8a3c1d92e07`) with lease, heartbeat, soft PAGESTATE, cursor, pass/cycle counters |
| Collector | Honors `incremental` / `full` / `reconciliation`; soft PAGESTATE resume; renavigation when token invalid; per-page callback |
| Durable classify | NEW → `PENDING_PROCESSING`; UNCHANGED → `last_seen_at` only; UPDATED never steals an active `PROCESSING` owner (CAS requeue when idle) |
| `sync_listings` | Passes requested mode (no longer forces `full`); **not** called from the user launch path |
| Refresh orchestrator | [`pmmp_refresh.py`](../app/modules/radar1_markets/pmmp_refresh.py): front + deep budgets under DB lease |
| Launch path | `MarketsCollector._launch_bounded_refresh` before business; metrics `pmmp_refresh_pass` + `pmmp_sync_mode=bounded_refresh` |
| Stale recovery | Radar 1 active runs older than a budget-derived stale window are failed + processing claims released so Render Free spin-down can recover |
| CLI / API | `flask radar1-pmmp-refresh` and `POST /radars/1/pmmp-refresh` remain operator tools |
| UI | Single launch button; per-run refresh alert vs business progress; Index PMMP strip (pass vs cycle) |

Business policy, title filter, official detail, dedup, reviews, and existing index rows are preserved (no bulk reset).

## How refresh is triggered

1. **User (primary):** “Lancer une recherche” → bounded refresh inside the SearchRun job, then business.
2. **CLI (operator):** `flask radar1-pmmp-refresh`
3. **Authenticated API:** `POST /api/radars/1/pmmp-refresh` queues `run_refresh_job` (no SearchRun).

### Render Free / hosting limitations (honest)

- The web worker’s in-process job thread is **not** guaranteed to survive spin-down or restart.
- Progress that survives death: refresh **checkpoint** (cursor, PAGESTATE, lease expiry) and Neon index/ledger rows.
- A killed SearchRun stays active until the Radar 1 **stale window** (derived from refresh + processing + lease budgets, capped by `SEARCH_RUN_STALE_MINUTES`, minimum 10 minutes). Only then can a new launch recover it.
- One click does **one bounded pass**, not a full PMMP catalogue sync. Deep cycle completion requires many passes over time.
- No always-on scheduler exists on Free; optional external cron can still call the refresh API between user clicks, but the user path no longer depends on it.

## Page/time budgets and checkpoint strategy

Defaults (env-overridable):

| Setting | Default |
|---|---|
| `RADAR1_PMMP_REFRESH_FRONT_PAGES` | 5 |
| `RADAR1_PMMP_REFRESH_DEEP_PAGES` | 15 |
| `RADAR1_PMMP_REFRESH_MAX_SECONDS` | 90 |
| `RADAR1_PMMP_REFRESH_LEASE_SECONDS` | 180 |

**Front pass:** always a fresh PMMP session from page 1 (typical NEW listings). Incremental overlap may stop early; it never marks the deep cycle complete.

**Deep segment:** resumes from durable `cursor_page`. Soft `page_state` is tried first; on invalid/expired HTML, discard token and **re-navigate from page 1 up to the cursor**, then continue — never skip ahead of the cursor.

**Success semantics:**

- **Pass success** (`last_pass_success_at` / `pmmp_refresh_pass.pass_success`): this invocation’s page/time budget finished cleanly. **Not** full-catalogue reconciliation.
- **Cycle complete** (`last_cycle_completed_at` / `cycle_complete`): deep cursor wrapped `declared_pages` / final page.

## Safety

### Lease / heartbeat (no age-only reclaim)

- Single-flight via `lease_owner` + `lease_until` + per-page `heartbeat_at`.
- Acquire only when `idle`/`failed`, or when lease expired **and** heartbeat stale.
- Never reclaim solely because `last_started_at` is old.
- `--force-release-expired-lease` uses the same expired predicate; never kills a live lease.
- Second refresh while lease held → CLI error / HTTP 409 / launch records `lease_held` and continues business with clear failure flag.

### Concurrent UPDATED vs business processing

- Active `PROCESSING` + live SearchRun: content/fingerprint update only; owner kept; reason `listing_changed_while_processing`.
- Idle / non-owned: CAS requeue to `PENDING_PROCESSING`.
- Reviews/Results are not rewritten by refresh.

### Overlapping launches

- Active SearchRun → HTTP 409 `RUN_ALREADY_ACTIVE`.
- Stale SearchRun after budget window → auto-fail + `release_run` so a new launch can proceed.

## Cost safeguards

- No paid search, AI, or browser automation for listing collection.
- Hard page + time budgets; delay ≥ 0.35s between HTTP calls.
- Single refresh lease; duplicate identities handled by durable classify.
- Business runs remain bounded by existing `RADAR1_PROCESSING_BATCH_SIZE` / `MAX_SECONDS`.

## Migration

```text
alembic_version → f8a3c1d92e07
```

From `backend`:

```bash
python -m flask --app wsgi db upgrade
```

Idempotent singleton row `id=1` is inserted by the migration. No data migration of `pmmp_listing_index`.

## Deployment steps

1. Deploy backend revision with migration `f8a3c1d92e07`.
2. Confirm `RADAR1_DISCOVERY_MODE=pmmp_index`.
3. Optionally restore production batch defaults (`25` / `120`) after refresh is healthy.
4. Deploy matching frontend (single button + separate refresh/business notices).
5. Optional: external cron for extra refresh passes between user clicks.
6. Expect “Lancer une recherche” to perform a **bounded** refresh then business — not a full board sync.

## First manual verification (operator)

1. Confirm no active Radar 1 SearchRun and no valid refresh lease (`pmmp_refresh.lease_held=false`).
2. Click **Lancer une recherche** once (or run one orchestrated fixture launch).
3. Expect: `pmmp_refresh_pass` on the run; index `last_seen_at` / NEW rows move when PMMP has changes; `pass_success` ≠ catalogue reconciled unless deep cycle wrapped.
4. Confirm existing PROCESSED/REJECTED unchanged fingerprints stay terminal; prior PENDING remain eligible; reviews preserved.
5. Confirm UI shows refresh failure clearly if the pass fails (never “fully updated” on old index alone).
6. Only after a real PMMP-backed launch, treat live refresh as proven.

## Tests executed (offline)

- `tests/modules/radar1/test_pmmp_refresh.py` — lease, reclaim, NEW/UPDATED/PENDING, deep resume, PAGESTATE renav, **launch → refresh → business**, partial failure, lease-held, duplicate launch, restart lease reclaim, budgets
- `tests/modules/radar1/test_indexed_title_flow.py` — Radar 1 stale recovery after budget window
- Related reliability/phase3 suites updated for `bounded_refresh` metrics

No real PMMP crawl, production write, deploy, or live cron was performed by this implementation.
