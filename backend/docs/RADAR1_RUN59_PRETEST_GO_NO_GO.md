# Radar 1: scoped recovery completed and verified

## Authorized recovery outcome — October 10, 10:18 UTC

The user explicitly authorized the prepared #59-only recovery. The guarded DO block was executed with its COMMIT withheld until preservation checks passed. Before COMMIT, the transaction revalidated the documented state, locked #59, compared complete-row fingerprints of all listings, results, reviews, audit events, observations and all other SearchRuns, and verified that only the six approved failure/history fields of #59 changed. Any mismatch would have caused ROLLBACK. All guards and preservation checks passed.

An independent connection then used a verified READ ONLY transaction, ending with ROLLBACK, to confirm the committed outcome at **2026-10-10 10:18:08.444988 UTC**:

- #59 is `failed / FAILED`, finished_at `2026-10-10 10:18:00.057763 UTC`, error_kind `abandoned_worker_confirmed`.
- No Radar 1 run remains active. #59 owns zero claims and has zero ResultObservations.
- All **5,209 index rows and 1,808 PENDING_PROCESSING rows** are unchanged, verified by complete-row fingerprints. Latest listing timestamp remains October 9 17:32:49.377028 UTC.
- All **71 business results, 25 market reviews, 106 result audit events and 108 ResultObservations** are unchanged. All other SearchRuns are unchanged.
- Existing #59 run_metadata and all other unapproved columns are unchanged. Its two previous stage-history entries are preserved, with one FAILED recovery entry appended.
- Only #59's `status`, `current_stage`, `finished_at`, `error_kind`, `error_message` and `stage_history` changed.

Audit export: `C:\Users\AYMANE~1\AppData\Local\Temp\radar1_run59_authorized_recovery_i1dd7bj6.json` contains the original run row, SQL hash, preservation fingerprints and verification outcome. No application startup, search, PMMP crawl, index reset, business processing, configuration change, worker action or deployment was performed.

The active-run blocker is resolved. For the user's first manual test, make these settings effective on deployed revision `4baa8e6` before clicking once:

```dotenv
RADAR1_DISCOVERY_MODE=pmmp_index
RADAR1_PROCESSING_BATCH_SIZE=5
RADAR1_PROCESSING_MAX_SECONDS=60
RADAR1_AI_ENABLED=false
SOURCE_HTTP_TIMEOUT_SECONDS=20
```

The 60 seconds is an admission budget; an in-flight request may finish afterward. No new migration is needed beyond existing e7c91b2486af. Configuration was not changed or independently verified here; batch/time defaults are 25/120, so do not assume 5/60 without confirming the effective settings. Once effective, the single bounded manual test is cleared from the stale-run perspective. This recovery did not launch or authorize an automated test.

Earlier approval-pending and NO-GO sections below are historical and superseded by the completed authorized recovery.

## Current decision — October 10, 10:04 UTC

The user has now confirmed in Render Events that deployment `4baa8e6` completed successfully and replaced the previous deployment. **This is sufficient operational evidence that #59's original in-process worker cannot continue.** It resolves the original-instance replacement prerequisite in the older sections below. The in-memory thread cannot migrate to the replacement instance, and that instance does not automatically resume a run whose persisted status is already running. No further general audit is required.

One fresh verified READ ONLY Neon transaction, ending with ROLLBACK, observed at **2026-10-10 10:04:17.206367 UTC**: #59 remains running/COLLECTING, started October 9 16:51:39.570765 UTC, finished_at NULL, pages 339, all candidate/analysis/accepted/manual-review/new/updated counters zero. There are **5,209 indexed listings, exactly 1,808 PENDING_PROCESSING listings, zero #59 claims and zero #59 ResultObservations**. #59 is the sole active Radar 1 run. Last listing progress remains October 9 17:32:49.377028 UTC.

**GO to request authorization for the exact #59-only recovery SQL below; it has not been executed.** The transaction locks and revalidates #59, then changes only its status/stage to failed/FAILED, records a finish time and abandonment reason, and appends a history entry. No listing, Result, ResultObservation or review row is updated or deleted. All 1,808 pending listings and all 5,209 index rows remain intact. There are no claims to release. Any guard failure aborts the transaction.

The manual test remains blocked until recovery is separately authorized and completed. After recovery, re-read the active-run slot and use deployed `pmmp_index` with batch size 5 and a 60-second admission budget for one separately authorized manual test. Recovery authorization does not authorize a search, crawl, index reset, configuration change or business-record alteration. Earlier NO-GO sections below are historical and superseded by this confirmed rollout evidence.

## October 10 deployment-evidence follow-up

User supplied actual deployment evidence: previous revision `8bb61b6`, deployed October 9 around 16:50 UTC; replacement revision `4baa8e65d3a28092cd5e7d01f27eaf666467486a`, deployment started 22:06:31 UTC, new Gunicorn PID 44 started 22:07:40 UTC, service live 22:07:47 UTC. This replaces the earlier placeholder-only evidence. Its source is the user's Render deployment summary, not direct authenticated Render access by this diagnostic.

**Commit contents CONFIRMED:** Git resolves that exact full hash, which is now local HEAD. Inspection of the committed blobs and the `pmmp_index_discovery` AST confirms `title_filter.py`, `indexed_title_batch`, official-detail verification, bounded 25/120 defaults, resumable NULL/UNCHANGED eligibility, rules version 11, no-paid-services handling, Radar 1 age-only recovery protection and UI progress. There are no calls to `sync_listings`, `recover_legacy`, `queue_reconciliation_refresh` or `reconciliation_due` in the normal index discovery function. This verifies the commit's source, not effective Render environment overrides.

**Worker termination: strongly supported, not directly confirmed.** [Render's deployment documentation](https://render.com/docs/deploys) says the old instance is sent SIGTERM 60 seconds after traffic handoff, then SIGKILL if necessary after its shutdown delay (default 30 seconds; configurable up to 300 seconds without a support exception). If 22:07:47 is the handoff for the instance that owned #59, expected SIGTERM is 22:08:47, default forced-termination deadline 22:09:17, and ordinary maximum deadline 22:13:47 UTC on October 9. These are calculated expectations, not observed exit events. A new PID is container-local and does not identify or prove the old PID's death. The supplied summary does not show original-instance exit, all-instance rollout completion, configured shutdown delay or subsequent rollback/failure events. For a normally completed replacement of the original instance, that instance cannot still execute #59 now; that condition has not been independently verified here.

Both committed versions use an in-process `ThreadPoolExecutor`, with a fresh executor at application startup. Its running thread does not migrate to a new container. The new process does not automatically resume persisted active runs; execution claiming requires status `initialized`, whereas #59 remains `running`. Therefore a confirmed original-instance termination establishes task abandonment even if the database status remains active.

**Fresh Neon evidence, October 10 09:51:15.936581 UTC:** verified READ ONLY transaction, bounded timeouts, ROLLBACK. #59 remains running/COLLECTING, started October 9 16:51:39.570765 UTC, 339 pages, old strategy `complete_board_comparison`, policy r10, no finished/error timestamp. Candidate/analysis/accepted/manual-review/new/updated counters and ResultObservations are all zero. Index still contains 5,209 rows, latest listing observation October 9 17:32:49.377028 UTC, last evaluation 16:54:23.949436 UTC, zero attempts and zero #59 claims. No other visible DB sessions; #59 is the sole active Radar 1 run. Migration e7c91b2486af remains applied. No new committed progress since earlier snapshots.

**Decision: NO-GO for a manual launch now.** Even after original-instance termination is confirmed, #59's active database slot must be resolved through separately approved scoped recovery. Before approving that recovery, confirm the original instance was replaced/terminated (old worker exit or completed rollout evidence covering that instance) and the service/database mapping. The zero-claim SQL below still matches the latest observed state and changes only #59, preserving every indexed listing and all previous review decisions. It has not been executed. After recovery, verify no active Radar 1 run and effective `RADAR1_DISCOVERY_MODE=pmmp_index`, batch size 5, admission budget 60 seconds, and the deployed revision across serving instances; then the bounded first manual test can be cleared. No new migration, reconciliation or worker restart is required.

The older sections below retain the prior October 9 observations and conditional operator procedure.

Service URL follow-up: the supplied `https://radar-strategique.onrender.com` returned HTTP 200 / `{"status":"ok"}` from `/api/health` at **2026-10-09 22:12:42.737435 UTC**, and HTTP 200 / `{"status":"ready"}` from `/api/ready` at **22:12:44.338373 UTC**. These were bounded, unauthenticated GETs only. They establish API availability and reported database readiness, not the identity/liveness of #59's original executing worker, the deployed commit, or the exact database mapping. The supplied commit/log/event fields were literal placeholders; no actual worker termination or deployment evidence was provided. **NO-GO remains unchanged.** Recovery and any real search require the user's explicit approval after ownership is verified.

Observed 2026-10-09 **22:07:40.444531 UTC** and **22:08:40.579482 UTC**, 60 seconds apart. No Radar search, PMMP request, application startup, recovery, worker action, deployment or database mutation was performed.

## Findings

1. **Original worker: CANNOT BE VERIFIED.** No Render operational connector, Render API credential or accessible browser session was available. Browser inventory returned no apps or browsers. Local logs are historical audits. No current Render log, PID, thread/task inventory or deployment exit event was obtained. Worker loss remains likely, not confirmed.
2. **No recent committed progress in the configured Neon database.** Both independent READ ONLY transactions verified `transaction_read_only=on`, used 5-second connection / 8-second statement / 2-second lock limits and ended with ROLLBACK.

| Evidence | Both snapshots |
| --- | --- |
| #59 | Radar 1; running / COLLECTING; no finished timestamp |
| Started | 2026-10-09 16:51:39.570765 UTC |
| Recorded mode / strategy / policy | pmmp_index / complete_board_comparison / archeritage-r10 |
| Listing pages / completion | 339 / false |
| Indexed rows | 5,209 |
| Last listing observation | 2026-10-09 17:32:49.377028 UTC |
| Last listing change | 17:32:49.028734 UTC (first snapshot) |
| Last evaluated listing | 16:54:23.949436 UTC |
| Processing attempts / claims owned by #59 | 0 / 0 |
| #59 candidates, analyses, accepted, new/updated results | All 0 |
| ResultObservations for #59 | 0 |
| Other visible DB sessions / blockers | None |
| Active Radar 1 runs | Only #59 |
| Migration | e7c91b2486af (first snapshot) |

The last listing observation was about **4 hours 36 minutes** before the second snapshot and is unchanged from prior diagnostics. No business processing has started in the index ledger. An absent database connection does not prove process death: a worker may be outside the database or on HTTP, and pooled activity is instantaneous.

Processing states in the first snapshot: 1,808 PENDING_PROCESSING, 7 PROCESSED, 3,394 REJECTED. These include old recovery decisions; the last evaluated timestamp is not proof of successful candidate processing by #59.

3. **A new launch is not safe to try.** #59 still holds the active-run slot. The new local code refuses age-only Radar 1 recovery and should reject a new reservation while #59 is active. If production still runs the previous build, its age-based recovery could mark #59 failed and launch another worker while the old crawler remains alive. Do not use a launch attempt to test which behavior is deployed.
4. **Production deployment is unverified.** The user's newly deployed simplified flow cannot be confirmed from the accessible evidence. No Render revision, effective environment or database/service mapping was obtained. #59's recorded r10 strategy describes its original execution, not the current deployed revision. Absence of an r11 SearchRun also does not prove deployment absence. The database facts above apply to the configured Neon source, whose exact linkage to Render remains independently unverified.
5. **Manual-run decision: NO-GO.** Resolve ownership, confirm the intended deployment and its database mapping, and explicitly resolve the active-run slot before reconsidering GO. Local fixture tests do not establish that production meets these conditions.

## Exact conditional recovery procedure — not executed

**Prerequisite:** an operator must establish through Render logs/process or deployment-instance evidence that every process capable of continuing the original #59 task has exited and cannot resume. Correlate `run_id=59`, the instance/deploy, worker PID and task thread. A new deployment being live, an old timestamp or a lack of logs is insufficient unless the original instance's termination is confirmed. If the worker is alive, leave #59 alone and investigate its current operation; wait only when measurable progress is demonstrated.

Once abandonment is confirmed and recovery is separately authorized:

1. Confirm the Render service uses this exact Neon database. Save #59's full row, its stage history and metrics, all rows with `processing_run_id=59`, and its ResultObservations to an operator-controlled audit export. Do not create backup tables or reset results.
2. Take another read-only snapshot. If counters, pages, claims, observations or status changed, stop and re-audit ownership. The transaction below is deliberately valid only for the observed zero-claim/zero-result state.
3. In one short operator-controlled transaction, lock #59, verify its exact identity/state and mark **only #59 failed** with an audit reason and an appended stage-history entry. Existing metrics, review history, business results and listing states remain intact. There are currently zero claims to release; no listing UPDATE is necessary.

The following is a **future operator script**, not a command run during this diagnostic. Execute only after the prerequisites above. Any exception requires ROLLBACK and investigation, not removing its guards.

```sql
BEGIN;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '2s';
SET LOCAL TIME ZONE 'UTC';

DO $recovery$
DECLARE
  r search_runs%ROWTYPE;
BEGIN
  SELECT * INTO r FROM search_runs WHERE id = 59 FOR UPDATE NOWAIT;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'SearchRun 59 missing; abort';
  END IF;
  IF r.radar_id IS DISTINCT FROM 1
     OR r.status IS DISTINCT FROM 'running'
     OR r.current_stage IS DISTINCT FROM 'COLLECTING'
     OR r.started_at IS DISTINCT FROM
        TIMESTAMPTZ '2026-10-09 16:51:39.570765+00'
     OR r.finished_at IS NOT NULL
     OR (r.run_metadata->'collector_metrics'->>'pmmp_sync_pages')
        IS DISTINCT FROM '339'
     OR (r.run_metadata->'collector_metrics'->>'pmmp_discovery_strategy')
        IS DISTINCT FROM 'complete_board_comparison'
     OR (r.run_metadata->'collector_metrics'->>'pmmp_policy_version')
        IS DISTINCT FROM 'archeritage-r10'
     OR r.candidates_count IS DISTINCT FROM 0
     OR r.analyzed_count IS DISTINCT FROM 0
     OR r.accepted_count IS DISTINCT FROM 0
     OR r.new_results_count IS DISTINCT FROM 0
     OR r.updated_results_count IS DISTINCT FROM 0 THEN
    RAISE EXCEPTION 'Run 59 changed; re-audit before recovery';
  END IF;
  IF EXISTS (SELECT 1 FROM pmmp_listing_index
             WHERE processing_run_id = 59)
     OR EXISTS (SELECT 1 FROM result_observations WHERE run_id = 59) THEN
    RAISE EXCEPTION 'Run 59 has claims/observations; re-audit before recovery';
  END IF;

  UPDATE search_runs
  SET status = 'failed', current_stage = 'FAILED',
      finished_at = transaction_timestamp(),
      error_kind = 'abandoned_worker_confirmed',
      error_message = 'Operator confirmed original Render worker termination; scoped manual recovery of run 59.',
      stage_history = (
        COALESCE(stage_history::jsonb, '[]'::jsonb) ||
        jsonb_build_array(jsonb_build_object(
          'stage', 'FAILED', 'at', transaction_timestamp(),
          'reason', 'abandoned_worker_confirmed'
        ))
      )::json
  WHERE id = 59;
END;
$recovery$;

SELECT id, radar_id, status, current_stage, finished_at, error_kind
FROM search_runs WHERE id = 59;
COMMIT;
```

If a later audit finds abandoned PROCESSING claims, do not use this zero-claim script. Review a separate scoped release of **only** confirmed #59-owned PROCESSING rows to FAILED_RETRYABLE, clearing their owner/start fields while preserving fingerprints, attempts, evaluated evidence and all business results. Never perform whole-index recovery or reconciliation for this incident.

4. Re-read #59 and the active Radar 1 run list in a new read-only transaction. Confirm the scoped change and absence of other active Radar 1 runs. Retain the audit export and Render termination evidence.
5. Verify the actually deployed backend contains `indexed_title_batch`, rules version 11, the Radar 1 age-only recovery guard, and `RADAR1_DISCOVERY_MODE=pmmp_index`; verify effective batch/time settings and migration e7c91b2486af. Confirm all serving instances use that revision and database. This verification must not start a SearchRun.
6. Only then reconsider GO for the single bounded manual test described in `RADAR1_SIMPLIFIED_FLOW_IMPLEMENTATION.md` (5 candidates / 60-second admission budget, official verification, no paid services). No automatic recovery or test was performed here.
