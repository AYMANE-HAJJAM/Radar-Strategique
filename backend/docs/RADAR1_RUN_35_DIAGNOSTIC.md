# Radar 1 run #35 diagnostic

**Date of analysis:** 2026-09-29  
**Scope:** Read-only. No code changes, no new production search, no paid API calls, no data writes.

**Run:** `#35` (`RADAR_1_MARKETS`), started 2026-09-29 12:19:54 UTC, finished 2026-09-29 12:26:48 UTC, status `completed`, trigger `web`, agent `MarketsRadarAgent`.

Telegram counts match the row exactly:

| Telegram line | Stored value |
|---|---:|
| Nouveaux | 0 (`new_results_count`) |
| Mis à jour | 0 (`updated_results_count`) |
| Déjà connus | 0 (`duplicate_count`) |
| Rejetés automatiquement | 100 (`rejected_count`) |
| À traiter | 0 (`manual_review_count`) |

Collector health was `HEALTHY`, with empty `collector_health_reasons`. Because new, updated, and known were all zero, the completion text is the healthy empty-search wording. That wording is wrong for this run: collection found three verified offers and then dropped all three before persistence.

Evidence is `search_runs` row 35 (`run_metadata.collector_metrics`, `collection_queries`, `collector_trace`, `candidate_error_details`) and `result_observations` for runs 31, 33, and 35. Paid counters on the row are zero (`ai_calls`, `search_calls`, `input_tokens`, `estimated_ai_cost` 0).

---

## Why the run ended at 0 / 0

The collector kept three open, verified PMMP offers and handed them to the orchestrator (`candidates_count` = 3). All three failed at stage `NORMALIZING` with the same `ValidationError`:

```text
MarketCandidate.estimated_amount
Input should be a valid number, unable to parse string as a number
input_value='* TTC MAD'
```

Nothing reached dedup or save. `result_observations` for run #35 is empty. `final_kept` is 0. `candidates_after_rules` is 0.

`rejected_count` 100 = 97 collector relevance rejects (`policy_rejects_count`) + 3 normalization errors (`candidate_errors_count`). The three errors are counted as automatic rejects, which is why Telegram shows 100 rejections and 0 à traiter.

The invalid string is what the PMMP amount-label merger produces when the estimate cell is `*` and the label contains TTC and Dhs/MAD (`_amount_context_hints`). `_amount()` finds no digits and does not replace the text with a number. `enrich_detail()` then `model_copy`s that string onto `estimated_amount`. `model_copy` does not revalidate, so the collector still classifies and keeps the offer. The orchestrator revalidates with `MarketCandidate.model_validate` and discards the whole candidate.

The same error already dropped the two verified PMMP keeps on run #33. Run #33 still produced three new results because three Marché Facile fallbacks had no such placeholder. Run #35 had no fallback survivor: every kept offer was a verified PMMP detail carrying `* TTC MAD`.

---

## 1. Total candidates discovered

| Count | Value | Meaning |
|---|---:|---|
| Raw listing rows | 200 | Sum of page row counts (`pmmp_raw` 160 + `aggregator_raw` 40) |
| Candidates created | **100** | Usable observations that entered the decision trace |
| Unique identities | 100 | |
| Duplicate rows skipped before a second observation | 74 | Not included in the 100 |
| Handed to the orchestrator | 3 | `candidates_count` |

`truncation` is `candidate_limit`. Observation stopped at `RADAR1_MAX_CANDIDATES` (100). That cap closed discovery; it did not prevent the three keeps above.

## 2. Candidates per source

19 direct discovery pages, 0 paid search calls.

| Source | Pages | Raw rows | Candidates created | Entered detail path |
|---|---:|---:|---:|---:|
| PMMP (`marchespublics.gov.ma`) | 17 | 160 | 82 | 18 |
| Marché Facile (`marchefacile.ma`) | 2 | 40 | 18 | 0 |
| Institutional | 0 | 0 | 0 | 0 |

Per PMMP keyword family (created / relevance-rejected / detail attempts / verified):

| Family | Keyword page | Created | Rejected | Detail attempts | Verified |
|---|---|---:|---:|---:|---:|
| architecture | etudes architecturales patrimoine | 10 | 9 | 4 | 1 |
| competition | concours architectural | 4 | 3 | 4 | 1 |
| major_architecture | maitrise oeuvre grand equipement public | 9 | 9 | 0 | 0 |
| major_architecture | conception suivi grand projet architectural | 6 | 6 | 1 | 0 |
| rehabilitation | etude restauration conservation patrimoine | 7 | 7 | 1 | 0 |
| rehabilitation | etude rehabilitation reconversion patrimoine | 4 | 4 | 0 | 0 |
| urbanism | medina ancienne ville | 7 | 6 | 1 | 1 |
| urbanism | revitalisation centre historique | 4 | 4 | 0 | 0 |
| territorial_studies | etude valorisation patrimoine culturel | 2 | 2 | 0 | 0 |
| territorial_studies | etude circuits sites patrimoniaux | 3 | 3 | 3 | 0 |
| project_management | amo plan sauvegarde patrimoine | 6 | 6 | 1 | 0 |
| project_management | suivi travaux restauration patrimoniale | 4 | 4 | 0 | 0 |
| project_management | diagnostic inventaire patrimonial | 10 | 10 | 3 | 0 |
| built_environment | bati ancien menacant ruine | 6 | 6 | 0 | 0 |
| built_environment | remparts murailles fortifications | 0 | 0 | 0 | 0 |
| built_environment | kasbah ksar fondouk | 0 | 0 | 0 | 0 |
| technical_studies | etude technique consolidation batiment historique | 0 | 0 | 0 | 0 |
| AGGREGATOR architecture page 1 | services architecturales et topographiques | 18 | 18 | 0 | 0 |
| AGGREGATOR architecture page 2 | same sector, page=2 | 0 | 0 | 0 | 0 |

The three verified offers came from the first architecture page (ISTA Tahannaout), the competition page (Sidi Ifni), and the médina page (Tiznit).

## 3. PMMP requests / results

| Item | Count |
|---|---:|
| Paid search / resolution API calls | 0 / 0 |
| Direct HTTP fetches recorded on the run | 73 |
| Discovery pages fetched | 19 (17 PMMP + 2 Marché Facile) |
| PMMP raw listing rows | 160 |
| PMMP candidates created | 82 |
| Official detail attempts | 18 |
| Verified official details | 3 |

`billable_search` is false on every query. `search_calls`, `discovery_search_calls`, and `resolution_search_calls` are 0.

## 4. Candidates rejected before detail enrichment

**82.**

They have no `official_url`, resolution state is unresolved, and the trace reason is `irrelevant_business_purpose`. They never entered `official_resolution_attempts`.

## 5. Candidates enriched from PMMP detail

**18 attempted, 18 verified.**

`official_resolution_attempts` = 18, `verified_official` = 3, `unresolved` = 0, `rejected_by_resolution` = 0, `unverified_credible` = 0. The other 15 verified details were rejected by the business policy after enrichment (section 6). Enrichment itself did not fail for this set.

## 6. Candidates rejected after detail

**15**, all `VERIFIED_OFFICIAL`, all `irrelevant_business_purpose`.

| Reference | Reason code | Title |
|---|---|---|
| 04/2026/ITAB | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Etudes techniques et suivi des travaux de construction de l'internat des filles, Institut technique agricole de Berkane |
| 141/2026/S/ETU | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Contrôle technique des études, optimisation et suivi des travaux, ensemble immobilier Les Jardins de Sala Al Jadida |
| 40CA/DPK/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Etudes architecturales et suivi des travaux de transformation de l'unité scolaire Ouled Jmil |
| 06/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Concours architectural pour la conception architecturale et le suivi des travaux de construction du nouveau siège |
| 06/2026/CA/BR/RGON | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Concours architectural, conception et suivi, annexe du siège de la région |
| 44/2026/ANEPRSK | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Conception architecturale et suivi des travaux de construction des logements Sidi Abdellah à Salé |
| A141/RRA/2026 | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Etude technique et suivi des travaux de reconstruction de l'Institut supérieur de la magistrature à Souissi |
| 76/2026/DRPE | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Etude d'identification des sources de pollution industrielle de trois cours d'eau |
| 20/AUKSS/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Etude de renouvellement urbain, zone limitrophe de la gare de Souk Larbaa |
| 19/AUKSS/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Plans de restructuration des douars Tghari, Lakrate, Lemrifege et Machra Rdem |
| 18/AUKSS/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Plans de restructuration des douars Douagher et PAM Lalla Yettou |
| 17/AUKSS/2026 | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Plans de restructuration des secteurs du plan d'aménagement |
| 11/ENA/2026 | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Diagnostic, repositionnement stratégique et transformation de l'Ecole nationale d'administration |
| 19/2026/DPANEF/TA | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Etude, suivi et contrôle des forêts urbaines et péri-urbaines |
| 27/2026/AOOS/CHM6M | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | Diagnostic, réparation et remise en conformité d'une fuite sur un réseau de canalisations |

Arithmetic: 82 before detail + 15 after detail + 3 kept = 100 traces.

## 7. Rejection counts by exact reason code

Trace decisions: `reject` 97, `keep` 2, `review` 1.

| Reason code | Count |
|---|---:|
| `REJECT_IRRELEVANT_DOMAIN` | 24 |
| `REJECT_PURE_EXECUTION` | 22 |
| `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | 20 |
| `REJECT_NO_ARCHITECTURAL_ROLE` | 14 |
| `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | 10 |
| `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | 7 |
| `ACCEPT_ARCHITECTURAL_COMPETITION` | 2 |
| `REVIEW_AMBIGUOUS_RELEVANCE` | 1 |

Legacy `rejection_reason` on the 97 rejects only (the two keeps and the review have none):

| Legacy reason | Count |
|---|---:|
| `non_architectural_purchase` | 24 |
| `pure_execution_works` | 22 |
| `no_architectural_role` | 14 |
| `topography_only` | 11 |
| `no_heritage_scope` | 10 |
| `infrastructure_without_architecture` | 9 |
| `generic_architecture_not_strategic` | 7 |

`topography_only` (11) and `infrastructure_without_architecture` (9) share `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (20). Trace `reason` is only `irrelevant_business_purpose` (97) and `verified_offer` (3). Collector counters: `rejected_by_relevance` 97, `topography_rejected` 11, `technical_only_rejected` 0.

## 8. Keep / review before persistence

| Decision | Category | Code | Reference | Title |
|---|---|---|---|---|
| keep | `P1_CONCOURS` | `ACCEPT_ARCHITECTURAL_COMPETITION` | `101/2026/OFPPT` | Études architecturales et conduite des travaux de démolition et reconstruction de l'ISTA Tahannaout et son internat |
| keep | `P1_CONCOURS` | `ACCEPT_ARCHITECTURAL_COMPETITION` | `04/2026/CA/BR/RGON` | Élaboration des études architecturales et suivi des travaux d'aménagement de la corniche de Sidi Ifni |
| review | `P2_REVIEW` | `REVIEW_AMBIGUOUS_RELEVANCE` | `03/2026` | Élaboration du plan d'aménagement et de sauvegarde de la médina de Tiznit |

Collector counters: `architecture_kept` 3, `heritage_kept` 2, `kept_p1` 2, `kept_p2` 1, `kept_p3` 0. All three are open and have verified PMMP detail URLs (`refConsultation` 1041342 / o4d, 1032453 / m8x, 1042105 / j8k).

## 9. Candidate persistence errors

Three, all at `NORMALIZING`, none at `PERSIST_RESULT`. No SQL error. `error_message` and `error_kind` are null. The run status is `completed`.

| Index | Reference | Title | Error |
|---|---|---|---|
| 0 | `03/2026` | Plan d'aménagement et de sauvegarde de la médina de Tiznit | `estimated_amount='* TTC MAD'` |
| 1 | `101/2026/OFPPT` | ISTA Tahannaout | `estimated_amount='* TTC MAD'` |
| 2 | `04/2026/CA/BR/RGON` | Corniche de Sidi Ifni | `estimated_amount='* TTC MAD'` |

## 10. Dedup outcomes

Result states written for run #35:

| State | Count |
|---|---:|
| NEW | 0 |
| UPDATED | 0 |
| UNCHANGED | 0 |

`duplicate_count` is 0. There is no `known_unchanged_or_duplicate` trace event. The 74 `duplicates_skipped` / `deduped_before_enrichment` are within-run listing duplicates, not persisted UNCHANGED results. Cross-radar dedup did not run because normalization failed first.

## 11. Source failures, timeouts, cooldowns

None recorded.

| Signal | Value |
|---|---|
| `source_errors` | 0 |
| `query_errors` | empty |
| `collector_health` | HEALTHY |
| `collector_health_reasons` | empty |
| `http_403` / `http_429` / `blocked` | 0 / 0 / 0 |
| `cost_warning` | false |
| Timeouts in the trace | none (`resolution_error` null on every kept and post-detail reject) |

One discovery page returned no rows: keyword `remparts+murailles+fortifications` was classified `generic_org` with `raw_results_count` 0. Two other pages had rows that were already seen (`kasbah+ksar+fondouk`, 1 duplicate; the technical-studies page, 9 duplicates) and created no new candidates. Those are empty yields, not fetch failures.

## 12. Parsing failures

`rejected_by_parser` = 0, `parser_failures` = 0, `rejected_by_source` = 0. The trace has no `no_tender_rows_or_detail_fields`, `page_fetch_or_parse`, `missing_geography_buyer_or_deadline`, or `official_resolution_failed` events.

The amount placeholder is not counted as a parser rejection. It survives collection and fails only when the orchestrator rebuilds `MarketCandidate`.

## 13. Rate-limit and HTTP errors

None. `http_403` = 0, `http_429` = 0, `source_errors` = 0, `query_errors` = [].

## 14. Plausibly relevant titles that were rejected

The three titles in section 8 were classified keep/review and then lost to the amount error. They are not policy rejects.

These verified details were rejected after enrichment despite explicit architectural or competition wording:

| Reference | Code | Why it looks relevant |
|---|---|---|
| `06/2026` | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Title is a concours architectural for conception and works supervision |
| `06/2026/CA/BR/RGON` | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Concours architectural for design and works supervision of a regional annex |
| `40CA/DPK/2026` | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Études architecturales and works supervision for a school conversion |
| `44/2026/ANEPRSK` | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Conception architecturale and works supervision of housing at Salé |

Listing-only rejects (no detail fetch) with explicit architectural wording, dropped as generic or out of scope:

| Reference | Code | Title start |
|---|---|---|
| `TC2130522/2026/ONEEBELEC` | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | Etudes et conceptions architecturales, entrepôt au poste Ghanem |
| `04/2026` | `REJECT_NO_ARCHITECTURAL_ROLE` | Charte architecturale et paysagère de la ville d'Es-Smara |
| `010/2026/DPAJ/SMOP` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etude architecturale, unité de trituration, Guenfouda |
| `05/2026/Y/SP` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etudes architecturales, 22 terrains de sport |
| `009/2026/DPAJ/SMOP` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etude architecturale, unité de valorisation des PAM |
| `22/2026/CA` | `REJECT_IRRELEVANT_DOMAIN` | Etude architecturale, parc automobile, Taroudannt |
| `CA12/N/2026` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etudes architecturales, remplacement de quatre bâtiments préfabriqués |
| `CA10/N/2026` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etudes architecturales, dix blocs sanitaires scolaires |
| `01/CA/2026/CCisfm` | `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | Etude architecturale, centre multiservices Ain Chkef |

`REJECT_PURE_EXECUTION` also hits lexical noise (`restauration collective`, hospital food, school canteens) and `REJECT_IRRELEVANT_DOMAIN` hits building security and cleaning. Those are not plausible architecture opportunities. The keyword `patrimoine` also pulled logiciel / patrimoine foncier (`23/DDE/DDI/2026`), which the domain reject correctly dropped.

## 15. Empty market, or a pipeline problem?

The run did not find an empty market. It created 100 observations, verified 18 official details, and classified 3 as keep or review. The 0 nouveaux / 0 mis à jour outcome is the normalization failure on `estimated_amount='* TTC MAD'` for every survivor.

Filtering is also stricter than the titles suggest: four verified architectural or competition notices were rejected as infrastructure after detail. That strictness did not produce the zero Telegram counts. Those four were already rejected. The three that passed never got a result row.

---

## Comparison with the latest run that produced actionable results

The latest Radar 1 run with `new_results_count` or `updated_results_count` above zero is **#33** (2026-09-24 09:58–10:02 UTC, telegram trigger). It wrote 3 `manual_review` observations, all `discovery_status` NEW (`28/2026`, `26/2026`, `27/2026`, the Chefchaouen architectural consultations). Run #31 (7 new) is older. Run #32, between them, was also 0 new / 0 updated.

| | Run #35 | Run #33 |
|---|---:|---:|
| Discovered (candidates created) | 100 | 63 |
| Raw listing rows | 200 | 90 |
| Rejected (Telegram `rejected_count`) | 100 | 58 |
| Collector relevance rejects | 97 | 56 |
| Kept by collector | 3 (2 keep + 1 review) | 5 (2 verified + 3 credible fallback) |
| Persisted (`result_observations`) | 0 | 3 |
| New | 0 | 3 |
| Updated | 0 | 0 |
| Unchanged (result state) | 0 | 0 |
| Errors (`candidate_errors_count`) | 3 | 2 |
| Collector health | HEALTHY | PARTIAL (`official_verification_pending`) |
| Paid search calls | 0 | 2 |
| Handed to orchestrator | 3 | 5 |

Run #33's two errors are the same `* TTC MAD` validation on `101/2026/OFPPT` and `04/2026/CA/BR/RGON`. Those two never became results on #33 either. The three that did were Marché Facile credible fallbacks, which do not carry that placeholder. Run #35 verified the médina de Tiznit as well and then lost all three keeps, including the two that had already failed on #33.

Run #33 collector trace also has 2 `known_unchanged_or_duplicate` events. Those did not create UNCHANGED rows (`duplicate_count` stayed 0).

---

## Conclusion

**F. Another specific cause: orchestrator normalization drops every collector keep because `estimated_amount` is the unparsed string `* TTC MAD`.**

Discovery, PMMP fetch, and detail verification worked. The three actionable offers were classified keep/review and then discarded at `NORMALIZING` before any NEW, UPDATED, or UNCHANGED row could be written. Filtering rejected other architectural-looking titles, but that is not what forced 0 nouveaux and 0 mis à jour.
