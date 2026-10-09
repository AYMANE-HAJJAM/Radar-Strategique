# Radar 1 indexed-title implementation

Implemented locally; **not deployed and no real SearchRun executed**. Only #59 diagnostic SELECTs reached the configured Neon database, in a verified READ ONLY transaction ending with ROLLBACK. All processing validation uses fixtures and isolated SQLite databases; network calls are forbidden by the test harness.

## Behavior

- `pmmp_index` is the default. A normal launch reads existing listings, selects titles, verifies official PMMP objects and deadlines, then applies the existing ARCHERITAGE policy, feedback constraints, deduplication and review workflow. No listing crawl, legacy recovery scan or reconciliation runs on this path. Explicit legacy mode and separate ingestion tools remain available.
- Title triage retains the experiment's heritage/services, qualified competitions, major projects and ambiguous truncated scopes. Arabic semantic equivalents support the existing policy while preserving original titles. Unknown Arabic scope goes to official detail. Generic schools/OFPPT, infrastructure, supplies and execution are excluded; studies/supervision of heritage works survive.
- NULL/unproven, pending, retryable, changed-fingerprint and outdated-policy rows remain eligible even when ingestion says UNCHANGED. Rules version is `11` (`archeritage-r11`); old terminal evaluations are recertified lazily, without resetting results or reviews. Current-version successful unchanged rows are skipped.
- Defaults: **25 official candidates / 120-second admission budget** per launch, also respecting existing candidate caps. Never-attempted work precedes retries, with heritage first inside each attempt tier. At most 250 cheap title rejects are recorded per launch; remaining rows are untouched and remain eligible. No sleeping/retry loop or paid search/AI on the index path.
- Official identity, complete object and independently evidenced deadline are mandatory. Unavailable/missing/incomplete/mismatched evidence stays retryable; a confirmed expired/closed notice is rejected. A 429 suppresses further requests to that host for the batch. Requests retain redirects/size/socket limits and add elapsed checks during body reads. The admission budget can overrun by an in-flight request/socket timeout; it is not a hard process deadline or DNS watchdog.
- A durable claim precedes HTTP. Accepted work completes only when Result, ResultObservation and fingerprint/owner acknowledgment commit together. Failed saves and failed/inactive owners release retryable work. Active owners are never stolen. Existing review history survives nonmaterial refreshes; material updates follow the existing review rules.
- The Radar 1 page shows indexed, selected, processed, relevant, rejected and pending counts and a timestamp. Progress snapshots commit before and after each detail attempt. `processed` means attempted this batch, `relevant` means passed collector policy, and `pending` means selected work still lacking durable completion (including retries). `rejected` includes cheap eligible-title rejects and terminal detail/policy rejects; these are batch metrics, not lifetime counts. The exact-run results view uses existing observations.

## #59: recovery remains an operator decision

**CONFIRMED ROOT CAUSE of excess workload:** the deployed reliability path reconciles the full board before business processing. This implementation removes that normal-launch dependency.

**LIKELY CAUSE of the interruption:** lost executing worker. At `2026-10-09 21:34:47 UTC`, the configured Neon database still showed #59 running/COLLECTING, 339 pages, no completion, no claims/attempts, no other visible DB sessions and no listing progress since `17:32:49 UTC`.

**UNVERIFIED PRODUCTION STATE:** Render service/database mapping, worker PID, deployment lifecycle, logs and worker liveness. A database status is not a worker lease. Do not infer death from age or absence of a DB connection. Radar 1 reservation now refuses age-only automatic recovery; it leaves #59 untouched and blocks a replacement launch while #59 is active.

Before deployment or another search, the operator must inspect Render logs/deploy events and identify whether the original process still executes #59. If fresh measurable progress exists, wait. If worker death is confirmed, separately authorize a narrowly scoped transaction to mark only #59 failed, preserving its stage history and results, and release only any claims it owns. Re-read the current state under lock first. Do not run reconciliation/backfill/recovery of the whole index or reset workers/results. No recovery was executed here.

## Migration and deployment

1. Resolve #59 ownership first; deploying may terminate the old worker. Do not redeploy over an unverified live owner.
2. Confirm `alembic_version = e7c91b2486af` and the existing processing-ledger columns. **No new migration or data migration is required.** If that revision is already applied, do not re-run recovery. Only a genuinely older, separately approved environment needs `python -m flask --app wsgi db upgrade` from `backend`.
3. Render: deploy the reviewed backend revision using existing root `backend`, build `pip install -r requirements.txt`, and existing start `gunicorn wsgi:app --bind 0.0.0.0:$PORT`. Explicitly set `RADAR1_DISCOVERY_MODE=pmmp_index`, `RADAR1_PROCESSING_BATCH_SIZE=5`, `RADAR1_PROCESSING_MAX_SECONDS=60`, `RADAR1_AI_ENABLED=false` for the first test. Keep HTTP timeout 20 seconds. No new dependencies or scheduler. Existing explicit `legacy` settings override the new default and must be corrected.
4. Deploy the matching frontend revision through the existing Next/Vercel pipeline (`npm ci`, `npm run build`), preserving `NEXT_PUBLIC_API_URL`. No worker reset, startup crawl, or startup queue consumption is needed. Restore batch defaults 25/120 only after review of the first test.

## First real manual test — operator only

1. Confirm no active Radar 1 run, correct deployed mode/version, existing indexed data and #59's explicitly resolved ownership. Preserve a read-only baseline of result IDs/reviews and listing states. Do not clear anything.
2. Click **Lancer une recherche exactly once** in Radar 1. Record the new run ID. Expect strategy `indexed_title_batch`, `pmmp_sync_mode=not_requested`, pages 0, search/AI calls 0, at most 5 detail attempts, and visible progress timestamps. No real acceptance is promised if PMMP refuses official access.
3. Inspect `À traiter` for that exact run and corresponding ResultObservations. Cross-check each displayed reference, full official title, buyer and verified future deadline. Historical Settat `04/2026/AUS` and Meknès `42/2026/ADERFES` were expired in the experiment; selection coverage does not make them currently eligible. Safi `145/2026` and Sidi Ifni `04/2026/CA/BR/RGON` require current official verification.
4. Confirm accepted rows have matching evaluated fingerprints/policy version and no owner; retries/overflow remain pending. Check earlier approved/rejected reviews remain intact. A completed batch with pending > 0 is expected. If only official-access failures occur, keep them retryable and investigate access; do not weaken verification or launch exhaustive recovery.
5. Only after inspecting that first run, optionally launch one further batch to verify resumption and absence of duplicate business results. Never launch concurrently or retry by restarting a worker.

## Validation and limits

The offline corpus covers **all 112 experiment candidates**, including all four known references. Tests cover Arabic heritage, noise/execution, NULL/UNCHANGED eligibility, complete official enrichment, deadline/object/identity failures, bounded admission, retries, interrupted saves, superseded fingerprints, review preservation, authenticated exact-run visibility and committed progress. Arabic title/buyer evidence matching preserves literal text separately from semantic policy matching; an absent Arabic buyer cannot pass by folding to an empty string.

Executed checks (overlapping counts, not additive):

| Check | Result |
| --- | --- |
| Backend full suite, `python -m pytest -q` | 1,045 passed |
| After the final Arabic evidence refinement: `python -m pytest tests/modules/radar1/test_indexed_title_flow.py tests/modules/radar1/test_procurement_pipeline.py tests/modules/radar1/test_processing_reliability.py -q` | 203 passed |
| Agent boundary, production-acceptance fixtures and usage-accounting follow-up | 226 passed |
| Frontend `npm test` | 30 passed |
| Frontend `npm run typecheck -- --incremental false`, `npm run lint` | Passed |
| `git diff --check` | Passed |

The full suite preceded the final Arabic evidence refinement; the affected indexed/official/persistence pipelines were rerun afterward. No live browser or PostgreSQL processing/concurrency test was performed. Fixture-generated historical audit output was restored to its original bytes.

Remaining blockers: Render ownership evidence for #59; production official-detail accessibility; and live database/worker configuration verification. SQLite fixture tests do not establish PostgreSQL concurrency behavior or production quality/recall. Unsupported Arabic official-page labels or unreadable complete objects remain retryable rather than being accepted from listing evidence. New opportunities require separately maintained index ingestion; normal launch intentionally does not refresh the board.
