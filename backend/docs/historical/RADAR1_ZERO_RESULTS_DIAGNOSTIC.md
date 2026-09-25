# Radar 1 zero-results diagnostic

**Date:** 2026-09-23

**Scope:** Read-only analysis of persisted `search_runs` / `results` / `collector_trace`. No code changes, no new production search, no OpenAI/external search calls.

**Primary focus run:** `#29` (2026-09-21 15:13 UTC) — exact Telegram counts match the observation (0 new / 0 updated / 1 known / 99 auto-rejects / 0 a traiter).

**Latest run:** `#30` (2026-09-23 09:28 UTC) — same failure mode (0/0/0/100) with 4 collector keeps all lost to `candidate_errors`.

Evidence: `docs/historical/audits/radar1-zero-run-29-detail.json`, `radar1-zero-diagnostic-bundle.json`, `radar1-zero-known-results.json`.

---

## 1. Last-run summary

| Metric | Run #29 (observed) | Run #30 (latest) |
|---|---:|---:|
| Status / health | completed / HEALTHY | completed / HEALTHY |
| Usable discoveries | 100 | 100 |
| Collector relevance rejects | 96 | 96 |
| Collector architecture kept / verified official | 3 / 3 | 4 / 4 |
| Handed to orchestrator | 3 | 4 |
| `candidates_after_rules` | 0 | 0 |
| `candidate_errors_count` | **3** | **4** |
| Nouveaux | 0 | 0 |
| Mis a jour | 0 | 0 |
| Deja connus | 1 | 0 |
| Rejectes automatiquement | 99 | 100 |
| A traiter | 0 | 0 |
| `final_kept` | 0 | 0 |
| AI / paid search calls | 0 / 0 | 0 / 0 |

### Verdict mapping (A/B/C/D)

| Hypothesis | Verdict |
|---|---|
| **A. Market empty** | **No.** Discovery found 100 usable observations; collector itself kept 3-4 strong architectural offers. |
| **B. Filtering too strict (false negatives)** | **Yes (major).** Listing titles with explicit etudes architecturales / heritage-adjacent language are hard-rejected as `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` before PMMP detail enrichment. |
| **C. PMMP enrichment/classification failing before final relevance** | **Partial.** The 96 rejects are listing-only (`official_url` null). The 3-4 keeps did enrich successfully (`verified_offer`). |
| **D. Dedup incorrectly collapsing relevant NEW** | **Secondary.** 1 known (concours) is explainable. The decisive post-collector failure is `candidate_errors` on every kept offer from run #28 onward. |

**Exact arithmetic for run #29:** collector `rejected=96` + orchestrator `candidate_errors=3` -> Telegram Rejectes=99, plus collector early-known concours -> Deja connus=1.

---

## 2. Rejection-reason distribution (run #29)

| Reason code | Count | % of 96 rejects |
|---|---:|---:|
| `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | 25 | 26.0% |
| `REJECT_PURE_EXECUTION` | 24 | 25.0% |
| `REJECT_IRRELEVANT_DOMAIN` | 23 | 24.0% |
| `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | 17 | 17.7% |
| `REJECT_NO_ARCHITECTURAL_ROLE` | 7 | 7.3% |
| `ACCEPT_ARCHITECTURAL_COMPETITION` (kept/known traces) | 4 | n/a |

Legacy rejection_reason mix: `no_heritage_scope` 25, `pure_execution_works` 24, `non_architectural_purchase` 23, `infrastructure_without_architecture` 15, `no_architectural_role` 7, `topography_only` 1, `generic_construction_or_infrastructure` 1.

**Dominant eliminator:** `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` (26%).

---

## 3. Suspicious false negatives

Flagged **20** rejected titles with strong positive lexical signals. Overriding rule is almost always step-8 fallthrough after role-fit succeeds but heritage/competition/major tracks fail.

| Title (truncated) | Positive signals | Overriding reason_code | Notes |
|---|---|---|---|
| La réalisation des prestations de maintenance et de support logiciel du système de gestion du patrimoine fonci | patrimoine | `REJECT_IRRELEVANT_DOMAIN` / `non_architectural_purchase` |  |
| Etudes techniques et du suivi des travaux de la sécurisation de l’ensemble des accès de l’Institut Royal de Po | suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` |  |
| LA RÉALISATION DES ÉTUDES ARCHITECTURALES ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DU SIEGE DE LA CAIDAT TATOFT | etudes architecturales, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etudes architecturales et suivi des travaux de construction du lycée qualifiant ALMARINIAINE à MHAMIDE 10 à la | etudes architecturales, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etudes architecturales et suivi des travaux de construction du LYCEE QUALIFIANT RACHID EL YAZAMI, arrondisseme | etudes architecturales, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE DEMOLITION DE DEUX LOGEMENTS DE FONCTION ET DE RECONSTRUCTION DE  | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE DEMOLITION ET DE RECONSTRUCTION DU LOGEMENT DE FONCTION DU CAID F | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etude architecturale pour l'aménagement d'une fromagerie et 2 unités de trituration des olives au profit des c | etude architecturale | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etude architecturale et le suivi des travaux de construction d’une salle multisports couverte à la commune SID | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etude Architecturale Conception Et Suivi Des Travaux De Construction D’une Maison Du Quartier touhamou A La Co | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| ETUDE ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DES MAGASINS AU SOUK HAD IMOULASS PROVINCE DE TAR | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| Etude architecturale et suivi des travaux de construction d’une unité scolaire à la commune EL MSIED à la prov | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CREATION D’UN ESPACE DE LA MEMOIRE HISTORIQUE DE LA RESISTANCE  | etudes architecturales, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Historical-memory facility; still rejected |
| ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE CONSTRUCTION D’UN NOYAU COLLEGIAL A LA CT ANERGUI DANS LA PROVINC | etude architecturale, suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` | Has ARCHITECTURAL_SCOPE but still no_heritage_scope fallthrough |
| REHABILITATION DES EQUIPEMENTS DE LA STATION DE TRAITEMENT MEKNES (2EME RANCHE) | rehabilitation | `REJECT_PURE_EXECUTION` / `pure_execution_works` |  |
| Mission d’Assistance à la Maîtrise d’Ouvrage pour  le Contrôle et le Suivi des travaux d’élargissement et de r | suivi des travaux | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` / `no_heritage_scope` |  |
| Travaux de renforcement et de réhabilitation de l’avenue Casablanca dans la ville de Larache (Province de Lara | rehabilitation | `REJECT_PURE_EXECUTION` / `pure_execution_works` |  |
| La sécurité, la surveillance et le gardiennage des bâtiments administratifs et monuments historiques relevant  | monument | `REJECT_IRRELEVANT_DOMAIN` / `non_architectural_purchase` |  |
| Aménagement et Gros Travaux de Maintenance des Bâtiments administratifs relevant du territoire de l’Arrondisse | medina | `REJECT_PURE_EXECUTION` / `pure_execution_works` | Medina hit but pure-execution / works path |
| Travaux d’aménagement et de réhabilitation de la maison de la culture à Ksar El Kebir | rehabilitation | `REJECT_PURE_EXECUTION` / `pure_execution_works` |  |

### Policy reproduction (offline, no HTTP)

- Etudes architecturales + suivi des travaux + construction -> `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` even with `ARCHITECTURAL_SCOPE`.
- Same title with `procedure_type='competition'` -> `ACCEPT_ARCHITECTURAL_COMPETITION`.

Ordinary architectural professional services are not a first-class keep track; they often survive only when competition procedure is tagged.

---

## 4. PMMP detail-enrichment success rate (run #29)

| Bucket | Count |
|---|---:|
| Detail enrichment success (`verified_offer`) | 3 |
| Known unchanged | 1 |
| Listing-only classification/reject (`official_url` null) | 96 |
| Detail enrichment failure (`rejected_by_resolution`) | 0 |

**Flag:** 96 candidates rejected from listing titles only. Architectural-service language on the listing never got a detail rescue path.

---

## 5. Preliminary-filter issues

`preliminary_plausible` only hard-rejects NEGATIVE goods/IT and pure execution.

- False-negative etudes carry full `evaluate_relevance` payloads with `ARCHITECTURAL_SCOPE` -> not killed solely by preliminary filter.
- Pure-execution / irrelevant-domain (47 combined) mostly match obvious garbage.
- Borderline: some pure-execution rows mention medina / maison de la culture without study framing — never reach detail.

**Conclusion:** preliminary filter is not the main FN engine; **post-preliminary domain fallthrough (step 8)** is.

---

## 6. Domain-fit precedence findings

Order: pure execution -> unrelated -> infrastructure -> heritage -> concours -> require professional role -> major architecture -> else reject `no_heritage_scope`.

| Should remain eligible | Actual run #29 behavior |
|---|---|
| etudes + suivi + ancienne medina | Not a fresh keep; prior `#138` is human-REJECTED / UNCHANGED |
| etudes architecturales + suivi des travaux | Mass FN via `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` unless competition tagged |
| concours architectural | Kept in collector; one early-known |
| maitrise d oeuvre + patrimoine | Not observed as keep |
| architecture paysagere + conception | Not observed |

**Gap:** `ARCHITECTURAL_SCOPE` + professional role is insufficient without heritage / concours / major asset.

---

## 7. Infrastructure-rule findings

`REJECT_OUT_OF_SCOPE_INFRASTRUCTURE`: **17 / 96 (17.7%)**.

- Ordinary voirie/reseaux/topographie rejects align with intent.
- Policy still treats etudes architecturales + voirie without heritage/major asset as out of scope.
- Corniche Sidi Ifni survived via competition/major-asset (`corniche` in MAJOR_ASSETS), not infrastructure rescue.

Not the top eliminator this run; step-8 no-domain is.

---

## 8. Feedback findings

| Question | Evidence |
|---|---|
| Influenced positively (run #29 trace) | 0 |
| Influenced negatively on persisted Corniche `#103` | Historically `demote_keep_to_review`, score ~-0.60 |
| Current profile | n_approved=3, n_rejected=4; soft `score_only` on keeps |
| Rejected primarily because of feedback | **No** |

---

## 9. Dedup / known-result findings

### The 1 Deja connu (run #29)

| Field | Value |
|---|---|
| Title | Concours architectural ... annexe siege Region Guelmim Oued Noun |
| Reference | `06/2026/CA/BR/RGON` |
| Collector outcome | `known_unchanged_or_duplicate` |
| Existing result | `#139` |
| Current status | NEW / APPROVED |
| Meaningful update? | No |
| Why UNCHANGED | Early-known snapshot path; not re-handed to orchestrator |

### Other identities

| Result | Ref | Review | Role |
|---|---|---|---|
| `#103` Corniche Sidi Ifni | `04/2026/CA/BR/RGON` | PENDING | Last successful update `#27`; `#28-30` fail before save |
| `#107` Logements Sidi Abdellah | `44/2026/ANEPRSK` | REJECTED | Rediscovered then lost to candidate_errors |
| ISTA Tahannaout `101/2026/OFPPT` | — | Never persisted | verified_offer in `#28-30` but no results row |

`reference_key = digest(reference + institution)` — buyer-string variants change the key. No colliding keys among 38 Radar 1 results. Over-broad title matching is not the primary zero-result cause.

---

## 10. Comparison of recent runs

| Run | Started (UTC) | Disc. | New | Upd | Unch | Auto-rej | Actionable | Cand | after_rules | cand_errors | Collector kept |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 | 2026-09-23T09:28 | 100 | 0 | 0 | 0 | 100 | 0 | 4 | 0 | 4 | 4 |
| 29 | 2026-09-21T15:13 | 100 | 0 | 0 | 1 | 99 | 0 | 3 | 0 | 3 | 3 |
| 28 | 2026-09-21T10:26 | 100 | 0 | 0 | 1 | 99 | 0 | 3 | 0 | 3 | 3 |
| 27 | 2026-09-19T22:27 | 100 | 0 | 1 | 2 | 97 | 1 | 2 | 2 | 0 | 2 |
| 26 | 2026-09-18T20:52 | 100 | 0 | 0 | 3 | 97 | 0 | 2 | 2 | 0 | 2 |
| 25 | 2026-09-18T20:15 | 100 | 0 | 0 | 3 | 97 | 0 | 2 | 2 | 0 | 2 |
| 24 | 2026-09-18T14:57 | 100 | 0 | 0 | 2 | 98 | 0 | 1 | 1 | 0 | 1 |
| 23 | 2026-09-18T09:23 | 68 | 0 | 0 | 3 | 65 | 0 | 2 | 2 | 0 | 2 |
| 21 | 2026-09-17T14:30 | 100 | 1 | 0 | 2 | 97 | 1 | 3 | 2 | 0 | 3 |
| 20 | 2026-09-17T09:26 | 100 | 0 | 0 | 3 | 97 | 0 | 3 | 3 | 0 | 3 |
| 19 | 2026-09-16T12:26 | 100 | 1 | 0 | 2 | 97 | 1 | 3 | 3 | 0 | 3 |
| 18 | 2026-09-15T11:50 | 100 | 0 | 0 | 2 | 97 | 0 | 2 | 2 | 0 | 2 |
| 17 | 2026-09-15T08:16 | 100 | 0 | 2 | 0 | 97 | 2 | 2 | 2 | 0 | 2 |
| 16 | 2026-09-14T16:09 | 100 | 3 | 2 | 0 | 94 | 5 | 5 | 5 | 0 | 5 |
| 13 | 2026-09-14T10:34 | 100 | 2 | 0 | 0 | 98 | 2 | 2 | 1 | 0 | 2 |
| 12 | 2026-09-14T09:08 | 100 | 1 | 0 | 0 | 99 | 1 | 1 | 1 | 0 | 1 |
| 11 | 2026-09-13T17:35 | 79 | 30 | 0 | 0 | 49 | 30 | 30 | 13 | 0 | 30 |

### Collapse point

- Through **run `#27` (2026-09-19)**: keeps still persist (`candidate_errors=0`).
- From **run `#28` (2026-09-21 10:26)** onward: `candidate_errors_count` equals every orchestrator candidate; `final_kept=0`; zero `result_observations`.
- High auto-reject counts existed earlier, but actionable output fully died when post-collector persistence started erroring.

---

## 11. Exact likely root cause(s)

### Root cause 1 — Post-collector persistence failure (decisive for 0 NEW/UPDATED)

Every collector-kept offer in runs `#28-#30` increments `candidate_errors_count` and is counted as auto-reject. Nothing is saved. `log_failure` only records `error_type`, so the exact exception string is not in DB.

Leading suspects: (1) `MarketCandidate` re-validation after in-place metadata mutations; (2) `InvalidCandidateError` from conflicting identities (not reproduced with simplified reconstructions).

### Root cause 2 — Domain-fit fallthrough false negatives

Step 8 rejects professional architectural studies lacking heritage/concours/major-asset, emitting `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` despite `ARCHITECTURAL_SCOPE`. Listing-only path prevents detail rescue.

### Not root causes

- Empty market / broken discovery
- Adaptive feedback hard-reject
- PMMP resolution failures (`rejected_by_resolution=0`)
- Dedup swallowing ISTA into an existing row

---

## 12. Recommended minimal rule/code changes (DO NOT IMPLEMENT YET)

1. Persist candidate error detail on `run_metadata` (exception type + validation loc/msg).
2. Fix orchestrator normalize/save path that turns all keeps into `candidate_errors` since `#28`.
3. Add architectural professional-service keep/review track for explicit etudes/conception/suivi architectural without requiring heritage or competition.
4. Defer step-8 no-domain reject until after PMMP `enrich_detail` when a detail URL is available.
5. Tighten competition tagging so `procedure_type=competition` is not the only lifeline for AO etudes.
6. Keep infrastructure rejects for ordinary voirie; allow rescue when architectural-scope + public-space/corniche/major-asset is present.
7. Reconcile same reference across buyer-string variants; do not lose rediscoveries as silent candidate_errors.
8. Keep feedback non-hard-reject; consider excluding bare `token:travaux` from demoting verified architectural studies.

---

## Appendix A — Collector keeps / known (run #29)

| Outcome | Ref | Reason code | Title | Official URL |
|---|---|---|---|---|
| verified_offer | 101/2026/OFPPT | `ACCEPT_ARCHITECTURAL_COMPETITION` | Études architecturales et la conduite des travaux de démolition et reconstruction de l'ISTA TAHANNAO | https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation& |
| verified_offer | 04/2026/CA/BR/RGON | `ACCEPT_ARCHITECTURAL_COMPETITION` | L'élaboration des études architecturales et suivi des travaux d'aménagement de la corniche de SIDI I | https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation& |
| known_unchanged_or_duplicate | 06/2026/CA/BR/RGON | `ACCEPT_ARCHITECTURAL_COMPETITION` | Concours architectural pour la conception et le suivi des travaux de construction de l’annexe du siè |  |
| verified_offer | 44/2026/ANEPRSK | `ACCEPT_ARCHITECTURAL_COMPETITION` | LA CONCEPTION ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DES LOGEMENTS SIDI ABDELLAH A S | https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation& |

## Appendix B — Full candidate diagnostic table (run #29, all 100)

| # | Outcome | Reason code | Role | Arch | Heritage | Infra | Comp | Major | FB | Title | Ref | URL |
|---:|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | verified_offer | `ACCEPT_ARCHITECTURAL_COMPETITION` | True | True | False | False | True | False | None | Études architecturales et la conduite des travaux de démolition et reconstructio | 101/2026/OFPPT | https://www.marchespublics.gov.ma/index.php?page=entreprise. |
| 2 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | La réalisation des prestations de maintenance et de support logiciel du système  | 23/DDE/DDI/2026 |  |
| 3 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | ETUDES DE DEVELOPPEMENT, D'EXPLOITATION ET DE SECURISATION DU RESEAU FERROVIAIRE | 26E013/PLGV |  |
| 4 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | Etudes d’exécution, fourniture des équipements, construction, installation et mi | SP4130189 |  |
| 5 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | Etudes et conceptions architecturales pour le projet de construction d’un entrep | TC2130522/2026/ONEEBELEC |  |
| 6 | verified_offer | `ACCEPT_ARCHITECTURAL_COMPETITION` | True | True | False | False | True | True | None | L'élaboration des études architecturales et suivi des travaux d'aménagement de l | 04/2026/CA/BR/RGON | https://www.marchespublics.gov.ma/index.php?page=entreprise. |
| 7 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etudes techniques et du suivi des travaux de la sécurisation de l’ensemble des a | 12/SAP/2026 |  |
| 8 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | ETUDES TECHNIQUES DE CONSTRUCTION ET REVETEMENT EN BICOUCHE DES PISTES SUR ENVIR | SAPSB/10/2026 |  |
| 9 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | LA RÉALISATION DES ÉTUDES ARCHITECTURALES ET LE SUIVI DES TRAVAUX DE CONSTRUCTIO | 59/2026/BG |  |
| 10 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | CONTROLE ET OPTIMISATION DES ETUDES TECHNIQUES ET CONTROLE DES TRAVAUX DE CONSTR | 138/2026/T/ETU |  |
| 11 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère démat | 13/AUKSS/2026 |  |
| 12 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère démat | 14/AUKSS/2026 |  |
| 13 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère démat | 15/AUKSS/2026 |  |
| 14 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etude d’élaboration des plans de restructuration des douars Labghailia, Sidi Ais | 16/AUKSS/2026 |  |
| 15 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etudes architecturales et suivi des travaux de construction du lycée qualifiant  | 25/MR/2026 |  |
| 16 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | ÉLABORATION D’UN SCHÉMA D’AMÉNAGEMENT INTÉGRÉ ET DÉVELOPPEMENT DURABLE DES SYSTÈ | 10/2026/dpa/es |  |
| 17 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etudes architecturales et suivi des travaux de construction du LYCEE QUALIFIANT  | CA26/AREFCS/2026 |  |
| 18 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | Réalisation de prestations topographiques relatives au recensement des chutes et | N04/2026/DPA/Benslimane |  |
| 19 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE DEMOLITION DE DEUX LOGEMENTS DE FON | 37/2026/CA |  |
| 20 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE DEMOLITION ET DE RECONSTRUCTION DU  | 38/2026/CA |  |
| 21 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude architecturale pour l'aménagement d'une fromagerie et 2 unités de triturat | 008/2026/DPAJ/SMOP |  |
| 22 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Contrôle topographique des travaux de construction de la piste reliant la RP 200 | 55/2026/BP |  |
| 23 | known_unchanged_or_duplicate | `ACCEPT_ARCHITECTURAL_COMPETITION` | True | True | False | False | True | False | None | Concours architectural pour la conception et le suivi des travaux de constructio | 06/2026/CA/BR/RGON |  |
| 24 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude architecturale et le suivi des travaux de construction d’une salle multisp | 01/26/SS |  |
| 25 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude Architecturale Conception Et Suivi Des Travaux De Construction D’une Maiso | 23/2026/CAR/CAM |  |
| 26 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | ETUDE ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DES MAGASINS AU SOU | 03/2026 |  |
| 27 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Programme Prioritaire de Connectivité Intercommunale : Contrôle extérieur topogr | 31/2026/OU |  |
| 28 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | Etude architecturale et suivi des travaux de construction d’une unité scolaire à | 16/CPTT/2026 |  |
| 29 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CREATION D’UN ESPACE DE LA MEMOIR | 01/2026/CA/BP |  |
| 30 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | False | False | False | False | None | LIGNE A GRANDE VITESSE ENTRE KENITRA ET MARRAKECH : TRAVAUX COMPLEMENTAIRES D’IN | 26T061/PLGV |  |
| 31 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Liaison à Grande Vitesse entre Kenitra et Marrakech Travaux de construction des  | 26T057/PLGV |  |
| 32 | verified_offer | `ACCEPT_ARCHITECTURAL_COMPETITION` | True | True | False | False | True | False | None | LA CONCEPTION ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DES LOGEMEN | 44/2026/ANEPRSK | https://www.marchespublics.gov.ma/index.php?page=entreprise. |
| 33 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | PROJET D'AMÉNAGEMENT DES VOIES, DES ESPACES PUBLICS ET DU PAYSAGE URBAIN — AVENU | 06/BT/2026 |  |
| 34 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Acquisition et installation d une chaine continue de trituration des olives a de | N31/2026/DPAO |  |
| 35 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | True | False | False | False | False | None | ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE CONSTRUCTION D’UN NOYAU COLLEGIAL A | CA/24/2026 |  |
| 36 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | Renforcement de l'AEP du centre et des douars relevant de la commune Melloussa-  | 81/2026/DR9 |  |
| 37 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | Renforcement de l'AEP du centre et des douars relevant de la commune Ain Lahcen- | 74/2026/DR9 |  |
| 38 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | REHABILITATION DES EQUIPEMENTS DE LA STATION DE TRAITEMENT MEKNES (2EME RANCHE) | 80/DR5/2026 |  |
| 39 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux de réalisation des équipements hydromécaniques et électromécaniques du b | 96/2026/DAH |  |
| 40 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Acquisition, installation des équipements  au profit de la morgue de khemisset.  | 17/2026 |  |
| 41 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | INSTALLATION D'UNE STATION MONOBLOC DE DENITRIFICATION (PAR OI) DES EAUX DES FOR | 64/DR5/2026 |  |
| 42 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | EQUIPEMENT DES ADDUCTIONS SPN/1 PAR DES DEBITMETRE ELECTROMAGNETIQUES. | 73/2026/DR9/C |  |
| 43 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | False | False | False | False | None | Réalisation des essais de contrôle et suivi de la qualité des Travaux d’élargiss | 30/2026 |  |
| 44 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Mission d’Assistance à la Maîtrise d’Ouvrage pour  le Contrôle et le Suivi des t | SK45/2026 |  |
| 45 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | La restauration des malades et du personnel de garde du centre hospitalier provi | 09/2026/CHPK |  |
| 46 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | restauration collective au profit des étudiants bénéficiaires de services de res | 07/ONOUSC/2026 |  |
| 47 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | ETUDE GEOTECHNIQUE, RECEPTION DE FONDS DE FOUILLES ET CONTROLE DE QUALITE DES TR | 34/2026/ANEPCO |  |
| 48 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | True | False | False | False | None | La Gestion Déléguée du Centre d’Enfouissement et de Valorisation des déchets mén | 01/2026 |  |
| 49 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux de renforcement et de réhabilitation de l’avenue Casablanca dans la vill | 23/2026/CDPEL |  |
| 50 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | L’affermage du parking du centre commercial à la ville de Chichaoua. | 26/2026 |  |
| 51 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | TRAVAUX DE MISE A NIVEAU DES QUARTIERS SOUS EQUIPES A LA VILLE DE DEMNATE A LA P | 232/2026 |  |
| 52 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Achat de matériels pour l’entretien du réseau d’éclairage  public de la ville de | 24/2026 |  |
| 53 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | False | False | False | False | None | Exploitation de la place des olives de la ville de Zaouit –Cheikh par appel d’of | 10/2026 |  |
| 54 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etude du schéma directeur d'aménagement lumière de la ville El Marsa | 17/2026 |  |
| 55 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | ACQUISITION DE VELOS-TAXIS A ASSISTANCE ELECTRIQUE DANS LE CADRE DU PROJET DE TR | 11/26/INDH |  |
| 56 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Acquisition d’un véhicule vivier équipé pour le transport de poissons vivants au | 11/2026/DRANEFFM/CNHP |  |
| 57 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | Renforcement de l'AEP du centre et des douars relevant de la commune Melloussa-  | 78/2026/DR9 |  |
| 58 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | Renforcement de l'AEP du centre et des douars relevant de la commune Melloussa-  | 79/2026/DR9 |  |
| 59 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Achat de 500 brebis de race SARDI au profit des éleveurs de la zone sud du cercl | 22/2026/DPA/10/SS |  |
| 60 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Le Gardiennage et la Surveillance des bâtiments du siège de la direction provinc | 01/E/2026/2026/DPANFA |  |
| 61 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | True | False | False | False | None | Acquisition  et mise en place de matériel technique relatif au poste de transfor | 30/2026/DPA/G |  |
| 62 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | L’acquisition des isolateurs composites 60 kV, 225 kV et 400 kV pour les Directi | TN4130587 |  |
| 63 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | False | False | False | False | None | Réalisation des prestations de maintenance et de réparations sur sites et à bord | 26S041 |  |
| 64 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Achat de matériel médico-technique pour le centre hospitalier provincial de Khen | 08/2026/CHPK |  |
| 65 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etude relative à la mise à jour du Plan d’Urgence National de Lutte contre la Po | 12/DECLP/2026 |  |
| 66 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux de plantation de 177,5 ha du cactus au niveau de la C.T Ichemraren provi | 16/2026/DPA/CH/SMOPFPA |  |
| 67 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’entretien des plantations de palmier dattier aux palmeraies relevant d | 31/2026/DPA/G |  |
| 68 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | True | False | False | False | None | Maintenance de la solution de sauvegarde | AO/1526 |  |
| 69 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Réalisation d’une étude portant sur l’élaboration d’un plan régional d’aménageme | 22/2026/ANDA |  |
| 70 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | L’assistance  technique pour les services fonctionnels et techniques des logicie | 67/2026/TGR |  |
| 71 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Programme prioritaire de Connectivite Intercommunale- Objet : PPCI-Travaux de co | SK04/2026/CFR |  |
| 72 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’assainissement liquide du POLE URBAIN KSAR SGHIR/KSAR MAJAZ (Province  | 074/2026/AS |  |
| 73 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux de pré-câblage réseaux informatiques et électriques au profit du 1er Arr | 15/SAP/2026 |  |
| 74 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | TRAVAUX D’AMENAGEMENT DE MUR DE CLOTURE DE TERRAIN COMMUNAL A LA COMMUNE DE JORF | 05/2026/CJ |  |
| 75 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | TRAVAUX D'AMÉNAGEMENT ET DE MAINTENANCE DES PARTIES DÉGRADES ET DES ACCOTEMENTS  | 02/2026 |  |
| 76 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | La réalisation de l’inventaire physique des immobilisations,  et des stocks et l | 026/2026/CHUMVIO |  |
| 77 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | L’étude, suivi et contrôle des Forêts Urbaines et péri-urbaines relevant de de l | 19/2026/DPANEF/TA |  |
| 78 | irrelevant_business_purpose | `REJECT_NO_ARCHITECTURAL_ROLE` | False | False | False | False | False | False | None | ASSISTANCE COMPTABLE, BUDGÉTAIRE, FISCALE, SOCIALE ET JURIDIQUE ET RÉALISATION D | 05/CRIMS/2026 |  |
| 79 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etude de diagnostic de l’état du tunnel situé au PK291+900 de la RN25 reliant Bi | 34/2026 |  |
| 80 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | Diagnostic des collecteurs visitables d'assainissement | A/303/26 |  |
| 81 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | False | False | True | False | False | None | DIAGNOSTIC ET ACTUALISATION DES ÉTUDES TECHNIQUES, SUIVI, CONTRÔLE, COORDINATION | 14/CN/2026 |  |
| 82 | irrelevant_business_purpose | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | True | False | False | False | False | False | None | Etude d’inventaire des degrés de pollution des ressources en eau au niveau de la | 40/2026/ABHGZR |  |
| 83 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | True | False | False | False | False | False | None | Acquisition de véhicule de diagnostic et de recherche de défaut sur câbles (DP S | 272/26/ELEC/S |  |
| 84 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | Inventaire physique et contrôle des immobilisations | 71/26/S |  |
| 85 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | True | False | False | False | False | False | None | Achat des réactifs à usage de diagnostic in vitro des programmes sanitaires de l | 37/2026/DAMPS/REA/DELM/A |  |
| 86 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | GARDIENNAGE ET SÉCURITÉ DES BÂTIMENTS ADMINISTRATIFS RELEVANT DE LA CIRCONSCRIPT | 18/DP/2026 |  |
| 87 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | True | False | False | False | None | La sécurité, la surveillance et le gardiennage des bâtiments administratifs et m | 12/DRCRMS/2026 |  |
| 88 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | hygiène et le nettoyage des bâtiments administratifs Relevant du Centre hospital | 10/2026 |  |
| 89 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | False | False | False | False | None | la passation d’un marché reconductible relatif aux prestations de gardiennage et | 29/2026/DRAIRSK/BG |  |
| 90 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Aménagement et Gros Travaux de Maintenance des Bâtiments administratifs relevant | 30/AMM/2026 |  |
| 91 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’aménagement des bâtiments de l’Ecole Nationale Forestière d’Ingénieurs | 06/2026/ENFI |  |
| 92 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | False | False | False | True | False | False | None | ENTRETIEN DES BÂTIMENTS TECHNIQUES DES INSTALLATIONS DE PRODUCTION RELEVANT DU S | 77/2026/DR9/C |  |
| 93 | irrelevant_business_purpose | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | True | True | True | True | False | False | None | Exécution des prestations d’étude et de maitrise d’œuvre pour les projets de :   | 82/2026/CM |  |
| 94 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | True | False | False | False | None | Acquisition du mobilier de bureau pour l’hôpital de proximité de Ksar Kébir rele | 18/2024 |  |
| 95 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | True | False | False | False | None | Acquisition et installation du matériel informatique et  du matériel de bureau p | 17/2026 |  |
| 96 | irrelevant_business_purpose | `REJECT_IRRELEVANT_DOMAIN` | False | False | True | False | False | False | None | Achat de matériel et mobilier de couchage pour l‘hôpital de proximité Ksar Kébir | 16/2026 |  |
| 97 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’extension du réseau pour l’alimentation en eau potable du lycée techni | 202/2026/apdn |  |
| 98 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’aménagement et de réhabilitation de la maison de la culture à Ksar El  | 30/2026/CKK |  |
| 99 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux de construction de huit classes de préscolaire aux communes d’Al Bahraou | 199/2026/apdn |  |
| 100 | irrelevant_business_purpose | `REJECT_PURE_EXECUTION` | False | False | False | False | False | False | None | Travaux d’équipement des forages avec construction d’ouvrages annexes pour l’abr | 56/2026/ORTAF |  |

Buyer/location are not on `collector_trace`; see `representative_results` / `results.radar_metadata` for enriched keeps.
