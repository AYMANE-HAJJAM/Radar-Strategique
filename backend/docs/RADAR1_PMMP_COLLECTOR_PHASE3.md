# Radar 1 PMMP collector — phase 3

**Date:** 2026-10-02  
**Scope:** Production integration of the durable PMMP listing index behind `RADAR1_DISCOVERY_MODE`. Default remains `legacy`. ARCHERITAGE final policy, Marché Facile, legacy keyword discovery, Radars 2–5, and the UI are unchanged.

Phase 1 validated the live board crawl. Phase 2 added `pmmp_listing_index` and incremental sync. Phase 3 wires the index into Radar 1 runs when explicitly opted in.

---

## Migration status

| Item | Value |
|---|---|
| Revision | `a1b2c3d4e5f6` |
| Alembic head | `a1b2c3d4e5f6` (confirmed current) |
| Table | `pmmp_listing_index` exists |
| Indexes | `ix_pmmp_listing_index_consultation_id`, `ix_pmmp_listing_index_source_consultation`, `uq_pmmp_listing_index_identity_key`, `uq_pmmp_listing_index_source_consultation` (partial unique where `consultation_id IS NOT NULL`), PK |
| Business data | No existing `results` / observation rows modified by the migration |

No additional migration was required for phase 3.

---

## Baseline import statistics

Command: `flask radar1-pmmp-baseline`  
**When:** 2026-10-02, 20:42–21:26 UTC (local)  
**Board size at crawl:** 384 pages / 3,840 declared results

| Measure | Value |
|---|---|
| Listings collected | **3,840** |
| Unique | **3,837** |
| NEW inserted | **3,837** |
| UPDATED | **0** |
| UNCHANGED | **0** |
| Duplicates | **3** |
| Errors | **0** |
| Pages fetched | **384** (`stop_reason=final_page`) |
| Elapsed time | **2,678.7 s** (~44.6 min) |
| Index rows before → after | 0 → **3,837** |
| Business `results` delta | **0** (62 → 62) |

The baseline establishes discovery memory only. It did **not** create Radar business results.

Known reference `04/2026/AUS` is present in the index (consultation id `1036481`, Agence urbaine de Settat / patrimoine culturel).

---

## Feature flag

```text
RADAR1_DISCOVERY_MODE=legacy|pmmp_index
```

| Value | Behavior |
|---|---|
| `legacy` (default) | Existing keyword discovery + Marché Facile path via `MarketsCollector.legacy_discovery` |
| `pmmp_index` | Incremental PMMP sync → NEW+UPDATED only → existing downstream pipeline |

Invalid values raise at config load. Production Render env is **not** switched in this phase.

---

## New runtime flow (`pmmp_index`)

1. Require a non-empty `pmmp_listing_index` (otherwise warn `pmmp_index_empty_run_baseline_first` and return no candidates).
2. `sync_listings(mode='incremental', commit=False)` against the durable index.
3. Take `result.actionable` only (`NEW` + `UPDATED`).
4. Map each listing with `listing_to_search_hit`.
5. Pass each hit into the existing `_process` path:
   - cheap preliminary / relevance checks
   - official PMMP detail enrichment where required
   - existing ARCHERITAGE final policy (not duplicated)
   - existing dedup
6. Orchestrator persistence produces NEW / UPDATED / UNCHANGED business results as before.

**Not run in this mode:** legacy keyword discovery, Marché Facile, discovery paid search.

---

## SearchRun integration

Discovery mode is an internal collector choice. The orchestrator still:

- creates / updates `SearchRun`
- records `launched_by_user_id`, timestamps, stage history
- counts candidates, NEW, UPDATED, duplicates / UNCHANGED, rejects, errors
- writes `ResultObservation` rows used by “Cette recherche”

The frontend does not need to know which discovery mode ran. Metrics include `discovery_mode` and `pmmp_sync_*` for operators.

---

## Run-scoped results (“Cette recherche”)

Unchanged API contract: with `?run_id=…&status=pending`, only results that have a NEW or UPDATED observation in that SearchRun are returned (`_actionable_states`).

`pmmp_listing_index` is never exposed as UI results. Index rows are not Radar `Result` rows.

---

## Cost behavior

| Layer | Paid search / OpenAI |
|---|---|
| PMMP listing collector + durable index sync | **None** (HTTP to marchespublics.gov.ma only) |
| `pmmp_index` discovery branch | **None** for discovery (`billable_search: False`) |
| Downstream `_process` / official link resolution | Existing `_lookup` may still call the search provider when official confirmation needs identity recovery — same as legacy after a hit is found |

Report for operators: in `pmmp_index` mode, any paid call is a **resolution fallback**, not discovery. Discovery and index layers remain zero-AI / zero-paid-search.

---

## Shadow comparison capability

Safe utilities (do not write duplicate business results):

| Entry | Purpose |
|---|---|
| `app.modules.radar1_markets.shadow_compare.compare_candidate_sets` | Pure set comparison |
| `shadow_compare(collector, radar, …)` | Runs legacy discovery + incremental PMMP actionable set; rolls back index changes by default |
| `flask radar1-pmmp-shadow-compare` | CLI wrapper; may use paid search on the **legacy** side only |

Reports: candidates seen by each path, overlap, unique to each, relevant after policy on the PMMP path, presence of reference `04/2026/AUS`.

Not wired into every production search.

---

## Test results

Focused:

```text
pytest tests/modules/radar1/test_pmmp_phase3_integration.py \
       tests/modules/radar1/test_pmmp_listing_collector.py \
       tests/modules/radar1/test_pmmp_listing_index.py
→ 36 passed
```

Coverage includes: legacy flag behavior, `pmmp_index` path selection, NEW/UPDATED handoff, UNCHANGED skip, empty-index guard, index ≠ UI results, SearchRun attribution fields, run-scoped NEW/UPDATED filter, no duplicate index row, no paid imports in discovery/index modules, Radars 2–5 registry untouched, shadow overlap helper, default mode `legacy`.

Full backend suite:

```text
pytest -q
→ 858 passed in 121.20s
```

Frontend checks: not required (API shape unchanged).

---

## Exact steps to enable production safely

1. Confirm Alembic head is `a1b2c3d4e5f6` on the production database and `pmmp_listing_index` exists.
2. Run a non-destructive baseline once against production (or restore a validated dump into `pmmp_listing_index`):
   ```text
   flask radar1-pmmp-baseline
   ```
   Confirm business `results` count is unchanged and index row count ≈ live board size.
3. Optionally run shadow comparison in a non-production window:
   ```text
   flask radar1-pmmp-shadow-compare
   ```
4. Set Render env **only after** baseline + a dry run in staging:
   ```text
   RADAR1_DISCOVERY_MODE=pmmp_index
   ```
5. Trigger one manual Radar 1 SearchRun; verify SearchRun counts, “Cette recherche”, and that legacy/MF are not used (`discovery_mode=pmmp_index` in metrics).
6. Keep a rollback plan: set `RADAR1_DISCOVERY_MODE=legacy` (no code deploy required).

**Do not** delete legacy discovery or Marché Facile until a later phase.

---

## CLI added

| Command | Effect |
|---|---|
| `flask radar1-pmmp-baseline` | Full crawl → index only |
| `flask radar1-pmmp-shadow-compare` | Legacy vs PMMP candidate comparison; index rollback |
