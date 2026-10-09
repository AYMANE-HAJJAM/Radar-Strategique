# Radar 1 local code and database diagnostic

Date: 2026-10-09. Database snapshot checks began at 14:39:38 UTC (15:39:38 Africa/Casablanca). Source checkout: `02f2cf2`.

## Scope and conclusion

This report inspects the local checkout and the PostgreSQL database selected by **local** `backend/.env`/`load_config()`. Its host is `ep-long-river-aebc069s-pooler.c-2.us-east-2.aws.neon.tech`, database `neondb`. This is a remote Neon database used by the local configuration; it is **not established as Render's production database**. Matching run numbers with the user's production observations does not establish database identity or deployed-code identity.

No source code, database records, or configuration was modified. No SearchRun was reserved, Radar execution launched, Flask application started, migration run, or paid API invoked. All database reads used an explicit PostgreSQL `READ ONLY` transaction, ending in rollback/connection close. Public board searches and official-detail reads were ordinary public HTTP inspections, without durable indexing or business persistence. Algorithm checks used scripted HTTP, mock sessions, and in-memory policy evaluation. This document is the only requested workspace artifact.

**The zero-result symptom exists in the locally configured DB history. It does not have a single cause.** Run #55 used incremental index discovery; #56–#58 used legacy discovery. The local code also contains confirmed opportunities for losing business processing after technical indexing, and a separate web display defect. Production applicability remains unverified.

Most important findings:

1. **CONFIRMED BUG:** collector-failure progress handling commits partially synchronized index rows. Failed run #54 inserted 528 rows during its time window without reaching business processing; subsequent index discovery can regard those rows as unchanged.
2. **CONFIRMED BUG:** the three-unchanged-page rule does not provide complete discovery on the observed PMMP ordering. The sampled board is consistent with descending deadline order, not publication order. A scripted replay missed an unseen heritage study on page four.
3. **CONFIRMED BUG:** successful indexing can consume changes beyond the 100-business-observation cap, without recording pending policy work. This path is reproduced offline; its occurrence in a historical successful index run is not established.
4. **CONFIRMED BUG:** the web exact-run filter only accepts observation states `new`/`updated`, while Radar 1 persistence writes relevant review candidates as `manual_review`. Local Radar 1 has 70 such observations and no `new`/`updated` observation states.
5. **DESIGN RISK:** collector, validator, and queue evaluate different policy corpora. PMMP activity classifications and buyer names can introduce heritage/architecture signals absent from the procurement object. Actual official-detail replays produce different decisions.

## 1. Actual pipeline and skip points

| Stage | Actual implementation | Important behavior |
|---|---|---|
| Runtime selection | `app/config.py:49`; `modules/radar1_markets/collector.py:671` | Default `legacy`; `pmmp_index` must be selected explicitly. Current local config is `pmmp_index`, overlap 3, candidate/trace cap 100. Stored runs record their own historical mode. |
| PMMP listing read | `pmmp_listing_collector.py:198,260,292` | GET search form, submit public search, follow Prado next-page state. Parses consultation identity, buyer, abbreviated reference/object, dates, procedure/category/location. No explicit newest-publication sort is requested. |
| Index classification | `pmmp_listing_index.py:36,69,79` | Lookup source+consultation ID, then identity key. Insert NEW; update last-seen for known rows; compare listing fingerprint for UPDATED/UNCHANGED. Classification flushes before business processing. |
| Incremental sync | `pmmp_listing_index.py:141`; collector `:679` | Sync runs with `commit=False`, but uses the same session as SearchRun progress. Only NEW/UPDATED observations are actionable. Empty index returns no candidates with a warning. |
| Observation and early dedup | collector `:377,507`; orchestrator `:264` | The 100-examined limit is checked before preliminary policy. Duplicate signatures, intersecting identities, or complete unchanged business snapshots may skip enrichment. Index UNCHANGED skips this entire stage. |
| Preliminary policy | `policy.py:preliminary_plausible`; collector `:530` | Obvious negative/goods/asset-management terms and execution-only titles reject before detail. These rejects do not become Results. Buyer and evidence text can affect this gate. |
| Pre-detail business policy | collector `:68,86,543` | Some no-role/no-domain/generic-architecture rejects are deferred when official detail could rescue them. Other rejects return before enrichment. |
| Official enrichment | `integrations/pmmp/parser.py:503,572`; collector `:576` | Fetch and cache individual notice; extract identity/buyer/procedure/deadline/estimate/domains; verify identity, buyer, title and deadline against page. Closed/expired evidence rejects. Noncontradictory access failures can retain credible review candidates; mismatches cannot. Resolution fallback may use paid searches in normal operation, but none were invoked here. |
| Final ARCHERITAGE policy | collector `:628`; `policy.py:evaluate_relevance` | Heritage, relevant competition, major architecture. Feedback may demote keep to review, not hard-reject a keep. Final missing Morocco/buyer/deadline checks and `radar.validate_candidate` can still reject. |
| Shared and specific validation | `radar1_markets/validators.py:6,39`; `core/radar_agent_base.py:validate_candidate`; `core/conditions.py` | Recomputes business policy with a smaller corpus; combines it with source/procedure/geography/freshness conditions. Unknown mandatory evidence generally requests review, not rejection. Confirmed expiry rejects. |
| Business dedup | `core/orchestrator.py:339`; `core/dedup.py:find_existing`; `core/review.py:66` | Canonical URL, reference+buyer and identity keys. Same commercial snapshot/memory can become business UNCHANGED. Conflicting identities yield candidate errors. Cross-radar dedup can attach evidence to another radar's owner card. |
| Persistence | `db/repositories/results.py:save,observe`; orchestrator `:492` | Saves validated candidates, workflow state, and per-run observations. Collector rejects never reach this repository. Optional AI failures usually become review. A relevant manual-review candidate is an observation with state `manual_review`, even when discovery status is NEW/UPDATED. |
| SearchRun | orchestrator `:126,166`; `db/repositories/search_runs.py` | NEW/UPDATED counts are business changes, distinct from technical index deltas. Progress commits use the same DB session as the index. Completed does not mean complete coverage or healthy sources. |
| API and frontend | `api/results.py:52,92`; `frontend/app/radars/[radarId]/page.tsx:26,30`; `components/run-history-table.tsx:18` | Pending list applies current policy and expiry gates. Exact-run view additionally requires `new`/`updated` observation state. Frontend history renders SearchRun business counters directly; it does not convert index NEW into business NEW. |

Additional loss paths are documented below: no retry ledger after indexing, no detail-only amendment detection, caps, pre-detail rejection, inconsistent policy corpora, queue revalidation, and process-local jobs.

## 2. Local database findings

### Index and business counts

| Measurement | Read-only finding |
|---|---:|
| `pmmp_listing_index` rows | **4,366** |
| Minimum first-seen | 2026-10-02 20:42:13.228029 UTC |
| Maximum first-seen | 2026-10-07 12:32:04.681174 UTC |
| Maximum last-seen | 2026-10-07 12:41:44.519493 UTC |
| Maximum last-changed | 2026-10-07 12:32:04.681174 UTC |
| Seen in trailing seven days at inspection | 4,366 |
| Inserted or changed in trailing seven days | 4,366; this includes baseline inserts, not 4,366 amendments |
| Stored fingerprints unequal to recomputation from stored listing fields | **0** |
| Alembic version in configured DB | `a1b2c3d4e5f6` |
| Radar 1 Results | **60** |
| Human review status | **42 PENDING / 8 APPROVED / 10 REJECTED** |
| Radar 1 observations | **97: 70 `manual_review`, 27 `unchanged`** |
| Radar 1 SearchRuns retained | **44** |
| Historical counter sums | 60 business NEW, 10 UPDATED, 3,049 rejected, 19 candidate errors |

Historical counter sums count repeated encounters and mixed pipeline stages. They are **not unique-index policy outcomes**. Human REJECTED is also distinct from automatic policy rejection. A zero `accepted_count` does not mean that nothing was persisted: deterministic/no-AI processing can save relevant candidates as manual review.

The 42 stored pending rows produce only **one currently eligible pending card** when the actual queue functions are evaluated on the snapshot: Result #170, `C01/2026`. Of the 42, 28 are obsolete and 40 fail current business eligibility; these sets overlap and must not be added. Expiry and a stricter current policy can legitimately hide historical pending records. The dashboard's raw pending counter does not apply these gates, creating a separate count discrepancy.

### Baseline and backfill

The latest **documented successful full baseline** is 2026-10-02, approximately 20:42–21:26 UTC: 384 pages, 3,840 declared/listed rows, 3,837 unique entries, final-page completion. Evidence: `RADAR1_PMMP_COLLECTOR_PHASE3.md`. The DB agrees: 3,837 entries first seen between 20:42:13.228029 and 21:26:46.393733 UTC. A baseline is not a SearchRun and has no durable baseline-job ledger; no later successful full baseline is proved by the DB alone.

First-seen batches: 1,528 rows in the 20:00 UTC hour, 2,309 in the 21:00 hour on 2 October; one additional row on 3 October; 528 on 7 October. Four baseline rows have last-changed later than first-seen.

The latest successful business backfill is **#45**, 2026-10-02 22:51:04.611499–23:09:07.133763 UTC. DB counters and observations establish **10 persisted candidates, 7 NEW / 3 UPDATED**, all 10 observations in `manual_review`. Backfill metadata/log reconstruction records 3,837 listings considered, 2,873 cheap-prefilter skips and 964 eligible for detail; 440 enrichment successes, approximately 948 pipeline rejects, and one hard-policy keep plus nine review decisions. These reconstructed stage counts are not an exhaustive per-listing audit and do not perfectly reconcile into one outcome table. Run-level rejected count is zero because the custom backfill collector returns only kept candidates and its CLI metadata recording failed after persistence; rejects are represented in reconstructed logs/metadata instead.

Backfill #44 failed with a database error; #46 failed with `worker_interrupted`. No later successful backfill is retained. The 529 entries indexed after #45 were not covered by that backfill. The backfill CLI raises its in-process observation limit to at least 5,000; the ordinary index-discovery path does not.

### What can be established about never-evaluated listings

**The exact number and list of entries never evaluated by business policy is not recoverable from the current schema.** The index has no policy-evaluated timestamp, evaluation version, decision, processing status, originating run or retry marker. Rejected listings usually have no Result/ResultObservation. Traces are capped; #45 has reconstructed aggregate metadata, not a complete retained trace.

A conservative evidence search across Radar 1 Results, observation snapshots and retained traces found:

- 85 index identities with direct consultation-ID evidence.
- 1,011 entries matching either retained consultation identity or a normalized reference.
- **3,355 entries with no retained evidence under those matching rules.** This is an evidence gap, not 3,355 proven never-evaluated notices. Reference-only matches can collide across buyers, and absent traces can represent correctly rejected/pre-filtered entries.
- Of the 528 entries inserted during #54, 125 have some retained identity/reference evidence elsewhere and 403 do not. That does not imply the 125 were processed by #54, or that the remaining 403 were never considered by another process.

**Confirmed:** all 528 newly indexed entries were staged during #54's listing collection, before that run reached its business handoff. Every one has first-seen within its failure window; #54 has zero business candidates/traces, and sync never returned final counts. A later retry cannot identify them as unprocessed from the index table. Some were evaluated by legacy runs independently; for example `C01/2026` has prior/later evidence.

## 3. Local zero-run history

| Run | Actual recorded mode | Key evidence | Business outcome |
|---|---|---|---|
| #42 / #43 | `pmmp_index` | 3 pages, 30 UNCHANGED, no actionable entries; index 3,837 | 0 / 0 |
| #45 | Business backfill | Existing 3,837-row baseline considered | **7 / 3** |
| #47 | `pmmp_index` | 5 pages, 1 technical NEW, 49 UNCHANGED; one policy rejection | 0 / 0 |
| #48 / #49 | `pmmp_index` | 3 pages, 30 UNCHANGED; index 3,838 | 0 / 0 |
| #54 | `pmmp_index`, failed | Began with 3,838; 528 entries inserted during collection; no completed sync/handoff | 0 / 0 |
| #55 | `pmmp_index` | Index before 4,366; 3 of 407 declared pages, board count 4,070; NEW 0 / UPDATED 0 / UNCHANGED 30; `incremental_overlap` | 0 / 0 |
| #56 / #57 | **`legacy`** | Each examined 100, rejected 100, `candidate_limit`; 200 raw hits, 29 pre-final relevant candidates | 0 / 0 |
| #58 | **`legacy`** | Examined 100, rejected 100, `candidate_limit`; 200 raw hits, 25 pre-final relevant candidates | 0 / 0 |

Thus the local history does not support interpreting #56–#58 as zero incremental-index runs. Current local `.env` mode is `pmmp_index`; these historical runs recorded `legacy`. The initiating process's environment/override and whether another deployment shares this DB are **NOT VERIFIED**. Historical DB metadata establishes mode for those runs, not the currently running Vercel/Render configuration.

#58's 100 trace outcomes: 22 execution-only, 22 unrelated infrastructure, 21 irrelevant domain, 15 missing approved heritage/architecture context, 11 generic architecture, eight no-role, and one final validator rejection after collector review. None of the four requested references appears in #56–#58 retained traces. Their absence from those fetched/processed samples is not a new rejection of those opportunities.

## 4. Incremental completeness

**CONFIRMED BUG / observed false assumption:** the implementation treats three stable pages from the beginning as evidence that deeper discovery work can stop, but it never requests or verifies newest-publication ordering.

Public inspection on 9 October found **4,144 declared consultations** during the later sample (the earlier 14:29 UTC inspection reported 4,138; the board changes). First-page publication dates ranged from 10 September to 9 October. Deadline samples were:

| Page | Consultation ID | Publication | Deadline |
|---|---|---|---|
| 1 | 1040952 | 18/09/2026 | 25/11/2026 10:00 |
| 1 | 1043875 | 29/09/2026 | 25/11/2026 10:00 |
| 2 | 1027190 | 08/10/2026 | 23/11/2026 10:00 |
| 2 | 1041301 | 20/09/2026 | 20/11/2026 13:00 |
| 3 | 1038485 | 09/10/2026 | 19/11/2026 10:00 |
| 4 | 963011 | 24/09/2026 | 17/11/2026 11:00 |

The observed sequence is consistent with descending deadline order. All sampled sort icons use `arrow-tri-off.gif`, so there is no active explicit publication sort indicated by the inspected form. Do not infer the site's permanent sort contract from six pages; the direct evidence is sufficient to reject the collector's newest-first assumption.

An October publication can sit behind older publications because of its deadline. An edit to an old listing's object/buyer can leave its sort position unchanged; a deadline edit can move it toward either end. The site also exposes independent sort controls. New/changed entries therefore need not appear before three stable pages. No PMMP API contract proving that all amendments move to the front was found or assumed.

**Offline reproduction:** seeded an in-memory index with pages 1–3, each stable, followed by an unknown heritage study on page 4. The actual collector with scripted HTTP stopped after page 3 (`incremental_overlap`), NEW=0, with page 4 unvisited. No network or DB was used in this replay. This confirms incompleteness of the stopping rule, rather than relying on existing tests passing.

Current public-to-local comparisons also found missing identities on page 1 (1046876, 1047800, 1047840, 1044789) and page 6 (1047074, 1044869, 1044858, 1047209, 1047792). They demonstrate that an index with 4,366 historical entries can still omit current board entries. They do **not** prove that run #55 missed those particular identities on 7 October: the snapshot is later, the index has not been refreshed since #55, and subsequent stored runs used legacy mode.

**DESIGN RISK:** older detail-only changes are invisible to the listing fingerprint if the displayed listing fields remain the same. The listing parser sets estimated amount to None, and the table has no persisted estimate/document/status or policy-version fields. Estimate, regulations, lots, eligibility or DCE amendments may not trigger listing UPDATED. Reconciliation of listing rows alone does not automatically reevaluate an unchanged business entry.

**CONFIRMED code omission / DESIGN RISK:** reconciliation mode exists, but no scheduled reconciliation caller was found in `app` or `run_bot.py`. It cannot repair omissions automatically. A full listing reconciliation without a separate policy backlog still leaves technically unchanged-but-unprocessed rows skipped.

Public source: https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons

## 5. Four known opportunities

References in the index include display suffixes such as `145/2026 - ...`. An exact equality query on the clean reference initially returned no matches. This is **not absence**: identities were verified using consultation ID, URL and normalized display reference, with buyer/title checks to exclude `145/2026/EL`, `145/2026/SKTRA`, and `04/2026/AUSY`. Fingerprints for all 4,366 rows match their stored listing fields. Their current live fingerprint equality was not asserted.

All four index entries have last-seen and last-changed equal to their baseline first-seen timestamp below; incremental discovery has not refreshed these rows since that baseline.

| Reference | Index row / consultation | Index first/last-seen UTC | Business evidence and current status |
|---|---|---|---|
| `04/2026/AUS` | #3790 / 1036481 | 2026-10-02 21:26:17.002944 | Result #132; first persisted on #13; #45 UPDATED, relevant/manual review (`P2_REVIEW`, `REVIEW_AMBIGUOUS_RELEVANCE`). Still human PENDING, but deadline 2 October is expired and the pending queue appropriately hides it. |
| `42/2026/ADERFES` | #2965 / 1040346 | 2026-10-02 21:16:48.363061 | Result #167; #45 NEW/manual review; hard policy heritage keep, feedback `demote_keep_to_review`; recorded reason `ACCEPT_HERITAGE_PROFESSIONAL_SERVICE`. Human APPROVED. Deadline 8 October is expired as of inspection. |
| `145/2026` | #1853 / 1039623 | 2026-10-02 21:03:49.079875 | Result #164; #45 NEW/manual review; hard policy heritage keep, feedback `demote_keep_to_review`. Human APPROVED, active recorded deadline 15 October. Already persisted, not a fresh pending opportunity. |
| `04/2026/CA/BR/RGON` | #781 / 1032453 | 2026-10-02 20:51:08.495179 | Result #103; prior #11/#16/#17 observations, #45 UPDATED/manual review. Human APPROVED, recorded deadline 22 October. Current official-detail procedure is competition; title-only validator/queue keep `P1_CONCOURS`, while collector's broader corpus returns review. |

Business last-seen: #132 at 2026-10-02 23:09:05.572158 UTC; #167 at 23:09:01.926751; #164 at 23:08:55.479783; #103 at 23:08:52.716315. Earlier technical-index last-seen is not the business last-seen.

**WORKING CORRECTLY:** all four were evaluated sufficiently to be persisted by #45. None is missing from business persistence. Their current pending-list absence follows expiry or human APPROVED state. Feedback review demotion did not discard them. Relevant opportunities can remain public after a submission deadline; public-detail readability alone does not prove current eligibility.

Current public-detail replays used individual public reads, then `enrich_detail`, `verify_detail`, `_business`, and validators in memory; no real collector run was executed. Safi and Sidi Ifni remained validator-accepted with a missing-publication-evidence review reason; Settat and Meknes were rejected on expiry.

Official sources:

- Settat: https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036481&orgAcronyme=j8k
- Meknes: https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040346&orgAcronyme=g3h
- Safi: https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039623&orgAcronyme=j8k
- Sidi Ifni: https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032453&orgAcronyme=m8x

## 6. Business-policy consistency and overriding gates

### Core tracks

**WORKING CORRECTLY in targeted offline cases:** actual `evaluate_relevance` kept heritage rehabilitation studies and cultural/historical valorisation studies as P1_HERITAGE; a grand-museum architectural competition as P1_CONCOURS; a new university-campus architectural project as P1_MAJOR_ARCH. It rejected generic primary-school studies, an OFPPT competition and a small administrative building as generic architecture; ordinary road/sanitation studies as infrastructure; execution-only restoration works as pure execution. These are focused checks, not a complete recall benchmark.

Major architecture requires professional role, an approved major asset and scale or a verified estimate (default threshold MAD 20 million). Plausible major assets without verified scale can remain P2 review. Competition procedure alone does not rescue generic schools/OFPPT. Ordinary-building vocabulary can block a major classification even when a budget is large; whether a real mixed campus/strategic project is overblocked needs case-specific validation.

### Different callers use different evidence

**CONFIRMED behavior / DESIGN RISK:** collector `_business` includes PMMP activity domains, object, main category, procedure and buyer; `validators.business_relevance` uses title, raw listing evidence, buyer and location, excluding those structured PMMP fields. The queue uses title and optional persisted `project_scope`/`scope`, estimate/procedure, excluding buyer/raw detail/domain evidence. `enrich_detail` does not replace raw listing evidence with a canonical procurement-only scope. A decision accepted in one stage can be changed in another.

Actual public-detail comparisons:

- Settat: collector REVIEW versus validator KEEP. Generic activity-domain text includes topography and built heritage, affecting the collector's signals.
- Sidi Ifni: collector REVIEW versus validator KEEP/P1_CONCOURS. The generic architectural/topographic domain affects competition relevance; the object itself is an architectural corniche competition. It is still retained for review, so this is not a demonstrated total loss of this notice.
- `12/2026/DRANEFFM/SAP` (Tazekka ecotourism study): collector REVIEW on generic `patrimoine bati` activity-domain evidence, validator REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT on actual object. This disagreement is retained in #56–#58 traces and reproduced from the current detail page. Rejection may be correct for the actual object; the issue is misleading collector relevance and inconsistent evidence, not proof that this ecotourism notice should be accepted.

**DESIGN RISK:** the title-independent buyer corpus can lend heritage signals to unrelated ADER/Al Omrane work. Conversely, unconditional negative terms such as `securite` or `fournitures` reject before detail even when attached to an architectural/heritage professional mission. An offline mixed architectural-restoration/security example was rejected. No specific live false-negative caused solely by this vocabulary was established.

**NOT VERIFIED as a systematic bug:** the current queue hides 40 of 42 stored pending records under current policy, but those include legacy records captured under broader rules. Count alone does not establish that they should all be shown. Known requested entries have correct current queue-policy keep decisions; their pending absence follows expiry/approval.

### Additional validators and dedup

- Geography/source/procedure guards can override business keep. Missing publication evidence was review-only in the targeted active-detail replays; no blanket loss from this missing field was found.
- Confirmed expired deadline and closed/cancelled/awarded status reject appropriately. Detail verification can reject a notice when title/buyer/deadline evidence fails. Current C01 detail verification failed in the minimal replay; this does not establish a parser bug without a page-specific extraction audit.
- Policy rejects after enrichment carry metadata and trace reasons but do not persist a listing-level policy outcome.
- `_early_known` can skip official enrichment when a complete business discovery snapshot matches. An approved or previously rejected business record may therefore avoid fresh detail evidence. Technical index UNCHANGED skips even earlier and has no policy-version check. A policy correction does not automatically revisit old entries.
- Cross-radar dedup deliberately preserves the first owner card and records related extraction. No cross-radar suppression of the four requested entries was found.
- Optional AI failure usually degrades to human review; automatic AI acceptance is not necessary for persistence. Paid resolution can occur in normal runtime even in index mode, so this diagnostic did not invoke `_process` with live providers.

`C01/2026` provides a useful extra control: Result #170 was persisted on #52 and rediscovered on #53 as credible review; it is the sole current eligible pending card. Later #56–#58 traces reject it as generic architecture while the current stored full title/queue still gives major-architecture review. Different discovered snapshots/procedure/detail evidence can therefore produce conflicting outcomes for one identity. The exact cause of that historical rejection is **NOT VERIFIED**, because candidate raw evidence is not fully persisted. Do not label it never evaluated merely because index insertion occurred in failed #54.

## 7. Confirmed failure and presentation defects

### P0: partial sync is committed on failure — CONFIRMED BUG

`AgentOrchestrator._collect` invokes `record_progress()` from its `finally` block (`orchestrator.py:200–206`). That calls `_record_collection`, whose `db.session.commit()` is at line 164. Index classification uses that same session. `sync_listings(commit=False)` does not isolate those index mutations.

If PMMP fails after some pages, no ListingSyncResult/actionable list reaches `pmmp_index_discovery`, but the finally progress commit persists staged NEW/UPDATED rows. The later safe-fail rollback cannot undo the previous commit. Similarly, normal progress commits can precede downstream validation/persistence failure.

Read-only DB evidence: #54 started 12:22:56.411550, failed 12:32:07.077561 UTC on 7 October. All 528 added rows first appeared between 12:23:06.127144 and 12:32:04.681174, inside that run window. #54 recorded index-before 3,838, no finalized sync metrics/candidates; #55 recorded 4,366. No business backfill covered this new batch afterwards.

Mock-only replay of actual `_collect`/`_record_collection`: fake collector staged 528 fake index writes and raised a scripted pagination error; actual finally path committed all 528, then raised CollectorError. No database was involved. The precise original external error causing #54 is **NOT VERIFIED** from its generic stored error message.

### P0: candidate cap consumes changes without policy completion — CONFIRMED BUG

`pmmp_index_discovery` syncs all visited listings first, then iterates actionable entries. `_observe` returns None after 100 examined candidates and marks `candidate_limit`. Already synchronized entries remain committed even when never filtered/enriched. A later unchanged sync does not retry them. The cap counts observed candidates, including rejected noise and some resolution observations, not just kept opportunities.

Offline replay of `_observe` at examined=100 rejected a further heritage-study observation with `candidate_limit`. There is no persistent unprocessed queue. This is a reachable code defect, **not an assertion that #55–#58 historically hit this defect in index mode**; #56–#58 hit the same cap in legacy mode, while #54 failed before any policy handoff.

### P1: exact-run web membership loses manual-review observations — CONFIRMED BUG

`api/results.py:52` uses `('new','updated')`; `results.py:save` selects `manual_review` when relevant analysis needs human review, and `observe` stores that state. SearchRun still increments business NEW/UPDATED. Compiled SQL from the actual web helper contains no `manual_review` state.

All 70 retained Radar 1 producing observations are `manual_review`. #45 produced ten such observations while counters reported 7 NEW/3 UPDATED; the web membership filter cannot select any of them. Telegram's `core/review.py:351` correctly includes `manual_review`, demonstrating divergent contracts. API tests manually construct `new`/`updated` observations rather than exercising this persistence-to-web path.

At today's snapshot, no #45 candidate is both pending and otherwise queue-eligible, so an empty current #45 pending page alone is not evidence of the display bug. The defective state contract is independently confirmed. It affects presentation, **not the zero SearchRun counters of #56–#58**.

### P2: displayed pending count differs from visible queue — CONFIRMED BUG

`api/radars.py:_radar` counts raw PENDING rows (42); `api/results.py:_status_rows` applies current eligibility (one). The frontend dashboard and queue can therefore disagree. This does not cause backend NEW/UPDATED zeros.

## 8. Production-specific risks established from code

| Area | Assessment | Evidence / practical implication |
|---|---|---|
| Startup/migrations | DESIGN RISK | `wsgi.py` creates the app; startup initializes migrations but does not run upgrades or validate baseline completeness. `/ready` checks DB availability, not index coverage or policy backlog. Local migration exists; deployed migration state remains NOT VERIFIED. |
| Environment | DESIGN RISK / NOT VERIFIED for production | Missing discovery mode defaults to legacy. Default config and actual local recent-run metadata differ. Changing a local env file does not update already-running processes. Render effective config/deployed revision cannot be inferred here. |
| Durable index | WORKING CORRECTLY for technical persistence | PostgreSQL table and unique identity constraints survive process restarts. All stored fingerprints are internally consistent. Persistence does not imply policy completion; failed-run commits are a separate confirmed defect. |
| Baseline/backfill | DESIGN RISK | Baseline creates index memory only; business backfill is a separate manual CLI step. No startup enforcement requires both completed. Empty index produces a warning/zero candidates; incomplete nonempty index is not detected. |
| Reconciliation | DESIGN RISK | Mode implemented but no scheduling caller found; no watermark contract or guaranteed deeper amendment coverage. No policy-version retry on unchanged listings. |
| Jobs | DESIGN RISK | LocalJobRunner is an in-process ThreadPoolExecutor (two workers, capacity five), not durable. Gunicorn/Render restart or worker loss can interrupt work. Active-run DB constraint/claim protects duplicate execution. Stale recovery occurs on the next reservation, default 120 minutes, not continuous resumption. Local #46 interruption is recorded; production interruptions remain unverified. |
| Transactions/network | CONFIRMED BUG / DESIGN RISK | Index and progress share commits; partial work can become permanent before policy. Long DB transactions span PMMP sync/detail reads. #44 has a DB failure; historical backfill records idle-in-transaction problems. Exact deployment DB timeout settings were not inspected. |
| Errors and completeness | CONFIRMED observability weakness | Completed can coexist with degraded health, cap truncation and zero candidates. #54 stores generic collector failure without sync page totals or original error; index changes survive. #45 metadata was reconstructed after a CLI recording failure. |
| Frontend diagnostics | DESIGN RISK | UI displays NEW/UPDATED and status but does not render collector mode, page coverage, sync counts, rejection breakdown or truncation. Run type omits those details even though backend JSON contains metadata. Zero results are ambiguous to the user. |
| Display contracts | CONFIRMED BUG | Manual-review exact-run omission and raw pending-count discrepancy can make a populated backend appear empty. Neither changes stored run NEW/UPDATED counters. |

## 9. Prioritized minimal fix plan — not implemented

1. **P0: separate technical observation from completed business evaluation.** Persist per-listing policy state/version and evaluated fingerprint (or a durable work queue). NEW/UPDATED indexing must enqueue work; mark it complete only after an explicit policy outcome/persistence. Failures, caps and detail-access errors must remain retryable. Record automatic rejects too. An unchanged listing with pending/stale evaluation must still be processed. This addresses failed-run commit loss, candidate overflow and baseline-without-backfill together.
2. **P0: prevent accidental partial-sync consumption.** Put sync in an isolated transaction/session or explicitly roll back partial mutations before progress failure commits; ensure successful sync plus failed business processing retains durable pending work. Logging a failure is not enough once progress has committed index changes. Add a focused mock/fault-injection regression for the exact finally path and for restart after partial business work.
3. **P1: restore complete board coverage.** Stop treating three stable deadline-ordered pages as a proof of completeness. Verify/request publication ordering if relying on a watermark for new insertions, and retain periodic full reconciliation for deeper modifications/reordering. Feed reconciliation changes and pending policy work into the business pipeline. Increasing overlap alone is not a completeness fix.
4. **P1: fix observation-state contract at the web boundary.** Include producing manual-review observations using their recorded NEW/UPDATED discovery snapshot; retain exclusions for unchanged and nonpending records. Verify with real ResultService output reaching the web filter, not hand-built `new` observations.
5. **P1: unify procurement-only policy evidence.** Use a single canonical scope across collector, validators, persistence and queue. Distinguish actual project scope from buyer mission/activity categories; preserve competition/procedure/verified estimates. Recheck the four requested cases, generic schools/OFPPT, infrastructure and mixed relevant/negative vocabulary offline. Keep adaptive feedback review-only.
6. **P2: improve diagnostics and count consistency.** Expose mode, pages, stopping reason, truncation, actionable versus evaluated counts, per-stage rejection reasons, policy backlog and index-before/after. Label degraded/partial completion explicitly. Make dashboard queue totals match the queue's eligibility rules or label raw backlog separately.
7. **P2: deployment guardrails and reliable jobs.** Validate schema and baseline/policy readiness, require explicit deployment mode, schedule reconciliation, and move long work to durable jobs or persist resumable work/heartbeats. Verify production DB identity and effective config separately before applying any production remedy.

Before any remediation that writes data, identify the exact production connection and deployed revision, obtain a verified read-only production snapshot, and compare its baseline and policy backlog independently. Do not copy local counters or claim that re-running a full listing baseline alone repairs unevaluated policy work.

## 10. Validation and limits

Completed checks: full relevant code-path inspection; enforced read-only SQL for local index/results/observations/runs; known-reference identity disambiguation; all 4,366 fingerprint internal-consistency checks; pure queue replay; focused scripted incremental/cap/transaction replays; policy matrix; public board ordering samples; six selected public official-detail reads. No application test suite was run against this DB, and no new test or application file was created.

The first DB connection attempt failed because Neon pooler rejected startup `statement_timeout` options. The diagnostic then used explicit `BEGIN ... READ ONLY` successfully. One query alias was corrected before continuing; neither failure wrote records. A first mock harness lacked required orchestrator fields and did not exercise the failure commit; the corrected harness reproduced the actual 528-write commit path. These failed attempts are not counted as diagnostic evidence.

Limitations: no production DB or Render shell access; no full current-board crawl; no guaranteed public sort contract; incomplete historical per-listing policy traces; no exact never-evaluated count; no historical raw candidate payload for every reject. Missing current board entries were demonstrated, but the historical cause of each omission is not inferred. The requested four opportunities are all known and persisted, and do not independently demonstrate current actionable discoveries.
