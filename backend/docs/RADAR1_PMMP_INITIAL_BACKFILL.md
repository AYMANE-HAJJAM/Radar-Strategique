# Radar 1 PMMP initial business backfill

**Date:** 2026-10-02  
**Command:** `flask radar1-pmmp-backfill`  
**Successful SearchRun:** **#45** (`trigger_type=pmmp_index_backfill`)  
**Source:** existing `pmmp_listing_index` rows only — **no PMMP board recrawl**  
**Policy:** existing ARCHERITAGE via `MarketsCollector._process` (no new classifier)  
**AI:** `no_ai=True` on the orchestrator; **0** AI calls  

Companion JSON: `docs/RADAR1_PMMP_INITIAL_BACKFILL_raw.json`

---

## Flow executed

```text
pmmp_listing_index (3,837 rows)
  → cheap_listing_prefilter (preliminary_plausible + infra-without-architecture helpers)
  → listing_to_search_hit
  → MarketsCollector._process (detail enrich + final ARCHERITAGE)
  → AgentOrchestrator normalize / dedup / persist
  → Result + ResultObservation on SearchRun #45
```

Rejected listings stay only in the index. Accepted / review candidates appear in the normal Radar 1 UI (`review_status=PENDING`).

---

## SearchRun #45

| Field | Value |
|---|---|
| Id | **45** |
| Launched by | Aymane (user id 1) |
| Started | 2026-10-02 22:51:04 UTC |
| Finished | 2026-10-02 23:09:07 UTC |
| Elapsed | **1,082.5 s** (~18.0 min) |
| Status | **`completed`** |
| Candidates kept by collector | 10 |

Failed / aborted attempts (no business writes from those attempts that conflict with #45’s persist):

| Run | Status | Note |
|---|---|---|
| #44 | failed (`database`) | Idle-in-transaction timeout during long detail HTTP (before persist) |
| #46 | failed (orphaned) | Accidental duplicate start; stopped immediately after #45 was confirmed complete |

---

## Counts

| Measure | Value |
|---|---|
| Total indexed rows considered | **3,837** |
| Skipped by cheap prefilter | **2,873** |
| Eligible for PMMP detail (prefilter continue + detail URL) | **964** |
| Detail enrichment OK (collector log) | **440** |
| Pipeline verified / kept candidates | **10** |
| Pipeline rejects after entering `_process` (log) | **~948** |
| Accepted (`decision=keep`) persisted | **1** |
| Review (`decision=review`) persisted | **9** |
| Business NEW | **7** |
| Business UPDATED | **3** |
| Business UNCHANGED | **0** |
| ResultObservation rows for #45 | **10** |
| Index rows after backfill | **3,837** (unchanged; nothing deleted) |
| `results` table | 62 → **69** (+7 new rows; 3 updates on existing) |
| Errors (run-level) | none on #45 |
| Paid search calls | **0** |
| AI calls | **0** |

### Prefilter reason breakdown

| Reason | Count |
|---|---|
| `pure_execution_works` | 1,421 |
| `non_architectural_purchase` | 1,205 |
| `infrastructure_without_architecture` | 247 |

---

## Persisted opportunities (SearchRun #45)

All ten are `PENDING` for human review in the Radar 1 UI.

| Ref | Discovery | Decision | Classification | Reason |
|---|---|---|---|---|
| 03/2026 | NEW | review | P2_REVIEW | REVIEW_AMBIGUOUS_RELEVANCE |
| 04/2026/CA/BR/RGON | UPDATED | review | P2_REVIEW | REVIEW_AMBIGUOUS_RELEVANCE |
| 07/2026/DRAI/BH | NEW | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 145/2026 | NEW | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 82/2026/CM | NEW | **keep** | **P1_HERITAGE** | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 36/BR/RGON/2026 | UPDATED | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 43/2026/ADERFES | NEW | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 42/2026/ADERFES | NEW | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| 195/2026/APDN | NEW | review | P2_REVIEW | ACCEPT_HERITAGE_PROFESSIONAL_SERVICE |
| **04/2026/AUS** | **UPDATED** | **review** | **P2_REVIEW** | **REVIEW_AMBIGUOUS_RELEVANCE** |

---

## Known reference `04/2026/AUS`

| Check | Result |
|---|---|
| Processed in backfill | **Yes** |
| Passed cheap prefilter | Yes |
| Final classification | **`P2_REVIEW`** |
| Decision | **`review`** |
| Reason | `REVIEW_AMBIGUOUS_RELEVANCE` |
| Business persistence | **UPDATED** existing result id **132** (not a duplicate insert) |
| UI | Appears under Radar 1 pending / run-scoped “Cette recherche” for SearchRun #45 |

---

## Cost

| Layer | Calls |
|---|---|
| Discovery / index read | 0 paid / 0 AI |
| Detail enrichment | PMMP official HTTP only |
| Paid search | **0** |
| AI classification | **0** (`no_ai=True`) |

---

## Safety / scope

| Check | Result |
|---|---|
| Full PMMP recrawl | **Not run** |
| Index rows deleted | **No** |
| Radars 2–5 | Untouched |
| ARCHERITAGE policy code | Unchanged |
| Dedup against existing Results | Normal path (3 UPDATED) |
| Dedicated SearchRun for audit | **#45** |
| Render production env changed by this backfill | **No** |

Local process config may already have `RADAR1_DISCOVERY_MODE=pmmp_index` from prior staging enablement; this backfill did not write Render settings.

How to re-run (only if needed): `flask radar1-pmmp-backfill`  
Implementation: `app/modules/radar1_markets/pmmp_index_backfill.py` + CLI `radar1-pmmp-backfill`.
