# Radar 1 PMMP staging SearchRun

**Date:** 2026-10-02  
**Method:** In-process override `RADAR1_DISCOVERY_MODE=pmmp_index` via `scripts/run_radar1_pmmp_staging.py`  
**Database:** local configured PostgreSQL (not Render env change)  
**Paid search / AI:** forbidden and guarded (`provider.search` raises if called); `no_ai=True` on orchestrator  
**Production default after run:** still `legacy`  
**Render environment:** not modified

Companion raw JSON: `docs/RADAR1_PMMP_STAGING_RUN_raw.json` (copied from the staging dump).

---

## 1. SearchRun

| Field | Value |
|---|---|
| Run id | **42** |
| Launched by | **Aymane** (user id `1`) |
| Trigger type | `staging_pmmp_index` |
| Started | 2026-10-02 22:12:14 UTC |
| Finished | 2026-10-02 22:12:57 UTC |
| Wall elapsed | **45.9 s** |
| Final status | **`completed`** |
| Stage | `COMPLETED` |
| Candidates kept by collector | 0 |
| Error | none |

---

## 2. Incremental sync

| Measure | Value |
|---|---|
| Discovery mode (collector metrics) | **`pmmp_index`** |
| Pages visited | **3** |
| HTTP requests | **4** (1 GET + 3 POST) |
| Elapsed (wall for whole SearchRun) | 45.9 s |
| Stop reason | **`incremental_overlap`** |
| NEW | **0** |
| UPDATED | **0** |
| UNCHANGED | **30** |
| Duplicates | 0 |
| Actionable (NEW+UPDATED) | **0** |
| Declared board | 385 pages / 3,848 results |
| Index size before | 3,837 |

Expected quiet window: the durable index was filled by the phase-3 baseline, so the newest pages are already known. The run still exercised the real `MarketsCollector.pmmp_index_discovery` → orchestrator → SearchRun commit path.

Did **not** walk ~384 pages.

---

## 3. Downstream (actionable NEW/UPDATED)

No actionable listings in this run → **no** policy evaluations on a live handoff.

| Actionable listing | Policy outcome |
|---|---|
| *(none)* | — |

Collector health: `DEGRADED` with reason `zero_usable_observations` (expected when actionable is empty; not a crash).

Prior shadow validation already force-evaluated `04/2026/AUS` through the same downstream pipeline as `review` / `P2_REVIEW` / `VERIFIED_OFFICIAL` when present as an index row. That notice remained **UNCHANGED** here and was correctly not re-processed as business work.

---

## 4. Persistence

| Measure | Value |
|---|---|
| Business NEW | **0** |
| Business UPDATED | **0** |
| Business UNCHANGED (duplicate_count) | **0** |
| ResultObservation rows for this run | **0** |
| `results` table before → after | 62 → **62** |
| Observations table before → after | 95 → **95** |
| Index rows before → after | 3,837 → **3,837** (rollback of unchanged-only sync; no net inserts) |
| Duplicate fingerprints in run | **0** |

No duplicate business results. Index rows were not turned into `Result` rows.

---

## 5. Run-scoped UI compatibility

Validated against the same predicates the API uses (`_actionable_states` + PENDING filter):

| Check | Result |
|---|---|
| “Cette recherche” actionable count | **0** |
| Pending rows for this `run_id` | **0** |
| Count matches rows | **Yes** (0 = 0) |
| Only this SearchRun’s NEW/UPDATED appear in run scope | **Yes** (empty set; no bleed from other runs) |
| “Tous à traiter” pending before → after | **39 → 39** (independent; unchanged) |
| `pmmp_listing_index` exposed as UI results | **No** (0) |

Frontend does not need to know discovery mode; SearchRun #42 is a normal completed run.

---

## 6. Cost

| Check | Result |
|---|---|
| Paid search attempts (guard) | **0** |
| `SearchRun.search_calls` | **0** |
| `SearchRun.resolution_search_calls` | **0** |
| `SearchRun.ai_calls` | **0** |
| Billable discovery query metrics | **false** |
| Downstream paid call | **None occurred** |

Discovery/index layer remained zero-paid / zero-AI. Resolution paid fallback did not run (budgets zeroed; no actionable detail path needed).

---

## 7. Safety

| Check | Result |
|---|---|
| Process override for this run | `pmmp_index` |
| Default `create_app()` mode after run | **`legacy`** |
| `.env` / Render changed | **No** |
| Legacy discovery deleted | **No** |
| Marché Facile removed | **No** |
| ARCHERITAGE policy changed | **No** |

---

## Final verdict

### **A. STAGING PASS — safe to enable `pmmp_index` on Render**

Evidence:

1. Real SearchRun **#42** completed with attribution (`launched_by=Aymane`), timestamps, and stage lifecycle.
2. Incremental sync used `pmmp_index`, stopped on **3-page unchanged overlap**, 4 HTTP requests — not a full-board crawl.
3. Zero paid/AI calls; no business duplicates; UI run-scope and open queue behave correctly.
4. Production default remains **`legacy`**; Render untouched.

**Enablement caveat:** this staging window had **0 NEW/UPDATED** (expected after baseline). It proves the SearchRun lifecycle and incremental performance under `pmmp_index`. The first production day after enablement should be watched for the first non-zero actionable handoff. Rollback remains: set `RADAR1_DISCOVERY_MODE=legacy` on Render (no code deploy required).

### Suggested Render enablement (manual, not done here)

1. Confirm production Alembic head `a1b2c3d4e5f6` and a populated `pmmp_listing_index` (or run baseline once against production).
2. Set `RADAR1_DISCOVERY_MODE=pmmp_index` on Render only.
3. Launch one manual Radar 1 search from the web UI; confirm SearchRun metrics `discovery_mode=pmmp_index` and incremental stop reason.
4. If anything regresses, set the flag back to `legacy`.
