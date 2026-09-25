# Production engineering audit — 2026-09-10

## Executive assessment

The project has a sound shared pipeline, persistent result memory, append-only lifecycle events, bounded workers, source allowlists, and a database-enforced one-active-run-per-radar invariant. It is suitable for controlled internal operation after applying the migration in this pass. External source coverage remains best effort: public sites can block or change markup, and web-search results are not exhaustive.

## Findings and remediation

### Critical

- Radar 2–4 queue menu callbacks imported their page handler but did not invoke it. Fixed in the central callback router and covered for all five radars.
- A crashed process could leave the partial unique run lock occupied forever. Active runs older than `SEARCH_RUN_STALE_MINUTES` are now atomically marked failed before a new reservation.

### High

- Rapid repeated Telegram callbacks could render duplicate pages. A per-user/action monotonic TTL debounce now makes repeated callbacks one effective action. Search launches also retain the database partial unique index, so independent workers cannot create two active runs for one radar.
- Search requests were counted as generic AI calls. Search, resolution search, direct fetch, and classification calls now have separate persisted counters.
- Radar 3–5 cards used the Radar 1 procurement link resolver and could lose valid official URLs. Non-procurement cards now use their radar metadata/source URL directly.
- Human audit events lacked explicit previous/new review state and radar code. These fields are now appended to every decision event; stale decisions retain compare-and-set protection.
- Radar 4/5 known unchanged records missed early collector dedup. The shared early-memory path now covers every specialized candidate type.
- The live Radar 1 audit exposed false positives caused by geographic `Ksar`, generic `urbanisme`, and water `conservation`. Those words no longer establish architecture scope without an explicit architectural, urban-design, restoration, or heritage intervention.

### Medium

- Queue ordering now explicitly ranks NEW before UPDATED before older lifecycle states, followed by last seen, deadline, priority, and deterministic Result ID.
- HTTP fetch timeout and stale-run timeout are configurable. Source failures remain isolated per URL/source and 429 hosts cool down for the rest of the run.
- Optional company-wide daily search and classification caps fail gracefully and reduce the remaining run budget.
- A single CLI now runs any of the five radars in isolated dry-run mode. A separate usage-audit command reads persisted metrics without network access.
- Classification models can be configured per radar while retaining the existing default.

### Low / documentation debt

- Several Radar 4/5 modules are densely formatted. They are functionally covered but should be reformatted during a future maintenance pass rather than mixed into production behavior changes.
- The generic review service retains its historical `market_review_service` name although it serves all radars.

## Architecture and operational decisions

The queue is company shared. `review_status` belongs to the Result, so a decision by one authorized user is immediately visible to every other user. Telegram session state only tracks presentation. PostgreSQL remains the source of truth.

Discovery lifecycle (`NEW`, `UPDATED`, `UNCHANGED`) stays independent from review lifecycle (`PENDING`, `APPROVED`, `REJECTED`). Deterministic meaningful fields are radar specific. Meaningful changes reopen pending review and append an event; unchanged approved/rejected records retain their decision and skip classification.

The local executor remains intentionally small and non-durable. Database reservation provides cross-process exclusion. Network work occurs after the run is committed and without sharing a SQLAlchemy session across threads; each worker enters its own Flask application context.

## Live isolated validation

All commands used `--dry-run --isolated`; no production Result, observation, review, or run data was written and no Telegram message was sent.

| Radar | Health | Direct fetches | Search requests | Provider web calls | Classification calls | Observations kept | Input/output tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 Markets | PARTIAL | 8 | 5 resolution | 8 | 0 | 18 | 27,607 / 375 |
| 2 Projects | HEALTHY | 2 | 2 | 4 | 0 | 1 | 26,645 / 1,026 |
| 3 Institutions | HEALTHY | 4 institutions checked | 2 | 2 | 0 | 3 | 26,261 / 1,490 |
| 4 Policies | HEALTHY | 1 official source | 2 | 2 | 0 | 4 | 18,088 / 1,505 |
| 5 Funding | HEALTHY | 2 funders checked | 2 | 3 | 0 | 9 | 26,533 / 3,251 |

Radar 1 inspected 82 raw rows, extracted 67 unique tender observations after 15 source duplicates, rejected 49 by business scope, rejected 6 topography-only and 14 technical-only records, verified 9 official links, retained 9 credible fallbacks, and kept 2 heritage opportunities. Its PARTIAL status means nine links still depended on credible secondary evidence. The audit then tightened three observed false-positive patterns, so the recorded 18 is a pre-fix upper bound rather than a claim that every one remains accepted.

Radar 2 produced one concrete but early C-maturity signal from 34 raw results and rejected 33 vague observations. Radar 3 produced three relevant institution profiles but no verified current officeholder in this bounded sample; decision-maker completeness is therefore unproven. Radar 4 separated two laws and two drafts, with reported/unconfirmed legal states left for review. Radar 5 found nine Morocco-related programs; five were monitoring-only/D status and no direct-access claim was made.

Dollar cost is not stated because model-specific token and web-search prices were not configured. Across this validation there were 13 search requests, 19 provider web calls, zero classification calls, 125,134 input tokens, and 7,647 output tokens. Direct HTTP fetches are not paid search calls.

## Validation and limitations

- Offline suite: 326 tests after this pass, including callback debounce, all-radar routing, run locking, authorization, lifecycle memory, stale decisions, pagination, source policy, and deterministic quality gates.
- Compilation and dependency checks pass.
- The existing memory tests prove first save, unchanged second snapshot without repeat classification, meaningful update reopening, and stale concurrent decision rejection using isolated databases. Live dry-run intentionally writes nothing, so a live two-pass persistence claim would contradict dry-run safety.
- Telegram latency is DB and local rendering bound for navigation; handlers offload synchronous DB reads and launch searches in the worker pool. Actual perceived latency still depends on Telegram and PostgreSQL network latency.
- A local SQLite profile with 500 pending rows measured a 20.4 ms mean service-layer page read over 100 iterations. This is comfortably below the one-second UI target; production PostgreSQL and Telegram round trips remain environment dependent.
- Source websites and search-provider availability remain external limitations. Radar 3 current-role coverage and Radar 1 exact-link coverage depend on accessible dated official evidence.

## Production commands

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe -m flask --app run seed-radars
.\.venv\Scripts\python.exe run_bot.py
```

Isolated diagnostics:

```powershell
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_2_PROJECTS --dry-run --isolated
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_3_INSTITUTIONS --dry-run --isolated
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_4_POLICIES --dry-run --isolated
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_5_FUNDING --dry-run --isolated
.\.venv\Scripts\python.exe -m scripts.usage_audit
```

Recommended schedule: Radar 1 daily; Radar 2 three times weekly; Radars 3–5 weekly. Increase Radar 2 around announced programs and Radar 4 after major legislative sessions. This balances source-change frequency with paid search usage.

## Files changed in this pass

- `app/config.py`
- `app/models/search_run.py`
- `app/agents/orchestrator.py`
- `app/services/search_run_service.py`
- `app/services/result_workflow_service.py`
- `app/services/market_review_service.py`
- `app/services/cost_service.py`
- `app/api/routes.py`
- `app/bot/handlers.py`
- `app/collectors/registry.py`
- `app/collectors/markets/pages.py`
- `app/collectors/markets/policy.py`
- Radar 1–5 collector constructors
- `scripts/run_live_radar.py`
- `scripts/usage_audit.py`
- `.env.example`
- `migrations/versions/a91f3d2c4e10_production_run_usage_metrics.py`
- Telegram and Radar 1 relevance tests
