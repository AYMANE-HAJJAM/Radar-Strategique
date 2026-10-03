# Radar 1 latest zero-result run

**Date of analysis:** 2026-10-02  
**Scope:** Read-only. No code changes, no new production search, no paid API calls, no database writes.

Evidence is `search_runs` row 41 (`run_metadata.collection_queries`, `collector_trace`, `collector_metrics`, `collector_health`) and `result_observations` for `run_id = 41`. Paid counters on the row are zero (`ai_calls`, `search_calls`, `input_tokens`, `estimated_ai_cost` 0).

---

## 1. The run

Latest completed Radar 1 `SearchRun` (`radars.code = RADAR_1_MARKETS`):

| Field | Value |
|---|---|
| Run id | **41** |
| Agent | `MarketsRadarAgent` |
| Started | 2026-10-02 09:31:15 UTC (10:31:15 UTC+1) |
| Finished | 2026-10-02 09:37:22 UTC (10:37:22 UTC+1) |
| Trigger | `web` |
| Launched by | user id **1**, display name **Aymane** (`launched_by_user_id = 1`, `triggered_by = 1`) |
| Final status | **completed** |
| Final stage | `COMPLETED` |
| Error | none (`error_kind` and `error_message` are null) |

Telegram / summary counters on the row:

| Counter | Value |
|---|---:|
| Nouveaux (`new_results_count`) | 0 |
| Mis à jour (`updated_results_count`) | 0 |
| Déjà connus (`duplicate_count`) | 1 |
| Rejetés (`rejected_count`) | 99 |
| À traiter (`manual_review_count`) | 0 |
| `final_kept` | 0 |

The previous completed Radar 1 run, **#40** (2026-09-30), did produce 2 updated results. Run #41 is the latest completed run, and it is the latest run with 0 NEW and 0 UPDATED.

---

## 2. Discovery counts

| Count | Value | Meaning |
|---|---:|---|
| Direct discovery pages fetched | 19 | 17 PMMP keyword pages + 2 Marché Facile sector pages |
| Raw listing rows | **200** | `pmmp_raw` 160 + `aggregator_raw` 40 |
| Candidates created | **100** | Usable observations in `collector_trace` (`unique_identities` 100) |
| Within-run listing duplicates skipped | 73 | `duplicates_skipped` / `deduped_before_enrichment`. These have no second trace event |
| Rows not processed after the candidate cap | 27 | `truncation` includes `candidate_limit`. 200 raw − 100 created − 73 duplicates |
| Handed to the orchestrator | **1** | `candidates_count` |

Candidates by source (created observations):

| Source | Candidates | Share of 100 |
|---|---:|---:|
| PMMP (`marchespublics.gov.ma`, `OFFICIAL_PROCUREMENT`) | **81** | 81% |
| Marché Facile (`marchefacile.ma`, `PROCUREMENT_AGGREGATOR`) | **19** | 19% |
| Other / institutional | **0** | 0% |

`pmmp_observations` is 81 and `marchefacile_observations` is 19. `institutional_observations` is absent from the non-zero metrics (0).

---

## 3. Exact queries executed

This run made **no paid search calls**. `queries_executed`, `search_calls`, and `resolution_search_calls` are 0. All 19 queries are direct public pages (`billable_search` false). PMMP queries are the `keyWord` on `entreprise.EntrepriseAdvancedSearch`. Result count below is the parsed listing-row count (`raw_results_count`). “Created” is how many of those rows became new observations.

| # | Family | Exact term / query | Source | Raw rows | Created | Relevance rejects | Detail attempts | Verified |
|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | architecture | `etudes architecturales patrimoine` | PMMP | 10 | 10 | 8 | 7 | 1 |
| 2 | architecture | `https://marchefacile.ma/appels-offres/secteur/services-architecturales-et-topographiques` | Marché Facile | 20 | 19 | 19 | 0 | 0 |
| 3 | competition | `concours architectural` | PMMP | 10 | 5 | 5 | 4 | 0 |
| 4 | major_architecture | `maitrise oeuvre grand equipement public` | PMMP | 10 | 9 | 9 | 0 | 0 |
| 5 | major_architecture | `conception suivi grand projet architectural` | PMMP | 10 | 5 | 5 | 0 | 0 |
| 6 | rehabilitation | `etude restauration conservation patrimoine` | PMMP | 10 | 6 | 6 | 1 | 0 |
| 7 | rehabilitation | `etude rehabilitation reconversion patrimoine` | PMMP | 10 | 2 | 2 | 0 | 0 |
| 8 | urbanism | `medina ancienne ville` | PMMP | 10 | 6 | 6 | 0 | 0 |
| 9 | urbanism | `revitalisation centre historique` | PMMP | 10 | 7 | 7 | 0 | 0 |
| 10 | territorial_studies | `etude valorisation patrimoine culturel` | PMMP | 10 | 1 | 1 | 1 | 0 |
| 11 | territorial_studies | `etude circuits sites patrimoniaux` | PMMP | 10 | 0 | 0 | 0 | 0 |
| 12 | project_management | `amo plan sauvegarde patrimoine` | PMMP | 10 | 8 | 8 | 0 | 0 |
| 13 | project_management | `suivi travaux restauration patrimoniale` | PMMP | 10 | 4 | 4 | 0 | 0 |
| 14 | project_management | `diagnostic inventaire patrimonial` | PMMP | 10 | 10 | 10 | 4 | 0 |
| 15 | built_environment | `bati ancien menacant ruine` | PMMP | 10 | 7 | 7 | 0 | 0 |
| 16 | built_environment | `remparts murailles fortifications` | PMMP | **0** | 0 | 0 | 0 | 0 |
| 17 | built_environment | `kasbah ksar fondouk` | PMMP | 10 | 1 | 1 | 0 | 0 |
| 18 | technical_studies | `etude technique consolidation batiment historique` | PMMP | 10 | 0 | 0 | 0 | 0 |
| 19 | architecture | same Marché Facile sector URL, `?page=2` | Marché Facile | 20 | 0 | 0 | 0 | 0 |

Query 1 also has `rejected_by_parser` 1 and `kept_p2` 1. Those are the Tazekka review discarded by the validator, and the ISTA Tahannaout offer that survived, described in sections 4 and 7.

Queries 18 and 19 ran after the 100-observation cap was already reached. Query 18’s 10 rows contain 9 already-seen duplicates and 1 unprocessed row. Query 19’s 20 rows contain 3 already-seen duplicates and 17 unprocessed rows. Together with 9 unprocessed rows at the end of query 17, that is the 27-row truncation. The heritage keyword pages (queries 1–16) finished before that cap.

Query 11 returned 10 rows that were all already-seen duplicates, so it created no new candidate. Query 16 returned no rows (`page_type` `generic_org`).

---

## 4. Pipeline counts

Trace events are 100, equal to candidates created. There is no `known_unchanged_or_duplicate` event. Every created observation produced exactly one trace, in query order.

| Stage | Count | Evidence |
|---|---:|---|
| Discovered | **100** | `candidates_created` / trace length. Raw rows were 200 |
| Preliminary / listing rejected (before detail) | **83** | `resolution_state = UNRESOLVED`, no `official_url`, trace reason `irrelevant_business_purpose` |
| Detail-enriched | **17** | `resolution_state = VERIFIED_OFFICIAL`. `official_resolution_attempts` 17. All 17 verified; `resolution_error` is null on every verified event |
| Final-policy rejected after detail | **15** | verified and reason `irrelevant_business_purpose` |
| Review, then validator-rejected | **1** | verified, business decision `review`, trace reason `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT` (`rejected_by_parser` 1) |
| Kept by collector | **1** | reason `verified_offer`. `architecture_kept` 1, `kept_p2` 1, `kept_p1` 0. Handed over: `candidates_count` 1 |
| Normalization errors | **0** | `candidate_errors_count` 0. No `candidate_error_details` key |
| Persistence errors | **0** | status `completed`, no error kind, no saving failure |
| Dedup NEW | **0** | `new_results_count` 0. No observation with state `manual_review` / NEW |
| Dedup UPDATED | **0** | `updated_results_count` 0 |
| Dedup UNCHANGED | **1** | `duplicate_count` 1. Observation 209, state `unchanged`, result 159 |
| Final actionable | **0** | `final_kept` 0, `manual_review_count` 0, `accepted_count` 0 |

Arithmetic: 83 + 15 + 1 + 1 = 100 traces. 83 + 15 + 1 = 99, which is `rejected_count`.

The 83 pre-detail rejects share one trace reason. Stored traces do not include `preliminary_relevance`, so the cheap prefilter and the later listing hard-reject are not stored as two counters. Both leave the candidate `UNRESOLVED`.

The one survivor was normalized (`candidates_after_rules` 1) and then skipped before any model call (`ai_calls` 0, `analyzed_count` 0, `ai_skipped_reasons.ALREADY_CACHED` 1).

---

## 5. Rejection reasons

99 rejections. Percentages are of those 99.

The 98 policy rejects use the trace’s business `reason_code`. The remaining item was classified `REVIEW_AMBIGUOUS_RELEVANCE` and then discarded by validation; the stored rejection string is `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT`.

| Reason code | Count | % of 99 | Before detail | After detail |
|---|---:|---:|---:|---:|
| `REJECT_IRRELEVANT_DOMAIN` | 30 | 30.3% | 29 | 1 |
| `REJECT_PURE_EXECUTION` | 20 | 20.2% | 20 | 0 |
| `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` | 19 | 19.2% | 13 | 6 |
| `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` | 12 | 12.1% | 12 | 0 |
| `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` | 11 | 11.1% | 3 | 8 |
| `REJECT_NO_ARCHITECTURAL_ROLE` | 6 | 6.1% | 6 | 0 |
| `REVIEW_AMBIGUOUS_RELEVANCE`, discarded as `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT` | 1 | 1.0% | 0 | 1 |

30 + 20 + 19 + 12 + 11 + 6 + 1 = 99.

Legacy `rejection_reason` on the 98 policy rejects (the review item and the keep have none):

| Legacy reason | Count |
|---|---:|
| `non_architectural_purchase` | 30 |
| `pure_execution_works` | 20 |
| `infrastructure_without_architecture` | 12 |
| `generic_architecture_not_strategic` | 12 |
| `no_heritage_scope` | 11 |
| `no_architectural_role` | 6 |
| `topography_only` | 7 |

`topography_only` (7) and `infrastructure_without_architecture` (12) together are `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (19). `topography_rejected` in collector metrics is 7, matching the legacy topography count. Six of those seven topography rejects are after a verified PMMP detail.

The not-kept review and the keep:

| Reference | Trace reason | Business decision | Code | Category on the trace | Resolution |
|---|---|---|---|---|---|
| `12/2026/DRANEFFM/SAP` | `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT` | `review` | `REVIEW_AMBIGUOUS_RELEVANCE` | `P2_REVIEW` | verified, then rejected |
| `101/2026/OFPPT` | `verified_offer` | `keep` | `ACCEPT_ARCHITECTURAL_COMPETITION` | `P1_CONCOURS` | verified, kept, then UNCHANGED |

The trace’s `business_relevance` is recomputed with `evaluate_relevance` when the event is written. Collector counters record the survivor at priority 2 (`kept_p2` 1, `heritage_kept` 0). The saved result 159 already stores category `P2_REVIEW`.

---

## 6. Notice 04/2026/AUS

**A. Never discovered.**

The reference `04/2026/AUS` does not appear in any of the 100 trace events. No trace title contains both Settat and a cultural / historical heritage study. The Settat titles in this run are a collège at El Jadida under AREF Casablanca-Settat, and two school-canteen contracts (`04EXP/DPBS/2026`, `127/DPS/2026`).

The keyword that matches the notice’s object did run:

- Query 10, family `territorial_studies`, exact term `etude valorisation patrimoine culturel`
- Source PMMP, 10 raw rows
- 9 rows were within-run duplicates of identities already seen
- The only new observation is `08/2026`, “ETUDE TECHNIQUE, SUIVI ET RECEPTION DES TRAVAUX DE REHABILITATION DES BATIMENTS DE L’ISPITS CASABLANCA - SITE LALLA AICHA”, verified and then rejected `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT`

That keyword page was fetched. `04/2026/AUS` was not among its 10 parsed rows, and it was not among the other 90 observations.

Stored history of the notice, not from this run: result **132**, reference `04/2026/AUS`, title “Appel d’offres ouvert National n° 04/2026 ayant pour objet l’étude de valorisation du patrimoine culturel, naturel et historique de la province de Settat.” It was observed only on run **13** (2026-09-14, state `manual_review`). Stored `review_status` is `APPROVED`, stored `source_status` is `open`, `deadline` is **2026-10-02**, `last_seen_at` is 2026-09-14. This diagnostic did not re-open the PMMP page, so it does not establish whether the notice was still listed on 2026-10-02. It does establish that run 41’s fetched pages did not contain it.

---

## 7. Candidates containing heritage terms

Accent-insensitive match on the 100 titles against: patrimoine, médina, monument, restauration, conservation, valorisation, remparts, fortifications, architecture patrimoniale.

No observation contains médina, monument, conservation, remparts, fortifications, or architecture patrimoniale.

Six titles match the other terms. All six were rejected before detail (`UNRESOLVED`, no official URL).

| Reference | Title | Matched term | Source | Query | Stage | Outcome | Reason |
|---|---|---|---|---|---|---|---|
| `23/DDE/DDI/2026` | Maintenance et support logiciel du système de gestion du patrimoine foncier et immobilier de l’Etat AMLACS | patrimoine | PMMP | architecture / `etudes architecturales patrimoine` | before detail | rejected | `REJECT_IRRELEVANT_DOMAIN` |
| `04EXP/DPBS/2026` | Restauration collective, internats et cantines, Direction Provinciale de Benslimane, AREF Casablanca-Settat | restauration | PMMP | rehabilitation / `etude restauration conservation patrimoine` | before detail | rejected | `REJECT_PURE_EXECUTION` |
| `127/DPS/2026` | Restauration collective, internats et cantines, direction provinciale de Settat | restauration | PMMP | same rehabilitation query | before detail | rejected | `REJECT_PURE_EXECUTION` |
| `11/2026` | Restauration collective des enfants des centres de protection de l’enfance à Fès | restauration | PMMP | same rehabilitation query | before detail | rejected | `REJECT_PURE_EXECUTION` |
| `24/2026/CHRM` | Restauration collective hospitalière, Centre Hospitalier Régional de Marrakech | restauration | PMMP | same rehabilitation query | before detail | rejected | `REJECT_PURE_EXECUTION` |
| `01/2026` | Gestion déléguée du centre d’enfouissement et de valorisation des déchets « Saddina pour l’Environnement » | valorisation | PMMP | urbanism / `medina ancienne ville` | before detail | rejected | `REJECT_NO_ARCHITECTURAL_ROLE` |

These six are keyword noise (land registry software, catering, landfill), not heritage studies.

Verified notices that do contain architectural wording, and that this run did fetch, were rejected after detail:

| Reference | Title | Stage | Outcome | Reason |
|---|---|---|---|---|
| `06/2026` | Concours architectural, conception et suivi, nouveau siège, Laâyoune | detail-enriched | rejected | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (`topography_only`) |
| `06/2026/CA/BR/RGON` | Concours architectural, conception et suivi, annexe du siège, Guelmim-Oued Noun | detail-enriched | rejected | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (`topography_only`) |
| `08/CONSA/2026/AREPO` | Étude architecturale, conception et suivi, souk hebdomadaire, Temsamane | detail-enriched | rejected | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (`topography_only`) |
| `27/2026/BR` | Étude architecturale et suivi, entretien et réhabilitation, salle couverte Kindy, Ben M’sick | detail-enriched | rejected | `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` (`topography_only`) |
| `08/2026` | Étude technique, suivi et réception, réhabilitation des bâtiments de l’ISPITS Casablanca | detail-enriched | rejected | `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` |
| `12/2026/DRANEFFM/SAP` | Études techniques, aménagements, circuits et clusters écotouristiques, Parc National de Tazekka | detail-enriched | review, then validator reject | `REVIEW_AMBIGUOUS_RELEVANCE` / `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT` |
| `101/2026/OFPPT` | Études architecturales et conduite des travaux, démolition et reconstruction de l’ISTA Tahannaout et son internat | detail-enriched, kept | deduplicated UNCHANGED | `ACCEPT_ARCHITECTURAL_COMPETITION` on the trace; result already stored |

Twelve Marché Facile titles were classified `REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC` without a detail fetch. They include ordinary lycées, sports grounds, a gare routière, a souk, and similar études architecturales. They never became actionable.

---

## 8. Source health

`collector_health` is **PARTIAL**. The only health reason is `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT`. That string is the validator rejection of `12/2026/DRANEFFM/SAP`. A parser-kind rejection calls the collector warning path, which sets health to `DEGRADED` and then rewrites it to `PARTIAL` because one candidate was kept. It is not an HTTP or parser failure of a source.

| Signal | This run |
|---|---|
| Source failures (`source_errors`) | 0 |
| Query errors (`query_errors`) | empty |
| HTTP 403 / 429 / blocked | 0 / 0 / 0 |
| Parser failures (`parser_failures`, `rejected_by_source`) | 0 on every query. The single `rejected_by_parser` is the validator reject above |
| Resolution failures | 0 (`rejected_by_resolution` 0, no `resolution_error`) |
| Rate limits / cooldowns | none recorded |
| Paid search / AI | 0 calls, cost 0 |
| Direct fetches | 70 (`direct_pages_fetched` 19, plus detail fetches) |
| Empty source response | query 16, `remparts murailles fortifications`, 0 rows, page type `generic_org` |
| Pagination | PMMP keywords were single search pages of 10 rows. No second PMMP page was fetched. Marché Facile page 2 was fetched (20 rows) and then almost entirely dropped by `candidate_limit` |

`truncation` is `['candidate_limit']`. The cap closed the tail of query 17 and queries 18–19. It did not stop the valorisation, médina, or concours pages.

---

## 9. Conclusion

**G. Mixed causes.**

Run 41 completed cleanly. It did not fail at fetch, parse, normalization, or save.

What produced 0 NEW / 0 UPDATED:

1. **Final policy rejected the verified architectural notices that were new.** Fifteen verified details were rejected, including two concours architectural (`06/2026`, `06/2026/CA/BR/RGON`) and the Temsamane souk and Kindy réhabilitation, all as `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE`. A seventeenth verified detail (`12/2026/DRANEFFM/SAP`, Tazekka) was scored `REVIEW_AMBIGUOUS_RELEVANCE` and then dropped by validation as `NOT_RELEVANT_INDIVIDUAL_PROCUREMENT`, which is also why health is `PARTIAL`.
2. **The only collector keep was already known.** `101/2026/OFPPT` (ISTA Tahannaout) was kept, normalized, and written as observation 209 with state `unchanged` against result 159. That result was created on run 36 (2026-09-29, `manual_review`) and is still `PENDING`. Run 40 had already recorded an update on `business_category`. Run 41 did not add a NEW or UPDATED row (`ai_skipped_reasons.ALREADY_CACHED` 1).
3. **The known Settat heritage notice was not on the fetched pages.** `04/2026/AUS` was not among the 100 observations. The exact keyword `etude valorisation patrimoine culturel` ran and its one new row was the ISPITS Casablanca rehabilitation, not Settat. Separately, listing policy rejected 83 candidates before any detail fetch, including 12 Marché Facile études architecturales as generic and the patrimoine / restauration / valorisation titles in section 7 as noise.

The zero actionable counts are the policy rejections plus one correct UNCHANGED dedup. They are not a persistence crash, a rate limit, or an empty PMMP response on the queries that ran.
