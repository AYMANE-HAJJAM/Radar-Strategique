# Radar 1 final incremental PMMP workflow

Implementation of independent, leased, bounded PMMP index refresh separated from Radar 1 business processing.

**Live success is not claimed here.** Fixture and isolated-DB tests pass. A later real refresh must prove new PMMP listings enter Neon and reach the existing business pipeline.

## Goal

Collect changes from PMMP → compare against Neon by stable identity/fingerprint → process only NEW, materially UPDATED, pending, or retryable work → show relevant opportunities.

Do **not** re-filter the entire historical catalogue on every “Lancer une recherche”.

## Actual implementation changes

| Area | Change |
|---|---|
| Model/migration | `pmmp_refresh_checkpoint` singleton (`f8a3c1d92e07`) with lease, heartbeat, soft PAGESTATE, cursor, pass/cycle counters |
| Collector | Honors `incremental` / `full` / `reconciliation`; soft PAGESTATE resume; renavigation when token invalid; per-page callback |
| Durable classify | NEW → `PENDING_PROCESSING`; UNCHANGED → `last_seen_at` only; UPDATED never steals an active `PROCESSING` owner (CAS requeue when idle) |
| `sync_listings` | Passes requested mode (no longer forces `full`) |
| Refresh orchestrator | [`pmmp_refresh.py`](../app/modules/radar1_markets/pmmp_refresh.py): front + deep budgets under DB lease |
| CLI | `flask radar1-pmmp-refresh` (+ `--force-release-expired-lease`) |
| API | `POST /radars/1/pmmp-refresh` (202 / 409); `pmmp_refresh` embedded in Radar 1 list payload |
| Business run | Still `indexed_title_batch` / `pmmp_sync_mode=not_requested`; snapshots refresh status into metrics |
| UI | Separate Index PMMP strip (pass vs cycle) vs per-run progress |

Business policy, title filter, official detail, dedup, reviews, and existing index rows are preserved (no bulk reset).

## How refresh is triggered

1. **CLI (operator / CI):** `flask radar1-pmmp-refresh`
2. **Authenticated API:** `POST /api/radars/1/pmmp-refresh` queues `run_refresh_job` on the existing `radar_job_runner` (does **not** create a SearchRun).
3. **Business button:** process-only. Never starts a crawl.

### Render Free limitation

No always-on in-process scheduler survives spin-down. Simplest viable automation:

- External cron (cron-job.org, GitHub Actions, etc.) calling the authenticated refresh endpoint, **or**
- `render run` / one-off shell: `flask radar1-pmmp-refresh`

Checkpoint lease + cursor survive process death. Do not rely on a background thread alone.

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

- **Pass success** (`last_pass_success_at`): this invocation’s page/time budget finished cleanly. **Not** full-catalogue reconciliation.
- **Cycle complete** (`last_cycle_completed_at` / `cycle_complete`): deep cursor wrapped `declared_pages` / final page.

## Safety

### Lease / heartbeat (no age-only reclaim)

- Single-flight via `lease_owner` + `lease_until` + per-page `heartbeat_at`.
- Acquire only when `idle`/`failed`, or when lease expired **and** heartbeat stale.
- Never reclaim solely because `last_started_at` is old.
- `--force-release-expired-lease` uses the same expired predicate; never kills a live lease.
- Second start while lease held → CLI error / HTTP 409.

### Concurrent UPDATED vs business processing

- Active `PROCESSING` + live SearchRun: content/fingerprint update only; owner kept; reason `listing_changed_while_processing`.
- Idle / non-owned: CAS requeue to `PENDING_PROCESSING`.
- Reviews/Results are not rewritten by refresh.

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
4. Deploy matching frontend (Radar 1 refresh status strip).
5. Schedule external cron for `POST /radars/1/pmmp-refresh` or CLI refresh.
6. Do **not** expect “Lancer une recherche” to refresh the board.

## First manual verification (operator)

1. Confirm no active Radar 1 SearchRun and no valid refresh lease (`pmmp_refresh.lease_held=false`).
2. Run one bounded refresh: `flask radar1-pmmp-refresh` (or API 202).
3. Expect: index `last_seen_at` / NEW rows move; `last_pass_success_at` set; `cycle_complete` only if cursor wrapped.
4. Confirm existing PROCESSED/REJECTED unchanged fingerprints stay terminal; prior PENDING remain eligible.
5. Launch **one** business search; expect `pmmp_sync_mode=not_requested`, pages 0, processing only pending/NEW/UPDATED/retry work.
6. Confirm no duplicate Results for the same consultation; reviews preserved.
7. Only after that, treat live refresh as proven.

## Tests executed (offline)

- `tests/modules/radar1/test_pmmp_refresh.py` — lease, reclaim, NEW/UPDATED/PENDING, deep resume, PAGESTATE renav, business no-crawl, budgets
- `tests/modules/radar1/test_pmmp_listing_index.py` — incremental overlap honored
- Related reliability/indexed suites updated for concurrent UPDATED + incremental stop semantics

No real PMMP crawl, production write, deploy, or live cron was performed by this implementation.
