# Radar 1 — Relevance, PMMP Detail Enrichment & Adaptive Feedback

## 1. Previous Radar 1 weakness

Professional-service phrases such as **« études »** and **« suivi des travaux »** could unlock the pure-execution gate even when the underlying object was ordinary **voirie / assainissement / réseaux**.

ARCHERITAGE needs a **role fit** (can we act as architect / BE / MOE / heritage study?) **and** a **domain fit** (heritage or architectural subject). Role alone is not enough.

## 2. New decision model

Hard policy order in `evaluate_relevance`:

1. Pure execution → `REJECT_PURE_EXECUTION`
2. Irrelevant goods / asset-management noise → `REJECT_IRRELEVANT_DOMAIN`
3. Out-of-scope infrastructure (no heritage/arch context) → `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE`
4. Heritage / patrimonial mission → `P1_HERITAGE` / `P2_REVIEW`
5. Architectural competition → `P1_CONCOURS`
6. Non-heritage tracks without professional role → `REJECT_NO_ARCHITECTURAL_ROLE`
7. Major architectural service → `P1_MAJOR_ARCH` / `P2_REVIEW`
8. Else → `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT`

Named predicates: `is_pure_execution`, `has_professional_service_role`, `has_heritage_context`, `is_out_of_scope_infrastructure`, `is_architectural_competition`, `is_major_architectural_service`, `preliminary_plausible`.

## 3. Role-fit rules

Valid when title/scope hits professional-service language (études, diagnostic, MOE, AMO, suivi des travaux, concours architectural, plan de sauvegarde, …).

Necessary for major-architecture track; heritage track can still qualify on domain (existing P2 adjacent cases preserved).

## 4. Domain-fit rules

Positive: built heritage, médina / centre historique, monuments, remparts, kasbah/ksar, restoration/conservation studies, architectural design/competition, major public architectural facilities.

## 5. Negative infrastructure rules

Expanded `INFRASTRUCTURE_ONLY` (voirie, assainissement, chaussée, VRD, réseaux, éclairage public, parking, drainage, …).

**Reject** études+suivi on ordinary roads/networks without heritage/architecture context.

**Keep** études+suivi + ancienne médina / remparts / patrimoine bâti.

## 6. PMMP detail extraction architecture

Pipeline:

listing → `preliminary_plausible` → identity dedup → `enrich_detail` (GET HTML, no browser automation) → structured `metadata.pmmp` → hard policy → adaptive feedback → validate → persist.

Detail fetch uses existing `AccessLimitedPages` cache (one GET per URL per run; 429 freezes host).

## 7. Exact fields parsed

Reference, objet, acheteur, type d’annonce, procédure, catégorie, allotissement, lieu d’exécution, estimation (amount/currency/TTC|HT), deadline date+time, caution provisoire, domaines d’activité, réservé TPE/PME, retrait/dépôt, ouverture des plis, prix des plans, qualifications, document types (DCE/CPS/RC/BPU/DQE/plans/annexes), official URL.

Stored under `radar_metadata.pmmp` (JSON, **no migration**). Flat estimate/caution fields remain for cards/workflow.

## 8. Example — ancienne médina de Guelmim

`REALISATION DES ETUDES ET SUIVI DES TRAVAUX DE REHABILITATION DE L’ANCIENNE MEDINA DE LA VILLE DE GUELMIM`

→ role fit + heritage domain → **`P1_HERITAGE` / `ACCEPT_HERITAGE_PROFESSIONAL_SERVICE`**.

## 9. Estimate vs caution

Labelled parsers remain separate. Fixture **3 552 000 MAD** estimate vs **70 000 MAD** caution never cross-maps (regression tests).

## 10. Adaptive feedback design

`Radar1FeedbackService`:

- Builds feature frequencies from Radar 1 `APPROVED` / `REJECTED` history (local DB only).
- Weighted overlap score with minimum support (**3** reviews per feature).
- Mixed evidence is dampened; never auto-promotes to P1.
- May soft-demote hard `keep` → `review` on strong negative consensus.
- Hard `reject` always unchanged.
- Profile invalidated after human `decide()` on Radar 1.

## 11. Why no black-box ML

Small review set → overfit risk, poor auditability. Deterministic features stay explainable and free.

## 12. How approved history affects future results

Recurring heritage/architecture/professional features increase `feedback_score` and appear in `nearest_positive_patterns` (audit metadata). Does not force accept of hard rejects.

## 13. How rejected history affects future results

Recurring infrastructure/noise features lower score; can demote borderline keeps to human review. Does not hard-reject strong verified heritage professional services solely from feedback.

## 14. Hard-rule precedence

`hard_decision == 'reject'` → feedback `applied: hard_reject_unchanged`.

## 15. Cost impact

- Adaptive scoring: **0** OpenAI / web-search / HTTP calls.
- Preliminary filter avoids detail GETs for obvious goods/IT/pure works.
- Plausible PMMP candidates still fetch detail **once** (cache).

## 16. PMMP fetch impact

Irrelevant listings: no detail fetch. Plausible: one enrich. Same URL in-run: cache hit.

## 17. R2–5 cleanup command

```bash
flask --app app:create_app cleanup-test-radar-data --radars 2,3,4,5 --dry-run
flask --app app:create_app cleanup-test-radar-data --radars 2,3,4,5 --confirm
```

Shows counts, writes backup JSON, deletes only selected R2–5 business rows. **Radar 1 preserved.** Not executed automatically.

## 18. Files changed

| File | Role |
|------|------|
| `app/collectors/markets/policy.py` | Role+domain decision model, reason codes, predicates |
| `app/collectors/markets/pages.py` | Extra PMMP labels, `build_pmmp_detail`, enrich metadata |
| `app/collectors/markets/collector.py` | Preliminary filter, enrichment logging, feedback apply |
| `app/services/radar1_feedback_service.py` | Adaptive local feedback |
| `app/services/result_review_service.py` | Card PMMP fields; invalidate feedback on decide |
| `app/bot/presenters/result_presenter.py` | Richer DB-only details |
| `app/agents/radars/markets/schemas.py` | Persist pmmp/business_relevance in radar_fields |
| `app/domain/markets/relevance.py` | Façade exports |
| `app/cli.py` / `app/cli_cleanup.py` | Cleanup command |
| `docs/architecture/ARCHITECTURE.md` | Pipeline + CLI notes |
| `tests/test_radar1_role_domain_relevance.py` | Role/domain regressions |
| `tests/test_pmmp_detail_enrichment.py` | Parser + estimate/caution |
| `tests/test_radar1_adaptive_feedback.py` | Feedback + hard override + zero paid |
| `tests/test_pmmp_fetch_gating.py` | Preliminary + cache |

## 19. Tests added

- Role/domain relevance (Guelmim keep; voirie/assainissement reject; pure works reject; concours/major)
- PMMP structured parse + estimate≠caution + enrich metadata
- Adaptive feedback positive/negative/mixed + hard override + zero HTTP
- Fetch gating / page cache

## 20. Total tests passed

**729 passed** (full pytest).

## 21. Alembic state

`current == head == f19a7c4d2e61`

## 22. Migration created?

**NO**

## 23. Remaining limitations

- Heritage P2 adjacent titles without explicit « étude » still allowed (product choice for ambiguous patrimonial missions).
- Feedback soft-demote is conservative; never auto-approves.
- PMMP collapsed « + » UI: relies on HTML already present in the GET response (no browser automation).
- R2–5 cleanup backup is count-level metadata; use DB snapshots for full restore.
- Adaptive profile is in-process; multi-worker deployments rebuild on invalidate/miss (correctness over shared cache).

---

**Acceptance:** ordinary infrastructure études+suivi rejected; heritage/architecture professional services kept; Guelmim médina eligible; PMMP detail structured before final classification; estimate≠caution; Details DB-only; local explainable feedback; hard rules win; 0 paid feedback calls; Radar 1 preserved; R2–5 cleanup opt-in only; no migration; architecture unchanged.
