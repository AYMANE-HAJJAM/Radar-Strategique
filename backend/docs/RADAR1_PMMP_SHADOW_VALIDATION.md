# Radar 1 PMMP shadow validation

**Date:** 2026-10-02  
**Command:** `flask radar1-pmmp-shadow-compare` (default **zero-paid** mode)  
**Production flag:** unchanged — `RADAR1_DISCOVERY_MODE=legacy`  
**Business results written:** no (`results` stayed at **62**)  
**Index committed:** no (session rolled back; index stayed at **3,837**)  
**Paid search / AI calls:** **0**

### Preflight note on paid search

The original shadow helper would have called paid search through `legacy_discovery` → `provider.search` (and possibly resolution `_lookup`). Per the validation rules, that path was **not** used.

The CLI now defaults to forbidding paid calls: discovery/resolution budgets are zeroed and `provider.search` is guarded. Legacy therefore ran as **direct HTTP discovery only** (PMMP keyword pages + Marché Facile). That is stricter than production legacy (which also uses paid keyword search). The PMMP incremental path and ARCHERITAGE evaluation below did not need paid search.

---

## 1. Legacy discovery (direct-HTTP only, zero paid)

| Measure | Value |
|---|---|
| Elapsed | **167.8 s** |
| Total kept candidates (after policy) | **0** |
| PMMP observations seen | **82** |
| Marché Facile observations seen | **18** |
| Institutional observations | **0** |
| Search / discovery / resolution paid calls | **0 / 0 / 0** |
| Health | `DEGRADED` (`NOT_RELEVANT_INDIVIDUAL_PROCUREMENT`) |
| Truncation | `candidate_limit`, `discovery_query_limit` |

Exact relevant survivors after current Radar 1 policy: **none** in this zero-paid direct window.

Closest rejects (architectural / near-scope titles that still failed final policy):

| Reference | Title (short) | Reason code |
|---|---|---|
| 27/2026/BR | Étude architecturale et suivi… salle Kindy Ben M’Sick | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 26/2026/BR | Étude architecturale et suivi… salle Sbata | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 06/2026/CA/BR/RGON | Concours architectural… annexe siège Région Guelmim | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 06/2026 | Concours architectural… siège DRE Laâyoune | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| TC2130522/2026/ONEEBELEC | Études et conceptions architecturales… entrepôt | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| N84/2026/DPAO | Étude architecturale… plateforme produits de terroir | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` |
| CA22/AREFCS/2026 | Études architecturales… lycée Bir Jdid | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` |
| CA02/RRE/2026 | Études urbanistiques et architecturales… parc industriel | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` |

---

## 2. New `pmmp_index` discovery (incremental)

| Measure | Value |
|---|---|
| Pages visited | **3** |
| Listings inspected | **30** |
| NEW | **0** |
| UPDATED | **0** |
| UNCHANGED | **30** |
| Duplicates | **0** |
| Actionable (NEW+UPDATED) | **0** |
| Elapsed | **17.8 s** |
| Stop reason | **`incremental_overlap`** |
| Declared board size | 385 pages / 3,845 results |
| Relevant kept after full downstream policy | **0** (nothing actionable to feed) |
| Paid search calls | **0** |

Zero actionable is **expected** immediately after the phase-3 baseline import: the newest pages are already remembered as UNCHANGED.

---

## 3. Coverage comparison

| Set | Count |
|---|---|
| Discovery overlap (legacy kept keys ∩ PMMP actionable) | **0** |
| Unique to legacy (kept) | **0** |
| Unique to new PMMP actionable | **0** |
| Relevant unique to new path | **0** |
| Relevant unique to legacy | **0** |

Interpretation for this window: both paths kept **zero** final candidates. That does **not** mean the PMMP index cannot discover; it means (a) incremental had no NEW/UPDATED to hand off, and (b) zero-paid legacy direct also kept none under current ARCHERITAGE. Coverage of *memory* vs *live board* is validated by the baseline (3,837 indexed rows) and by the known reference below—not by this quiet incremental delta.

---

## 4. Known reference `04/2026/AUS`

| Check | Result |
|---|---|
| Present in `pmmp_listing_index` | **Yes** (consultation id `1036481`) |
| Title / buyer in index | Étude de valorisation du patrimoine… / Agence urbaine de Settat |
| State in this incremental run | **`UNCHANGED`** (expected after baseline — **not a failure**) |
| Actionable this run | No |
| Cheap listing policy if evaluated | **`keep` / `P1_HERITAGE`** (`ACCEPT_HERITAGE_PROFESSIONAL_SERVICE`) |
| Full downstream pipeline if evaluated (detail HTTP, zero paid) | **Kept** as **`review` / `P2_REVIEW`** (`REVIEW_AMBIGUOUS_RELEVANCE`), `VERIFIED_OFFICIAL` |
| Verified estimate | Not verified (`amount` null) |

Detail enrichment moves the notice from listing-level `keep` to final `review`; it is still accepted into the Radar review path, not rejected.

---

## 5. Incremental performance (critical)

| Measure | Value |
|---|---|
| Pages crawled | **3** |
| HTTP requests | **4** (1 GET form/results + 3 POSTs) |
| Elapsed | **17.8 s** |
| Overlap config | `RADAR1_PMMP_OVERLAP_PAGES=3` |
| Unchanged page streak at stop | **3** |
| Stopped via 3-page unchanged overlap | **Yes** (`stop_reason=incremental_overlap`) |
| Walked all ~384 pages? | **No** |

This is the required behavior for production incremental runs.

---

## 6. Policy sample (new path)

### Accepted / REVIEW from actionable handoff

None — actionable count was 0.

### Force-evaluated known reference (pipeline)

| Field | Value |
|---|---|
| Reference | `04/2026/AUS` |
| Title | Appel d’offres ouvert National n° 04/2026… valorisation du patrimoine culturel, naturel et historique… Settat |
| Buyer | MHUAE / AUS - AGENCE URBAINE DE SETTAT |
| Procedure | tender (listing: Appel d'offres ouvert) |
| Estimate | not verified |
| Classification | `P2_REVIEW` |
| Decision | `review` |
| Reason | `REVIEW_AMBIGUOUS_RELEVANCE` |

### Listing-level policy on the 30 inspected rows (cheap, no detail)

**Accepted / review at listing text only:**

| Reference | Title (short) | Classification | Reason |
|---|---|---|---|
| 06/2026 | Concours architectural… nouveau siège DRE Laâyoune | `P1_CONCOURS` | `ACCEPT_ARCHITECTURAL_COMPETITION` |

Note: the same concours family was rejected in the legacy **full** pipeline after detail enrichment (`REJECT_OUT_OF_SCOPE_INFRASTRUCTURE`). Listing-only keep ≠ final keep; final ARCHERITAGE is unchanged and still applied downstream.

**Closest rejects among inspected listings:**

| Reference | Title (short) | Reason |
|---|---|---|
| 12/2026 | Conception architecturale… centre d’estivage Fondation Mohammadia | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` |
| 01/2026 | Restauration collective… centre protection enfance | `REJECT_PURE_EXECUTION` |
| 66DR6/2026 | Réhabilitation adductions Ville Zaio | `REJECT_PURE_EXECUTION` |
| 48/RH/2026/EXP | Prestation de restauration… internats Rhamna | `REJECT_PURE_EXECUTION` |
| 81/2026/DR9 | Renforcement AEP Melloussa | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 83/2026/DR9 | Equipement forage Nekour (conduites) | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 84/DR9/2026 | Equipement forage Nekour (génie civil) | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` |
| 36/2026/CTSA/F | Tramway T1 titres de transport | `REJECT_NO_ARCHITECTURAL_ROLE` |

---

## 7. Final go / no-go

### **A. READY TO ENABLE `pmmp_index` IN PRODUCTION**

Factual basis:

1. Incremental sync stops after **3 unchanged pages** (~18 s, 4 HTTP) and does **not** walk the full board.
2. Durable index holds the live board memory (**3,837** rows) including **`04/2026/AUS`**.
3. UNCHANGED for AUS after baseline is expected and correct.
4. When AUS is force-fed through the existing downstream path (zero paid), ARCHERITAGE keeps it as **REVIEW** / verified official.
5. Discovery/index layers made **no** paid search or AI calls; no business rows were written; production flag remains **`legacy`**.

Caveats before flipping Render:

- This shadow’s legacy arm was **direct-HTTP only** (paid keyword discovery intentionally blocked).
- A quiet post-baseline incremental (0 actionable) cannot prove NEW-handoff end-to-end; that needs either a later window with real NEW listings or a staging SearchRun after enablement.
- Recommended enablement sequence remains the one in `RADAR1_PMMP_COLLECTOR_PHASE3.md` (staging SearchRun first). **Do not enable the production flag from this document alone without that staging check.**

**Flag not changed.** Production stays `RADAR1_DISCOVERY_MODE=legacy`.
