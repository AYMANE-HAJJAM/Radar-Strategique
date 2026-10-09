# Radar 1 SearchRun #59 — stuck diagnostic

Diagnostic date: 2026-10-09. Evidence timestamps below are UTC.
Local source revision: `8bb61b6`; comparison baseline: its parent `02f2cf2`.

Implementation follow-up, observed **2026-10-09 21:34:47.193028 UTC**: a new direct, verified READ ONLY transaction (8-second statement / 2-second lock / 5-second connection limits, then ROLLBACK) still found #59 `running / COLLECTING`, `pmmp_index`, 339 pages, completion false, and no finished timestamp. The index remained 5,209 rows with latest listing observation `17:32:49.377028 UTC`; #59 claims, all attempted rows and other visible database sessions were all zero. No measurable committed progress since the earlier snapshots. Render process ownership is still unavailable and worker death remains unconfirmed. No run, claim or result was modified. The focused implementation removes normal-launch reconciliation and age-only Radar 1 recovery; the original source-path analysis below describes the deployed baseline, not the new working-tree implementation.

## Decision

**The runtime regression is confirmed: the reliability implementation replaced the short incremental walk with a full-board walk on every normal index-mode run. #59 actually selected reconciliation and committed 339 pages. The current absence of progress is confirmed in the configured Neon database; the reason execution stopped is not yet confirmed. Worker loss is the leading explanation, not an established production fact.**

Do not launch a replacement run or perform recovery yet. First obtain Render logs and verify whether the original executing process still owns #59. Waiting is justified only if new measurable progress or a live, bounded operation is demonstrated.

## Safety and evidence provenance

- No Radar search, PMMP request, paid API call, application startup, migration, reconciliation, recovery, worker restart, cancellation, or production record modification was performed by this diagnostic.
- Database access used the existing `DATABASE_URL` configuration, directly through psycopg, without importing or starting the Flask application. Each diagnostic query ran inside `BEGIN READ ONLY`, with transaction-local statement timeout 8 seconds and lock timeout 2 seconds, followed by `ROLLBACK`. Connection timeout was 5 seconds. `transaction_read_only=on` was verified.
- The first network attempt was sandbox-blocked. Approved read-only network access then encountered a Neon pooler startup-option incompatibility; the successful retry set timeouts inside the transaction instead. Neither failed attempt ran a Radar operation.
- The configured database is Neon `neondb`, with migration `e7c91b2486af`. It contains matching Radar 1 / #59 evidence. **Its identity as the exact database used by the Render service remains unverified independently:** Render configuration and the authenticated production API were unavailable. Database facts in this document apply to the configured Neon database, rather than being inferred from local source.
- Tool discovery found no Render/Neon operational connector. Browser inventory returned no accessible browsers or tabs. Available local log files are historical audits, not current Render logs. No authenticated Render logs, process inventory, service plan, deployment events, or effective Gunicorn settings were obtained.

## CONFIRMED ROOT CAUSE

### Confirmed cause of the longer collection workload

`app/modules/radar1_markets/pmmp_listing_index.py:154` now always invokes `PmmpListingCollector.collect(mode='full')` at line 177. Previously it passed the requested incremental mode, except for an explicitly requested reconciliation. Consequently the unchanged-page overlap stop is bypassed for **both** incremental and reconciliation durable syncs. Increasing/decreasing `RADAR1_PMMP_OVERLAP_PAGES` will not restore the former production early stop.

`app/modules/radar1_markets/collector.py:691` also now performs legacy recovery before the walk, selects reconciliation if no successful complete reconciliation is recorded or the default 24-hour interval has elapsed, and processes a durable queue afterward. Migration `e7c91b2486af` leaves existing processing states NULL, intentionally causing first-run evidence recovery.

These changes explain why a previously short search can take tens of minutes or approximately an hour. They do **not** independently explain why this particular run has had no further committed progress for more than three hours. There is no confirmed root cause of that interruption yet, and no code change is proposed as if there were one.

### Confirmed runtime evidence

First database observation: `2026-10-09 20:48:58.459097+00:00`.
Second run observation: `2026-10-09 20:50:07.453899+00:00`, approximately 69 seconds later.

| Evidence | Observed value |
| --- | --- |
| SearchRun / radar | `59` / `1` |
| Stored status / stage | `running` / `COLLECTING` in both snapshots |
| Started | `2026-10-09 16:51:39.570765+00:00` |
| Entered COLLECTING | `2026-10-09 16:51:40.099813+00:00` |
| Run age at second observation | Approximately 3 h 58 min 28 s; already longer than the initial one-hour report |
| Finished / error kind | NULL / NULL |
| Actual recorded discovery mode | `pmmp_index` |
| Mode source diagnostic | `environment_or_dotenv`; this does not distinguish Render environment from dotenv |
| Actual selected sync mode | `reconciliation` |
| Strategy | `complete_board_comparison` |
| Committed page progress | `pmmp_sync_pages=339`, unchanged between snapshots |
| Sync completion / stop reason | `false` / not recorded |
| Recovery | 892 queued, 3,464 rejected, 10 restored; total 4,366 |
| Index before / now | 4,366 / 5,209 |
| Rows seen since run start | 3,385 |
| Rows inserted since run start | 843 |
| Latest committed listing timestamp | `2026-10-09 17:32:49.377028+00:00`, unchanged between snapshots |
| Time since latest listing timestamp at second snapshot | Approximately 3 h 17 min 18 s |
| Pending queue under current policy predicate | 1,808 |
| Processing claims owned by #59 | 0 |
| Rows with `processing_attempts > 0` in the entire index | 0 |
| Latest processing-start timestamp | NULL |
| Stored candidates / rejects / direct fetches / search calls / AI calls | All 0 |
| Visible other database sessions / blockers | No other sessions in this database in either activity snapshot |

The querying role had `pg_read_all_stats` membership. Nonetheless, pooled connections and instantaneous observations mean an empty activity view does not prove application-process death or exclude an earlier lock incident.

Latest committed listing: index ID `1967`, consultation `1041377`, reference `32/NARSA/2026 - ...`, state `REJECTED`, no processing owner. The next two latest listing timestamps were IDs `1959` and `1958` at `17:32:49.275105` and `17:32:49.176628` UTC. These are the latest durable listing observations, **not business-processed candidates**. The exact final row of page 339 is not recorded as a page-to-row mapping.

The latest page count is evidence of 339 completed page callbacks. Execution last durably reached listing sync, around the boundary after page 339 and before the next completed page callback. It may have stopped during the next fetch, parsing, DB writes, or progress callback. Those operations cannot be distinguished without logs or a process stack.

## 1. Actual runtime path within COLLECTING

`app/core/agent_job_service.py` reserves a run and submits `AgentOrchestrator.execute` to the in-process executor. `app/core/orchestrator.py:78` commits `COLLECTING`, calls `_collect`, and only switches to `NORMALIZING` after the collector returns at line 81.

For an owned normal `pmmp_index` run, collection includes this sequence:

1. Count durable index; empty index returns with baseline warning.
2. Release abandoned processing claims whose owners are no longer active.
3. Recover legacy NULL-state listings using successful business snapshots or cheap scope/deadline gating. This is automatic inside the existing normal run, not a separate manually launched reconciliation.
4. Check reconciliation due status and commit recovery.
5. Crawl the complete public board, compare every observed listing, commit each page in a separate SQLAlchemy session, then commit a SearchRun page-progress snapshot.
6. On successful complete reconciliation, queue eligible stale previously processed active notices for official-detail refresh.
7. Materialize and sort the durable pending/retry/policy-invalid queue.
8. Cheap-gate queue rows, claim eligible rows, perform official-detail enrichment, resolution fallback if configured, relevance/feedback checks and candidate validation. Accepted rows wait for business persistence to acknowledge completion; rejected/retry outcomes may be committed during collection.
9. Return candidates; only then begin orchestrator normalization, deduplication, AI analysis when enabled, validation, saving, and final processing acknowledgment.

Thus COLLECTING includes recovery, full-board traversal even when named incremental, reconciliation, queue preparation, and downstream **collector-level** business policy/detail work. Orchestrator AI analysis and Result saving have their own later stages.

**#59's evidenced long operation is the full-board listing walk.** It has not evidenced queue processing: `pmmp_sync_complete=false`, no queue-start metric, no collection query record, no claims, and zero processing attempts across the ledger. The 1,808-row backlog exists but is not the current demonstrated bottleneck.

## 2. Long-operation and loop inspection

| Operation | Source behavior | Assessment for #59 |
| --- | --- | --- |
| Pagination | `pmmp_listing_collector.py:198`: stops on repeated tuple of consultation references, no next link, declared-page count reached, optional max pages, or final empty page. Page count increments. | No confirmed infinite loop. Runtime passes no `max_pages`; a board with missing/changing counts and endlessly novel signatures has no independent total-page/time bound. Declared count is only published to run metadata when sync returns. |
| Listing HTTP | `PmmpHttp`: timeout 25 s; maximum 3 attempts; retries URLError/TimeoutError/OSError and HTTP 500/502/503/504; backoffs 0.25 s and 0.5 s. Delay 0.35 s between successful-request sequences. Body limited to 2 MB. | Finite retry loop. Roughly 75.75 s per exhausted request under ordinary timeout behavior; this is not a strict total wall-clock deadline for all socket/body operations. Hundreds of successful slow requests can accumulate a long run. |
| PMMP throttling | Listing HTTP 403/429 are not retryable here and should raise; no indefinite Retry-After loop. Listing transport is separate from `AccessLimitedPages`. | No observed proof of throttling. Stored `http_403/http_429=0` does not establish absence during listing sync because those counters belong to the detail reader. |
| Detail HTTP | `integrations/http/html.py:118`: timeout 20 s, max four redirect hops, cache, failed-URL cache; detail wrapper stops a host on 429. Resolver query list and lookup budgets are finite. | Could add substantial time after sync, but no evidence #59 reached this phase. Paid fallback may be enabled by existing runtime config; it was never invoked by the diagnostic. |
| Database work | Each listing uses lookup(s) and flush, including UPDATE of `last_seen_at` for unchanged rows; each page commits index changes then progress. | Thousands of serial DB operations over Neon can amplify latency. Per-page sessions avoid holding the crawl transaction across the next HTTP request, but do not eliminate row locks or slow statements within a page. |
| DB timeouts / locks | App config sets connection timeout 5 s and pool pre-ping, but no app-level statement timeout or lock timeout. Recovery uses one transaction over legacy rows. Claims/finish/persistence use CAS or row locks and commits. | A statement or lock wait can be much longer than an HTTP timeout. No current visible DB session/blocker was observed. The diagnostic's bounded local timeouts are not production app settings. |
| Recovery | Loads Radar 1 Results and scans NULL processing states; normalizes snapshots and applies cheap gating, commits at end; no external HTTP in this function. | Recovery definitely completed: its totals are stored. Last recovery rejection evaluation timestamp was `16:54:23.949436` UTC. This is not an exact function-finish timestamp. |
| Queue preparation | `processing.pending_rows()` loads all eligible rows; reconciliation scans completed run history and refresh candidates without a DB LIMIT. | Queue materialization is not capped; no evidence it was reached in #59. No unbounded retry within this queue loop. |
| Candidate cap | Eligible evaluation limit is `min(RADAR1_MAX_CANDIDATES, AGENT_MAX_CANDIDATES)`; defaults 100 and 200. `examined` also enforces Radar 1 cap. Cheap rejects occur before the cap check. | The 100 default does not cap full-board pages, recovery rows, materialized queue size, or cheap rejections. Effective Render overrides are unknown. |
| Worker lifecycle | `LocalJobRunner`: ThreadPoolExecutor, two task threads, total admission capacity five including queued tasks; created per Flask app/process. Future returned to launch handler but no durable job ownership/heartbeat registry. | Process loss discards execution while committed SearchRun stays running. #59 was executing, not merely waiting for a task thread: it committed 339 pages. |
| Stale lifecycle | `_recover_stale` only runs when reserving a subsequent search; compares start time, default 120 minutes, rather than progress. No timer continuously closes stale runs. | Explains how the UI can remain running indefinitely after process loss. A new launch would mutate #59 and potentially start another search, so it is prohibited here. Long live full scans can also exceed this start-age threshold. |

All inspected processing/resolution loops operate over finite collections. Pagination lacks a global deadline but has repeated-page and declared-page safeguards. No specific infinite-loop defect was established by this evidence.

## 3. Runtime regression comparison

| Previous fast path | Reliability implementation |
| --- | --- |
| Incremental mode passed through to listing collector; three stable unchanged pages could stop the walk. | Durable sync forces `full` regardless of incremental/reconciliation label. |
| Only this sync's NEW/UPDATED observations entered detail policy processing. | Legacy evidence recovery and all eligible durable pending/retry/policy-invalid rows enter the capped queue after the scan. |
| No normal-run periodic reconciliation selection or stale successful detail refresh. | First normal run with no completed reconciliation is due immediately; later checks use 24-hour default. |
| Much smaller typical set of listing SELECT/UPDATE/flush operations. | All board rows, including unchanged ones, incur comparison/write work plus page commits and progress commits. |

Read-only historical comparison in the same configured database:

- #55: `pmmp_index`, incremental, 3 pages, `incremental_overlap`, `12:41:22.344947`–`12:41:49.287109` UTC on October 7: **26.94 seconds**.
- #48/#49: index-mode 3-page overlap runs, approximately 25.27 / 24.82 seconds.
- #56–#58: actual recorded mode was `legacy`; they are not valid examples of the prior fast PMMP incremental path.
- #59: 339 committed pages before loss of observable progress, already **113 times** #55's visited page count; roughly 41 minutes elapsed from run start to the latest committed listing timestamp. It had also performed first-run recovery of 4,366 old rows.

The recorded recovery and reconciliation selection establish that the new path was exercised, independent of the local mode setting. The expanded scan is a deliberate completeness change described in `RADAR1_RELIABILITY_FIX.md`, but changes the latency expectations of a normal interactive run. It is not merely a one-time reconciliation cost: even future runs labeled incremental still walk the complete board in this implementation.

## 4. Stage observability defects

- Stage stays COLLECTING for every operation above. The frontend radar page displays run ID, status, and stage; it does not display `pmmp_sync_pages`, queue/evaluation counters, or freshness of progress. Its existing polling reads stored state, not thread liveness.
- Page callback at `collector.py:724` increments `pmmp_sync_pages` and calls `on_progress`; index changes are already committed. This is a useful durable signal, but no explicit `last_progress_at`, current page URL/identity, declared-page total, elapsed substage, or executing process ID is persisted during the walk.
- `pmmp_sync_declared_pages/results`, counts, stop reason, and sync completion are populated only after sync returns. They are unavailable for an interrupted crawl like #59.
- Listing HTTP attempts do not feed the detail-reader counter used by orchestrator `record_progress`; `direct_fetches=0` while 339 listing pages were visited is an instrumentation gap, not proof no HTTP occurred.
- Recovery has no per-row progress callback. Reconciliation refresh and pending queue materialization also lack timed progress.
- Queue loop commits claims and outcomes, but does not call `on_progress` after each row. `pmmp_evaluated` is assigned in the queue loop's finally block; `_finish_query` calls progress afterward. Resolution search callbacks can incidentally publish partial metrics, but are not a reliable per-item heartbeat.
- A different run could therefore remain COLLECTING while processing many queue rows. **That interpretation does not fit #59's current evidence:** no claim attempts, no completed sync, no queue-start metrics.
- `collector_health=HEALTHY` is the last stored report value, not proof the worker is presently healthy. There is no SearchRun `updated_at` or heartbeat field to date the last page callback exactly; `last_seen_at` is the strongest available durable timestamp proxy.

## LIKELY CAUSE

**Loss/interruption of the executing in-process worker after page 339** best fits the frozen listing timestamp, unchanged page count, no processing claims, no completion/failure write, and absent visible DB sessions. A deploy, worker recycle, crash, memory exhaustion, or service stop can terminate the thread without executing the Python exception/finally paths that would record failure.

The full scan increases exposure to those lifecycle events. An alternative is a still-live process stuck in socket/body reads, CPU/parsing, or a callback operation without committing progress. Ordinary bounded listing retries alone are not a persuasive explanation for a three-hour silent interval. A current DB lock wait is less supported by the empty activity snapshots, while a historical lock incident remains possible.

Render documents SIGTERM on instance shutdown and a subsequent SIGKILL if shutdown does not finish within the configured delay, default 30 seconds: [Render deploy lifecycle](https://render.com/docs/deploys). Render distinguishes continuous dedicated background-worker services from web services: [Render background workers](https://render.com/docs/background-workers). Neither source establishes what happened to #59.

The repository's documented start command is `gunicorn wsgi:app --bind 0.0.0.0:$PORT`; it provides no explicit deployed worker/thread/resource settings. App executor threads are distinct from Gunicorn request threads. Gunicorn timeout concerns worker silence, rather than automatically timing out every background task at the configured duration: [Gunicorn settings](https://docs.gunicorn.org/en/stable/settings.html). Do not assert a Render concurrency cap, plan limit, or 30-second Gunicorn kill as #59's cause without effective config and logs.

## UNVERIFIED PRODUCTION STATE

- Exact Render-to-Neon database mapping and deployed source SHA.
- Whether the original #59 worker/process is alive, crashed, replaced, or paused.
- Whether Render emitted SIGTERM/SIGKILL, Gunicorn WORKER TIMEOUT, OOM, restart, or deployment events near `17:32:49` UTC.
- Exact page 340 request timing/status, final page-339 row, declared current board total, or a traceback/process stack at interruption.
- Effective Render candidate caps, paid-resolution settings, service plan, worker/process counts, Gunicorn flags, or database timeout overrides.

**Activity verdict:** database status is active; measurable committed work is stale at the observations. No continuing progress was measured. Worker death is strongly suspected but unverified. Do not equate `status=running` with live execution.

## 5. Safest next action for current #59 — recommendation only

1. Obtain read-only Render logs, deployment events, metrics, effective start command, and process ownership for October 9, particularly `16:51:39`–`17:35:00` UTC. Correlate `run_id=59`, `pmmp_listing mode=full page=339`, retry messages, the next page, worker exit/start PIDs, and any OOM/signal/timeout event. A working health endpoint only proves a serving process, not that the old job thread exists.
2. If page counters, listing timestamps, or claims advance, or a process stack shows an expected bounded operation, wait and monitor. Current evidence does not support unconditional waiting.
3. If logs/process ownership confirm the executor died, prepare a targeted stale-run recovery for #59 for separate authorization. Preserve committed index rows and pending ledger states; inspect any #59-owned leases before deciding what to release. Current snapshots have zero such leases. Do not delete the index, rerun full reconciliation manually, or use a new launch as the recovery mechanism.
4. If the worker is alive but a loop or blocking operation is confirmed, identify and fix that exact defect first. Any deploy can itself stop a live in-process run, so deployment/recovery sequencing needs explicit consideration and authorization.
5. Separately, after the interruption is identified, review the always-full interactive workload and missing heartbeat/substage instrumentation. Restoring a naive three-page overlap stop would reintroduce the completeness defect the reliability change addressed; a bounded/resumable or separately scheduled comprehensive design needs review rather than an emergency blind reversal.

No recovery or implementation was executed. In particular, `_recover_stale`, `release_abandoned`, `recover_legacy`, and `queue_reconciliation_refresh` were inspected as source only; their observed effects are effects of the existing #59 execution.

## 6. Repeatable bounded read-only checks

Use an existing authorized connection; do not import Flask, call a launch endpoint, or run CLI recovery scripts. The following statements only read application/system records; transaction-local settings expire at rollback.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '2s';

SELECT clock_timestamp() AS observed_at, id, status, current_stage,
       started_at, finished_at,
       run_metadata->'collector_metrics' AS metrics
FROM search_runs WHERE id = 59;

SELECT count(*) AS total, max(last_seen_at) AS last_seen,
       count(*) FILTER (WHERE processing_run_id = 59) AS run59_claims,
       count(*) FILTER (WHERE processing_attempts > 0) AS attempted_rows,
       max(processing_started_at) AS last_claim
FROM pmmp_listing_index;

SELECT processing_state, count(*) AS rows,
       max(evaluated_at) AS last_evaluated
FROM pmmp_listing_index GROUP BY processing_state;

SELECT id, consultation_id, reference, last_seen_at,
       processing_state, processing_run_id, processing_started_at
FROM pmmp_listing_index ORDER BY last_seen_at DESC LIMIT 3;

SELECT count(*) AS queue_count
FROM pmmp_listing_index
WHERE processing_state IN ('PENDING_PROCESSING', 'FAILED_RETRYABLE')
   OR (processing_state IN ('PROCESSED', 'REJECTED') AND
       (evaluated_fingerprint IS NULL OR policy_version IS NULL OR
        evaluated_fingerprint <> fingerprint OR
        policy_version <> 'archeritage-r10'));

SELECT pid, application_name, state, xact_start, query_start,
       wait_event_type, wait_event, pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid();

ROLLBACK;
```

The policy version predicate above matches #59's recorded version and current source. Revalidate it if source changes. Repeat snapshots must use new transactions to measure progress; absence of a database session still requires Render ownership evidence before recovery.
