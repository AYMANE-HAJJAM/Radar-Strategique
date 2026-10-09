# Radar 1 reliability fix

Date: 2026-10-09. The implementation follows `RADAR1_LOCAL_DIAGNOSTIC.md`, which describes the original code/database snapshot before these changes.

**Ready for deployment and a user-operated manual test after migration and configuration checks. Not deployed or migrated by this task.** No real Radar run, backfill, PMMP synchronization, reconciliation, or paid API call was executed during implementation. The 528 entries associated with failed local-configured run #54 have not been recovered or processed for real.

Production database state remains **NOT VERIFIED**. The configured local database is remote Neon; it is not assumed to be the Render production database. Vercel/Render URLs alone do not establish database identity or actual environment values.

## 1. Confirmed causes addressed

| Original cause | Change | Verification |
|---|---|---|
| An index write was treated as the only handoff to business processing; a failed run could commit discovery through progress callbacks and subsequent runs would skip UNCHANGED entries. | Durable per-listing business states, evaluated fingerprint, policy version, owner lease and retry reasons. New discovery is pending. Successful business persistence owns completion. | Interrupted collection/save/run fixtures; unchanged unprocessed listing fixture. |
| NEW/UPDATED entries beyond the candidate cap were indexed and permanently excluded from later business processing. | Each run selects the durable queue independently of technical NEW/UPDATED. Overflow stays pending. | Three launches with cap 1 persist three distinct synthetic notices, once each. |
| Three consecutive unchanged pages were used as evidence that deeper pages contained no new listings. | The production durable sync walks the complete board in incremental and reconciliation modes. | Both modes discover a new fourth-page notice after three unchanged pages. |
| Persisted `manual_review` observations were excluded from the exact-run web list. | Include actionable manual-review snapshots, map their NEW/UPDATED discovery dimension to the existing frontend contract, retain the current PENDING filter. | Authenticated exact-run API test and existing status/run-scope regressions. |
| Dashboard pending count included rows hidden by current queue eligibility. | Radar 1's dashboard count uses the same eligibility/deduplication function as its pending list. | Authenticated dashboard/list consistency test with eligible heritage and excluded infrastructure fixtures. |
| Stored runs could use legacy discovery even when a different mode was expected. | Actual resolved mode, configuration source, strategy, policy version and sync/queue counters are recorded. Invalid runtime mode fails explicitly. | Runtime metadata fixture. Production configuration is still an operator check. |
| Public HTTP could occur while index/run writes shared one transaction. | Normal index synchronization uses a separate session, committing each complete page before the next request. Partial discovery is durable pending work. | Page-two failure leaves the newly indexed synthetic row pending and writes no business result. |

The previous diagnostic's business-scope tests did not justify rewriting the relevance policy. `policy.py` and `validators.py` remain unchanged. Existing heritage, relevant competition, major-project, school/OFPPT, staff-housing, infrastructure and pure-works tests remain part of the backend suite.

## 2. Files changed

Paths below are relative to `backend/`.

| File | Purpose |
|---|---|
| `app/db/models/pmmp_listing_index.py` | Eight ledger columns, processing-state index and constraint. |
| `migrations/versions/e7c91b2486af_pmmp_processing_ledger.py` | Additive ledger migration; existing rows remain NULL/unclassified. |
| `app/modules/radar1_markets/processing.py` | Evidence recovery, cheap scope/freshness gate, queue selection, claims, guarded completion, stale-owner release, reconciliation refresh. |
| `app/modules/radar1_markets/pmmp_listing_index.py` | New/changed rows pending; complete comparison; independent per-page transactions. |
| `app/modules/radar1_markets/pmmp_listing_collector.py` | Adapter page-completion hook. |
| `app/modules/radar1_markets/collector.py` | Durable queue, cap/resume, explicit outcomes, discovery diagnostics and source-failure diagnostics. PMMP's jurisdiction is carried into normalized hits. |
| `app/modules/radar1_markets/service.py` | Specialized lifecycle hooks; shared orchestration stays radar-independent. |
| `app/core/radar_agent_base.py`, `app/core/orchestrator.py` | Generic handoff hooks, lease validation before saves, atomic business acknowledgment, release of incomplete handoffs. |
| `app/api/results.py`, `app/api/radars.py` | Exact-run manual-review visibility and dashboard/queue count consistency. |
| `app/config.py` | Discovery-source diagnostics; reconciliation interval default 24 hours. |
| `app/modules/radar1_markets/preview.py`, `app/cli.py` | Offline disposable-database preview. Listing-only baseline command also uses per-page transactions; its help explicitly says it writes index rows. |
| `tests/conftest.py` | Explicit legacy default in isolated fixtures, independent of the developer's `.env`. |
| `tests/modules/radar1/test_processing_reliability.py` | End-to-end fixture reliability and source-side-effect checks. |
| `tests/modules/radar1/test_processing_migration.py` | Isolated SQLite upgrade/downgrade and PostgreSQL offline DDL checks. |
| `tests/modules/radar1/test_pmmp_listing_index.py`, `test_pmmp_phase3_integration.py` | Replace unsafe overlap/UNCHANGED assumptions with full traversal and proven processing completion. |

No frontend implementation change is required: its existing run list receives `run_observation` values `new` or `updated` for actionable manual-review observations. No actual `.env`, Render environment, or production database was changed.

## 3. Migration

New revision: **`e7c91b2486af`**, parent **`a1b2c3d4e5f6`**.

It adds `processing_state`, `processing_run_id`, `processing_started_at`, `evaluated_at`, `evaluated_fingerprint`, `policy_version`, `processing_attempts`, and `processing_reason`. Existing rows have NULL processing state and zero attempts. No recovery, SearchRun, business backfill, or policy evaluation runs during migration or application startup.

`processing_run_id` is a logical lease owner. There is no foreign key from the durable index to business-run history, so existing business archive/reset tooling retains its safeguards and the index survives removal of business history. Abandoned-lease checks include owner status and run-start timing to avoid treating a reused run ID as the original owner.

The actual configured database remains on **`a1b2c3d4e5f6`**. This migration was exercised only on disposable SQLite and generated PostgreSQL SQL. It has **not** been applied locally or in production.

## 4. Processing states and transactions

| State | Meaning / next action |
|---|---|
| NULL | Legacy entry needing processing-evidence assessment. |
| `PENDING_PROCESSING` | New/changed/recovered notice awaiting business processing. |
| `PROCESSING` | Claimed by one running SearchRun for one listing fingerprint. |
| `PROCESSED` | Business persistence succeeded, or qualified prior business evidence was recovered. |
| `FAILED_RETRYABLE` | Transient resolution/parser/persistence failure or interrupted handoff. Remains queued. |
| `REJECTED` | A deterministic scope/freshness rejection or a persisted rejection, with fingerprint/version/reason recorded. |

Technical UNCHANGED describes the listing fingerprint. Business completion depends on the ledger. Fingerprint changes reset the handoff to pending; terminal entries with missing/different evaluated fingerprints or policy versions are also queued. The current version derives from the existing agent rules version: `archeritage-r10`.

Claims use a conditional database update and are committed before official HTTP. Accepted candidates carry a listing-ID/fingerprint token through normalization and deduplication. The persistence path verifies the live owner and locks the listing lease. `Result`, `ResultObservation`, human-review workflow changes and successful ledger acknowledgment commit together. A superseded handoff cannot save/acknowledge another listing version.

Deterministic exclusions commit their ledger decision without inventing a business card. Parser/source/resolution failures stay retryable. A persisted credible fallback stays retryable until official verification becomes available; current validators still determine whether such a fallback is eligible for persistence.

Run completion releases handoffs that never reached successful persistence, including normalization/validation skips. Run failure releases outstanding claims after rollback. If database failure prevents release, the next normal run reclaims leases whose owners are inactive. Existing active-run reservation and stale-run timeout remain in force.

## 5. Recovery, including failed run #54

**Recovery is included in the next normal `pmmp_index` Radar 1 run. It has not been executed on real data.** No separate backfill command is needed.

Legacy processing proof requires a persisted Radar 1 analysis, the current agent rules version, a complete matching normalized discovery snapshot, and a business-save timestamp at or after the index version's `last_changed_at`. Unverified credible fallbacks cannot certify completed official processing. Qualified evidence restores completion without recreating or reopening a result.

When proof is absent, the existing cheap scope gate and an unambiguous expired listing deadline can reject noise before HTTP. Remaining plausible notices are queued. Aggregate baseline/backfill counts, a matching reference alone, technical UNCHANGED, and an older business save do not certify that index version.

The 528 rows from failed #54 are covered by these rules because their legacy ledger is unclassified. Their eventual pending count may be reduced by valid processing evidence, expiry or scope exclusions. There is no hard-coded run-number reset, blanket reprocessing, promise of 528 accepted notices, or forced NEW/UPDATED result.

Human APPROVED/REJECTED status remains owned by the existing workflow. Reprocessing can produce UNCHANGED, enrich official evidence, or reopen review only when the workflow identifies a material change.

## 6. Caps and incremental/reconciliation behavior

The business budget is bounded by `RADAR1_MAX_CANDIDATES` and `AGENT_MAX_CANDIDATES`. Cheap exclusions do not spend an enrichment slot. Expired backlog cannot exhaust the cap ahead of active opportunities. Queued work is ordered by attempts, first-seen time and ID; fresh work is prioritized over repeated transient failures. Overflow is retained for later manual launches.

Incremental mode now compares **every available board page**, persists technical deltas and processes only queued business work. It does not stop after unchanged pages. The standalone experimental in-memory collector still offers the old overlap heuristic; the durable production sync always requests full traversal, so that heuristic is not the production stopping criterion. `RADAR1_PMMP_OVERLAP_PAGES` remains compatible with older tooling but cannot terminate the durable sync.

Periodic comprehensive reconciliation is checked only when a normal user-triggered run executes. `RADAR1_PMMP_RECONCILIATION_HOURS` defaults to **24**. A run is due if there is no recorded successful complete reconciliation or the last one is older than that interval. Successful reconciliation also queues stale, previously processed, active notices actually seen on that board walk for official-detail refresh. The usual processing cap and material-review rules apply. Rejected noise is not blindly re-enriched.

No scheduler or live reconciliation was installed or executed. If no normal runs occur, this interval does not launch work by itself. Operators can later schedule ordinary runs through their separately authorized deployment process.

Complete walking costs more public requests than the old early stop. PMMP pagination is a changing public dataset, not an atomic snapshot. Pagination loops/errors and declared-count discrepancies are visible in diagnostics; an incomplete walk does not establish a successful reconciliation watermark. Historical index rows are retained, so total index size can exceed today's board count.

Run metadata under `run_metadata.collector_metrics` includes:

- `discovery_mode`, `discovery_mode_source`, `pmmp_policy_version`, `pmmp_discovery_strategy`.
- `pmmp_sync_mode`, `pmmp_sync_complete`, `pmmp_sync_pages`, stop reason and declared page/result counts.
- `pmmp_sync_new`, `pmmp_sync_updated`, `pmmp_sync_unchanged`, `pmmp_sync_duplicate`, `pmmp_sync_unique`, count discrepancy and index counts before/after.
- `pmmp_recovery`, reconciliation refresh count, queue count before/after collection, evaluated count and completions without a business result.
- Sync/processing exception type where applicable, alongside existing source errors, traces, health reasons and truncation metadata.

`pmmp_queued_after_collection` excludes accepted candidates still in PROCESSING awaiting persistence. Read final ledger counts after the run ends to assess remaining work.

## 7. Automated validation and real-data preservation

Tests use disposable SQLite databases, synthetic notices and scripted HTML. HTTP and paid-search paths are denied/mocked. Synthetic SearchRuns are created only inside those isolated databases. The suite covers interruption, unchanged unprocessed rows, cap overflow/resume, failure retry, repeated launches, duplicate prevention, deeper-page discovery in both modes, manual-review web visibility, preservation of approved decisions, periodic detail refresh, obsolete-worker safeguards, migration safety, preview isolation and runtime diagnostics.

Final full backend suite: **909 passed in 179.75 seconds**, including dashboard/list consistency, recovery-timestamp and preview-cap cases. Earlier focused validation: **504 passed in 81.36 seconds** across all Radar 1 tests, API tests, specialized-agent integration and reset-tool integration, covering recovery-state and preview-reason refinements. `git diff --check` passed. The test-generated historical acceptance artifact was restored to its original contents.

Three SELECT-only PostgreSQL transactions against the **local-configured** database returned identical row counts and whole-table SHA-256 hashes:

| Table | Rows | Matching SHA-256 |
|---|---:|---|
| `pmmp_listing_index` | 4,366 | `274e45ac6c4f98afb28d1f2be3e8d8bb845efc43322cdd9d0113878f8382d2f0` |
| `results` | 71 | `ab4f4842daa8cc608c2b9eae723bdd2434794e672d388b9ccbb176f69698880f` |
| `result_observations` | 108 | `544dce6f0bee93a479469a96aedc4fba5a48cc239fbe702fb390d33f95873124` |
| `search_runs` | 48 | `e55264fbf67503f4805d0ea0210c492c1eb6c8dc8cad2e3364d435e2dcd66ee9` |
| `market_reviews` | 25 | `b85b4fbf1584f0a042d41ba2422bc0c0d7976e97485675016c1c47c923cdd60f` |
| `result_audit_events` | 106 | `626703c9db46b0629821752cbfda7b485556964958f3215ccf10650b272babe7` |

Business-table counts cover all radars; the earlier diagnostic's 60 results/97 observations concern Radar 1 specifically. These hash checkpoints were captured during validation, not retrospectively before implementation. The earlier diagnostic counts also remain consistent. No real write/recovery/migration command was performed. Production tables were not accessible and are not covered by this comparison.

## 8. Reusable preview

From `backend/`, using the configured environment:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi radar1-preview --limit 100
```

On Render/Linux:

```sh
python -m flask --app wsgi radar1-preview --limit 100
```

Default source is a read-only snapshot of the configured database. PostgreSQL uses `SET TRANSACTION READ ONLY`. Reflection supports the pre-ledger schema, so this command can preview before migration. It copies only radar definitions, existing results and listing rows into disposable in-memory SQLite. Recovery predictions and collector evaluations occur there, and that database is discarded.

Fixture mode avoids source-database queries entirely:

```sh
python -m flask --app wsgi radar1-preview --fixture /path/to/fixture.json --limit 10
```

Fixture shape:

```json
{
  "listings": [
    {
      "source": "marchespublics.gov.ma",
      "consultation_id": "FIXTURE-ID",
      "organization": "fixture",
      "reference": "FIXTURE-ONLY/2026",
      "title": "Etude architecturale de restauration du patrimoine",
      "buyer": "Acheteur fictif",
      "publication_date": "09/10/2026",
      "deadline": "09/11/2026 11:00",
      "procedure": "Appel d'offres ouvert",
      "category": "Services",
      "location": "FES",
      "detail_url": "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=FIXTURE-ID&orgAcronyme=fixture"
    }
  ],
  "detail_pages": {}
}
```

Supply matching fixture HTML in `detail_pages`, keyed by the exact URL, to exercise official-detail extraction/verification. Missing detail is explicitly unavailable offline; eligibility remains subject to existing validators. The illustrative fixture above is not a real opportunity or a promise of acceptance, and its dates should be adjusted for the test date.

Output distinguishes `fixture_prediction` from `database_snapshot_offline_prediction`, sets `live_observations=false`, and reports references, fingerprints, states, discovered/indexed count, queue/recovery predictions, evaluations, rejects, accepted/review candidates and cap overflow. The queue simulation applies to `pmmp_index`; a runtime `legacy` configuration remains visible and would not use this queue in a normal run.

Safety verified by source-engine SQL capture and complete source-row comparisons: no source INSERT/UPDATE/DELETE/DDL, result/review/index change, new SearchRun, or permanent processing transition. Paid search is disabled and its injected provider fails closed; official HTTP is replaced with fixture pages. The process-wide feedback profile is not read/trained/replaced by preview. Tests verify that its cached profile remains unchanged.

Preview has deliberate limits: it fetches no current PMMP board or live official details, performs no AI analysis, and does not simulate final business persistence/deduplication or train historical feedback. Accepted/review candidates are policy-stage predictions, not predicted NEW/UPDATED counters. It is the validation command to use before the first live run; an orchestrator dry-run or business backfill is not a substitute.

## 9. Deployment requirements — operator actions only

Use authenticated Render shell access or a trusted administrative environment connected to the intended production service. Do not paste database URLs, credentials, tokens, or full environment dumps into chat.

1. Verify the backend checkout contains this implementation. Privately verify the service's configured database identity and inspect its migration revision. Local Neon state is not production evidence.
2. Capture a normal database backup through your existing database administration process. Keep Radar launches paused during the migration/deployment operation.
3. From the backend working directory, inspect the current revision:

   ```sh
   python -m flask --app wsgi db current
   ```

4. If production is at the expected parent `a1b2c3d4e5f6`, apply the new migration before allowing a run:

   ```sh
   python -m flask --app wsgi db upgrade e7c91b2486af
   python -m flask --app wsgi db current
   ```

   If production is on a different historical revision, review the intervening migrations first; the no-data-processing description here concerns this new migration. If already on `e7c91b2486af`, do not downgrade or reset it.
5. Verify the actual resolved runtime mode without launching a run:

   ```sh
   python -c "from app import create_app; a=create_app(); print(a.config['RADAR1_DISCOVERY_MODE']); print(a.config.get('RADAR1_DISCOVERY_MODE_SOURCE'))"
   ```

   It must be `pmmp_index` to use the new queue. The code default remains `legacy`. An operator must correct Render's environment if necessary; this task changed no Render setting. Reconciliation defaults to 24 hours. Existing normal-run paid-resolution/AI settings still apply; preview always disables them.
6. Confirm index existence/count and initial ledger counts using SELECT-only access. Run the preview if desired. Do not run business backfill or pre-launch a normal Radar run to validate deployment.
7. Ensure the Render worker process remains available for the longer board walk. The existing job runner remains an in-process executor, not an external durable worker. Restart recovery preserves queued work, but a dead run can remain active until the configured stale-run timeout (default 120 minutes) permits another launch. No new scheduler was installed.

Read-only database check **after** migration:

```sql
BEGIN READ ONLY;
SELECT version_num FROM alembic_version;
SELECT count(*) AS total,
       count(*) FILTER (WHERE processing_state IS NULL) AS legacy_unclassified,
       count(*) FILTER (WHERE processing_state = 'PENDING_PROCESSING') AS pending,
       count(*) FILTER (WHERE processing_state = 'PROCESSING') AS processing,
       count(*) FILTER (WHERE processing_state = 'FAILED_RETRYABLE') AS retryable,
       count(*) FILTER (WHERE processing_state = 'PROCESSED') AS processed,
       count(*) FILTER (WHERE processing_state = 'REJECTED') AS rejected
FROM pmmp_listing_index;
COMMIT;
```

If the production index is empty, the existing baseline guard will report `pmmp_index_empty_run_baseline_first`. An operator must first perform a listing-only baseline import:

```sh
python -m flask --app wsgi radar1-pmmp-baseline
```

That command writes the technical index but creates no business result/SearchRun and leaves business work pending. It is unnecessary when the index already exists. It was not executed by this task. Do not use `radar1-pmmp-backfill` as a deployment test.

## 10. First real manual Radar 1 test

After the deployment/migration/mode checks above:

1. Open `https://radar-strategique.vercel.app`, sign in, and open Radar 1 / Marchés. Confirm the frontend is using the intended Render service.
2. Optionally run `radar1-preview` from the authenticated backend environment. Its source remains read-only and its output is an offline prediction.
3. Record initial production ledger counts and existing pending/approved/rejected counts. Confirm no other Radar 1 run is active. Do not alter individual entries or reset business history.
4. Click **Lancer une recherche** once. This is the first real run; the user performs it. Record the returned SearchRun ID. The complete board walk can take substantially longer than the old three-page stop.
5. After completion, inspect the authenticated `GET /api/runs/<id>` payload. Check actual `discovery_mode=pmmp_index`, strategy, sync completion/stop reason/pages, declared board count versus observed unique rows, source errors, recovery counts, evaluated count, cap truncation, and NEW/UPDATED/UNCHANGED outcomes. A failed/incomplete collection is not a healthy zero-result run.
6. Open **À traiter → Cette recherche** for that exact run. Actionable persisted manual-review NEW/UPDATED cards should appear. Compare **Tous à traiter**, **Validés**, and **Rejetés** separately; an unchanged rediscovery or approved historical card does not become a new pending card.
7. Re-read final ledger counts. Overflow/retryable rows must remain available. If work remains and no run is active, launch a second manual run to confirm resume behavior; distinguish that follow-up from the first test.
8. Verify genuinely new relevant references from that board walk against the index, processing reason/fingerprint, business row and observation. Existing opportunities can legitimately be UNCHANGED or already approved. Success requires complete discovery evidence, durable processing and correct visibility, not an artificially nonzero NEW/UPDATED counter.

The implementation is ready for these operator steps. Production migration, deployed commit, actual mode, database identity and eventual live behavior still require production access and the user's manual test.
