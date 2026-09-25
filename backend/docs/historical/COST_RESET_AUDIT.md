# Cost audit and safe radar data reset — 11 September 2026

Both requested tasks are complete. The configured PostgreSQL business data was backed up, cleared in one transaction, and checked again afterward. No production radar search was launched. Each of the five live discovery dry-runs ran **before the reset**, in a disposable local database, using the configured discovery budgets and with classification disabled.

## A. Measured cost and usage

### Passive actions

Each row below has **0 direct source HTTP fetches, 0 paid search requests, 0 OpenAI API calls, 0 classification calls, 0 input tokens, 0 output tokens, and 0 other billable provider calls**. No model was used.

| Independently exercised scenario | Result |
|---|---|
| `run_bot.main()` startup and 300-second idle polling lifecycle | Zero paid/network-source usage; 300.327 seconds measured |
| `/start` and all five radar menus | Zero |
| À traiter, all five radars | Zero |
| Validés, all five radars | Zero |
| Rejetés, all five radars | Zero |
| Details of stored results, all five radars | Zero |
| Validate stored results, all five radars | Zero |
| Reject stored results, all five radars | Zero |

**Measurement boundary:** the 300-second test used the real Application lifecycle, polling code, handlers and isolated stored fixtures, with a simulated Telegram HTTP transport. Every non-Telegram HTTP attempt was blocked and would fail the audit. Telegram replies in navigation tests were simulated; nothing was sent to users. This is not a claim of five minutes of live Telegram polling. A separate post-reset check used the real Telegram API: initialization and `Application.start()` succeeded, with exactly one `getMe`, zero paid calls and zero messages. It did not consume updates and shut down afterward. PostgreSQL reads are separate from direct source HTTP fetches; this audit does not measure database-hosting charges.

Evidence: [passive usage](audit-output/passive-usage.json), [clean start](audit-output/clean-start.json), [reproducible harness](scripts/audit_passive_usage.py).

### One isolated live dry-run per radar

| Radar | Direct HTTP attempts | Paid discovery requests | Paid resolution requests | OpenAI API requests | Web-search tool calls | Classification | Input tokens | Output tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 — Markets | 52 | 0 | 5 | 5 | 7 | 0 | 26,226 | 384 |
| 2 — Projects | 2 | 6 | 0 | 6 | 11 | 0 | 71,459 | 1,310 |
| 3 — Institutions | 1 | 5 | 0 | 5 | 5 | 0 | 65,207 | 4,607 |
| 4 — Policies | 2 | 5 | 0 | 5 | 6 | 0 | 57,422 | 3,495 |
| 5 — Funding | 2 | 6 | 0 | 6 | 9 | 0 | 79,275 | 7,824 |
| **Total** | **59** | **22** | **5** | **27** | **38** | **0** | **299,589** | **17,620** |

The reported model was **`gpt-5.6-luna` for all five**. All returned search usage was available. Other billable provider calls: **0**. No dollar estimate was made. Direct attempts include failed HTTP requests and redirect hops; cache hits do not add a request.

Discovery uses OpenAI Responses with web search and factual extraction. Therefore “dry-run” means no classification and no Result writes, **not free search**. Search requests, OpenAI requests and web-search tool calls are overlapping views of the same work; do not add these columns as independent API requests. Classification tokens were zero in every dry-run. The input/output counts above belong to search/extraction.

All five dry-runs completed. Radar 1 reported PARTIAL health (`official_verification_pending`), with 20 candidates; Radars 2–5 reported HEALTHY with 1, 4, 3 and 17 candidates respectively. This audit does not certify those candidates as fully verified offers. The next production searches remain a user decision.

Evidence: [combined measured usage](audit-output/measured-radar-usage.json), raw reports [1](audit-output/radar1.json), [2](audit-output/radar2.json), [3](audit-output/radar3.json), [4](audit-output/radar4.json), [5](audit-output/radar5.json).

Reproduce an individual measurement explicitly:

```powershell
.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --report-json audit-output/new-radar1.json
```

This command makes billable discovery calls. Do not use it merely to check startup.

### Historical development usage attribution

The preserved production history contains ten Radar 1 runs, all marked `telegram`: nine completed and one failed. Its recorded totals are **1,236,379 input tokens and 65,668 output tokens**. These combine discovery and classification; the old data does not provide a reliable per-category token split.

The legacy `ai_calls` total of **152** includes **116 discovery/resolution OpenAI requests plus 36 classification calls**. Search metadata also records **194 web-search tool calls**; `analyzed_count` and per-run `analysis_calls` support the 36 classification total. The newer top-level `search_calls` and `direct_fetches` columns were zero in those old records and are not valid evidence of no search or HTTP traffic. The exact historical discovery/resolution split cannot be reconstructed for every run.

The workspace also contains prior live-development JSON reports and explicit diagnostic entry points: `scripts.check_openai`, `flask test-openai`, and `scripts.test_agent --real-ai`. Running them uses the application API key even when initiated while developing in Codex. They do not run on import or startup. Existing reports may overlap other saved evidence, so they were not blindly summed into the production history.

Codex's own development-model usage is outside this application's telemetry. No account-wide provider billing ledger was available here, so an exact reconciliation of all past development charges is not claimed. The app evidence establishes real radar searches, explicit development searches and classification as usage sources. No scheduler or hidden/background paid-call path was found.

Historical evidence was exported before deletion to [production-before.json](audit-output/production-before.json) and is also in the backup.

### Safeguards checked and fixes applied

- Startup only constructs the app, handlers and job runner. Idle has no scheduled radar or model task. Menu/queue/Details/review paths use stored data and formatting only. No passive-action cost bug was found.
- Rapid duplicate callbacks are debounced. Reservations reject an active run, the database partial unique index enforces one active run per radar, and conditional claim prevents executing the same run twice. Existing tests cover these safeguards. Pressing Search again after a completed run is a new explicit research action.
- Every collector prefers direct-source parsing before paid discovery. Deterministic validation and deduplication precede classification; known unchanged results skip AI. All-five-radar post-reset fixtures verify first discovery followed by unchanged rediscovery without AI.
- **Fixed Radars 2–5 accounting:** search attempts are counted before I/O; failed searches retain returned token/tool usage. Radar 2 failed resolution attempts now consume their resolution budget instead of permitting additional uncounted attempts.
- **Fixed direct HTTP accounting:** `PublicPages` counts requests at the network boundary, including errors and redirects; persisted usage uses this count instead of source/page-success proxies.
- Added search model and usage-completeness metadata, classification model/completeness metadata, and direct/search/resolution counters to the structured run summary. Unknown usage stays explicitly incomplete; a timeout without returned usage is not asserted to be free.
- Fixed `scripts.usage_audit`: its previous keyword expansion into `print` failed, and its ratio added resolution calls to a search total that already included them.

Approved relevance, eligibility, freshness, ranking and human review logic were not changed. The reset also removes the old daily-usage history used by existing caps; it does not erase provider billing. The archived usage remains available in the snapshot.

## B. Safe business-data reset

The live schema was inspected before deletion. These are the actual committed counts:

| Table | Before | After | Action |
|---|---:|---:|---|
| result_observations | 114 | 0 | Cleared |
| market_reviews | 0 | 0 | Cleared |
| result_audit_events | 101 | 0 | Cleared |
| results | 99 | 0 | Cleared |
| search_runs | 10 | 0 | Cleared |
| radars | 5 | 5 | Preserved, including definitions and active flags |
| alembic_version | 1 | 1 | Preserved |

Result metadata, review decisions, fingerprint memory and queue contents live in the deleted Result/review rows. Learned query-performance history lives in SearchRun metadata and is reset with those runs. **Resetting that learned history is appropriate for the requested first-discovery state**; structural query settings and source strategies remain intact. There are no separate persistent source-cache/user/settings tables in the inspected schema. Source-page caches are per-collector memory; production workers were not running during the reset.

Authorization remains in configuration, with one configured authorized Telegram user. `.env`, model/source/radar settings and migration file hashes match before/after. No tables were dropped, no migration ran, no schema object was intentionally changed, and no sequence was reset. Keeping sequence positions also avoids reusing old result IDs in stale Telegram buttons.

### Backup and transaction

Backup: [radar-data-20260911T094159639857Z.json](backups/radar-data-20260911T094159639857Z.json)

SHA-256: `78fd12cd0fc8314e301b637662ffea562d080e853e7184b0c38d37a9c15305e8`

The snapshot exports all rows from all seven tables, with typed dates/decimals/JSON, table counts, columns and foreign keys. It is a data backup for restoration into the preserved schema, not a standalone PostgreSQL schema dump. It was flushed to disk, reread and checksum-verified before any DELETE. A matching `.sha256` file is stored beside it. Backups and raw audit output are excluded from version control.

The reset locks tables against concurrent writes, refuses a non-stale active run or an unreviewed dependent table, deletes child rows before parents, verifies empty targets and unchanged preserved rows, and commits once. Any error inside that transaction rolls back all deletes. Backup failure prevents deletion. The snapshot remains available even after a rollback.

[Reset implementation](scripts/reset_radar_data.py), [committed reset report](audit-output/reset-report.json).

```powershell
# Preview only; prints exact target/preserved row counts and deletes nothing
.venv\Scripts\python.exe -m scripts.reset_radar_data

# Explicit backup + transactional reset (already executed for this task)
.venv\Scripts\python.exe -m scripts.reset_radar_data --confirm

# Optional rollback into the same preserved schema; NOT executed on production
.venv\Scripts\python.exe -m scripts.reset_radar_data --restore backups\radar-data-20260911T094159639857Z.json --confirm
```

Restore verifies the checksum and preserved rows, requires empty business tables, and refuses to overwrite new discoveries. Do not restore the test dataset unless you intentionally want it back.

## C. Clean start and validation

- All **15** pending/approved/rejected queues are empty.
- SearchRun history and all five business tables are empty; therefore no result-linked orphan rows remain.
- All five radar definitions remain active; the migration record and authorization settings remain present.
- Real Telegram initialization and Application startup succeeded, with **zero OpenAI/search/token usage**. The verification stopped the application afterward; it did not leave a production bot polling.
- Isolated tests verify all five radars can create a fresh NEW result after reset, then recognize an unchanged rediscovery without AI. This is fixture verification, not a claim that a post-reset production search has occurred.
- No full production search ran after reset. Current open-tender discovery and resulting production NEW records will be verified when the user chooses the next real search. Radar 1's dry-run verification limitation is stated above.

The full suite passed **336 tests**. A subsequent targeted run passed **5 reset tests** and covers the reset command's final error-reporting refinement and an additional stale-run reset test; see [final reset test output](audit-output/reset-tests-final.txt). Tests cover preserved radar definitions/schema/authorization, empty results/runs/queues, foreign keys, rollback after a mid-delete error, snapshot restore, refusal to overwrite, active-run protection, stale-run cleanup, unknown dependent tables, failed-call accounting and all-five-radar clean discovery/unchanged behavior.

[Full test output](audit-output/test-results.txt), [reset tests](tests/test_reset_radar_data.py), [usage-accounting tests](tests/test_usage_accounting.py), [post-reset verification](audit-output/clean-start.json).
