# Radar 1 scope restore report

**Date:** 2026-09-23

**Goal:** Return Radar 1 to the approved ARCHERITAGE business scope — heritage, architectural competitions, and major/strategic architecture only. Ordinary études architecturales must not fill the queue.

**Constraints respected:** no architecture redesign, no PMMP/persistence/Telegram changes, no migration.

Evidence: `docs/historical/audits/radar1-scope-restore-replay.json`

---

## 1. Previous approved Radar 1 scope

ARCHERITAGE opportunities where the firm can act as architect / BE / MOE / AMO / heritage consultant **and** the project belongs to one of:

| Track | Category | Meaning |
|---|---|---|
| A | `P1_HERITAGE` | Patrimoine bâti / culturel / médina / monuments / restauration–conservation studies |
| B | `P1_CONCOURS` | Concours / consultation architecturale / verified competition procedure |
| C | `P1_MAJOR_ARCH` | Major / strategic public architecture (museum, campus, siège, corniche, verified high estimate) |

P2_REVIEW is reserved for **plausible** major/heritage-adjacent ambiguity — not a dump for generic schools or staff housing.

---

## 2. Heritage rules

- Primary track: built heritage, old fabric (médina, centre historique), monuments, remparts, kasbah/ksar, religious historic fabric, archaeological sites, patrimonial valorisation / conservation / restauration studies.
- Clear patrimonial **études / diagnostics / plans** → `P1_HERITAGE`.
- Soft adjacency (e.g. bare “valorisation du patrimoine culturel” without study framing, espaces publics de médina) → `P2_REVIEW`.
- Architectural study **in médina fabric** is not killed by ordinary “école” generic-work noise.

---

## 3. Competition rules

Accept:

- `concours architectural` / concours de conception
- `consultation architecturale`
- `procedure_type='competition'` with architectural scope

These do **not** require heritage context.

---

## 4. Major architecture rules

- Existing major assets / scale signals preserved.
- `MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD = 20_000_000` preserved.
- Verified estimate ≥ threshold supports `P1_MAJOR_ARCH` with architecture + major asset.
- Plausible major asset without verified scale → `P2_REVIEW` (MAJOR_ARCH track only).
- Budget alone cannot rescue ordinary infrastructure.
- Routine blockers expanded carefully: ordinary lycée / collège / école / logement de fonction / etc. block major promotion.

---

## 5. Generic architecture rejection

New reason: `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC`

Architectural role wording (`études architecturales`, `conception architecturale`, `mission d’architecte`, …) proves **role only**.

Without heritage / competition / major → **reject**.

Examples now rejected:

- lycée / collège architectural studies
- logement de fonction
- ordinary écoles / petites constructions
- bare “études architecturales” with no project family

---

## 6. Infrastructure rejection

Unchanged intent: `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` for voirie / rues / assainissement / réseaux / ordinary road engineering.

**Exception:** heritage urban fabric (e.g. réhabilitation des espaces et voies de l’ancienne médina) is not rejected merely because “voies/rues” appear.

---

## 7. Pure works rule

Unchanged: execution-only travaux → `REJECT_PURE_EXECUTION`.

Professional études / suivi / maîtrise d’œuvre on heritage assets remain eligible.

---

## 8. Latest-result replay (run #30 titles, offline)

| Metric | Count |
|---|---:|
| Trace rows | 100 |
| Kept under restored scope | 4 |
| `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | 14 |

Kept (with prior competition tagging where present): concours / competition-procedure architectural offers (ISTA, Corniche, Concours annexe, Logements tagged competition in live PMMP).

Removed from actionable path: ordinary lycées, logements de fonction, maisons de jeunes, chartes architecturales ordinaires, and similar generic études architecturales.

Listing-stage deferral to PMMP detail is **preserved** for architectural-role titles (including generic rejects), so detail can still uncover competition / heritage / major evidence before the **final** decision.

---

## 9. Results kept

- Heritage professional services (médina, patrimoine culturel études, monuments with study/MOE framing)
- Architectural competitions / consultations
- Major/strategic architecture (verified high estimate or clear major asset/scale)

---

## 10. Results removed

- Ordinary lycée / école / logement de fonction architectural packages
- Generic small administrative / commercial architectural studies without major/heritage/competition
- Ordinary voirie / assainissement / rues studies
- Pure restoration travaux

---

## 11. Tests passed

**775 passed** (`pytest -q`)

Added/updated regressions in:

- `tests/modules/radar1/test_radar1_architectural_scope_fix.py` (required cases 1–10)
- heritage / major / market_relevance / queue uniqueness / phase3 expectations aligned with restored scope

Preserved persistence / PMMP enrichment tests (no regression of 65536 metadata fix).

---

## 12. Alembic state

```
db current = f19a7c4d2e61 (head)
db heads   = f19a7c4d2e61 (head)
```

**No migration created.**

---

## Acceptance

Radar 1 actionable results focus on:

1. patrimoine / restoration / conservation / valorisation  
2. architectural competitions  
3. major/strategic architectural projects  

and are **not** filled with ordinary streets/roads, generic small architectural studies, ordinary schools, or staff residences.
