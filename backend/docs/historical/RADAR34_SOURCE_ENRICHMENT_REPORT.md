# Radar 3 / Radar 4 source enrichment — 13 September 2026

The isolated live sample now contains **3 VERIFIED_CURRENT officeholders** and **1 officially verified PUBLISHED law**, compared with zero of each before enrichment. No IN_FORCE claim was made. Both collectors remain PARTIAL because source coverage is incomplete.

No production searches, production results, database resets, migrations or Telegram messages were performed. Measurements below are from the final direct-only isolated run, not web research used to curate the registry.

## 1. Source registry additions

`app/sources/curated_institutions.py` stores institution identity, official evidence domain, scoped role pattern, governance/organization/leadership/appointment/news/project URLs where known, refresh interval, priority and enabled state. Names are extracted from fetched evidence, never hard-coded in the registry.

| Institution / source | Added monitoring | Interval |
|---|---|---:|
| Fondation Nationale des Musées | Official dated partnership article; governance and news URLs recorded | 7 days |
| Conseil Communal d’Essaouira | Official national-portal report naming the council president as signatory | 7 days |
| Culture Ministry | Official dated bilateral-meeting report explicitly naming the minister | 7 days |
| Agence Urbaine d’El Jadida-Sidi Bennour | Governance/leadership page | 7 days |
| APDN | Registry entry disabled: archive date contamination | Disabled |

Existing government composition, Al Omrane, national appointments and Culture Ministry news sources remain. Radar 3's domain configuration now permits FNM, AUEJSB and the current Culture Ministry domain. No Radar 1/2/5 domain configuration changed. FNM's additional governance/news addresses are recorded for maintenance; this bounded run fetches its dated evidence URL, not every optional registry address.

`app/sources/curated_legal.py` adds a reviewed link from heritage law 33.22 to official Arabic BO 7415, refreshed every 30 days. SGG's consolidated-law index is added as a reference lookup, refreshed every 14 days. It does not independently establish IN_FORCE. The Parliament adapter can extract explicit presented/committee/chamber-adopted/parliament-adopted stages from scoped official detail pages. The unavailable index remains configured and no live parliamentary progression is claimed.

These are ordinary sources using the existing source-state/cache service. The existing `RADAR3_SOURCES` and `RADAR4_SOURCES` overrides control intervals, priorities and enabled flags. New verified URLs are now persistent code registry entries, so scheduled runs do not rediscover them through paid search.

## 2. Radar 3 official coverage

Eight enabled source attempts: seven returned successfully and Culture Ministry news failed. Government composition and the El Jadida governance page were checked; the latter yielded no safely extractable role evidence. Three recent official activity pages supplied named role evidence. The existing national appointments index was checked; no fresh appointment was verified.

Final counters: 7 institution-candidate checks, 5 retained institution profiles, 3 VERIFIED_CURRENT, 1 PROBABLY_CURRENT, 1 UNVERIFIED, 0 OBSOLETE in the retained sample, 0 appointments detected. Candidate checks are not unique monitored-institution counts. The legacy `decision_makers_identified=0` counts standalone PERSON records; the three verified holders are correctly attached to institution profiles.

No separate live generic/recruitment rejection count was emitted. Tests demonstrate those exclusions; zero is not substituted for an unmeasured count. APDN is excluded from monitoring because its archive template shows recent dates above historical events, including a 2011 board meeting. Those template dates are not evidence of current officeholders.

## 3. VERIFIED_CURRENT officeholders found

Verification date: **2026-09-13**, using the existing maximum 180-day evidence age. Confidence: 0.95 for each.

| Person | Explicit role / institution | Evidence date | Official evidence |
|---|---|---|---|
| Mehdi Qotbi | Président, Fondation Nationale des Musées | 2026-04-13 | [FNM partnership signature](https://fnm.ma/actualites/35) |
| Tarik Ottmani | Président, Conseil Communal d’Essaouira | 2026-04-14 | [Official account of museum partnership](https://www.maroc.ma/fr/actualites/un-partenariat-strategique-pour-la-valorisation-du-musee-sidi-mohammed-ben-abdellah-dessaouira) |
| Mohamed Mehdi Bensaid | Ministre de la Jeunesse, de la Culture et de la Communication | 2026-07-16 | [Official bilateral meeting](https://www.maroc.ma/fr/actualites/renforcement-des-relations-bilaterales-entre-le-maroc-et-la-france-dans-le-domaine-de-la-culture) |

The first two articles identify responsible signatories, not merely event attendees. The third explicitly names the minister conducting the meeting. Titles remain as written in the evidence. Normalized role metadata supports the requested director/president/technical/heritage/project/procurement categories and leaves uncertain or unmapped titles unset. A minister's Culture and Communication portfolio is not treated as a communications-contact job.

## 4. Unresolved current roles

Fatima Ezzahra El MANSOURI remains PROBABLY_CURRENT because the governance evidence is undated. Al Omrane remains UNVERIFIED with no invented holder. El Jadida remains a coverage gap: its retrieved governance description did not supply a safely extracted named current director. APDN remains disabled pending a reliable dated source.

The existing resolver still prefers the freshest official evidence and rejects obsolete roles. No live replacement event occurred. Dated registry articles will age out; maintenance must add subsequent official evidence rather than extend dates or assume continuity.

## 5. Radar 4 official legal-source coverage

Seven configured sources checked: BO 7415, the recent French BO listing, SGG drafts, SGG consolidated laws, Parliament, CESE and HCP. The first four succeeded; Parliament, CESE and HCP failed. No new ministry/strategy source was enabled without sufficient reviewed evidence.

Two bulletins were successfully parsed: **7415 (2025-06-23)** and **7526 (2026-07-16)**. The bounded recent listing also attempted another issue without successfully retaining it. The final run made 11 direct HTTP requests, including document verification. SGG consolidated lookup checked two relevant references; unresolved consolidated entries are not added as extra ambiguous candidates, avoiding unnecessary AI work.

The Arabic BO adapter requires the publication formula, the own law reference, the law label and heritage subject together in the document, plus the expected issue number. A changed/unreadable endpoint fails verification. Reference normalization handles spaces, dots, hyphens, slashes and Arabic decimal digits. Effective dates are never inferred from a promulgation or publication date.

## 6. Verified status counts

| Final retained status | Count |
|---|---:|
| DRAFT | 11 |
| UNDER_PREPARATION | 0 |
| PUBLIC_CONSULTATION | 0 |
| ADOPTED | 0 |
| PUBLISHED | 1 |
| IN_FORCE | 0 |
| IMPLEMENTATION | 0 |
| POLICY_SIGNAL / ANNOUNCED | 0 |

**Loi n° 33.22 relative à la protection du patrimoine** is verified PUBLISHED in [official BO 7415](https://www.sgg.gov.ma/BO/AR/3111/2025/BO_7415_Ar.pdf), dated 23 June 2025. The stored excerpt preserves the Arabic promulgation/publication evidence. The French label is a curated descriptive title, not an assertion that this is a French BO edition. Status confidence is 0.98. Effective date remains null.

Publication verification is **1/12 retained candidates (8.33%)**. Current effectiveness remains unresolved for all 12. The other 11 records have official evidence of a listed draft version, not proof that the legislation remains a draft today. Missing own references and inaccessible/scanned documents prevent safe joins. The combined unrelated/nonofficial exclusion counter was 297; it is not a separately measured count of unrelated laws.

## 7. Status-transition matching

Live evidence proves publication of 33.22. It does **not** prove that a particular previously unnumbered SGG draft is the same record: similar heritage titles alone were not used to force a merge. Such unresolved entries may describe related stages and still require an exact-reference link.

Existing lifecycle tests prove DRAFT → ADOPTED → PUBLISHED → IN_FORCE updates one record for a stable legal identity. New source tests prove Arabic publication evidence yields PUBLISHED with no fabricated effective date, and reference variants normalize consistently. Parliament stage tests distinguish one chamber from definitive parliamentary adoption. Parliamentary publication dates are not silently copied into adoption dates. No live parliamentary transition or current entry-into-force example is claimed.

## 8. Paid search / OpenAI / tokens

| Final live isolated run | Radar 3 | Radar 4 |
|---|---:|---:|
| Retained candidates | 5 | 12 |
| Direct HTTP requests | 8 | 11 |
| Paid search requests | 0 | 0 |
| OpenAI requests | 0 | 0 |
| Input tokens | 0 | 0 |
| Output tokens | 0 | 0 |
| Total tokens | 0 | 0 |

Direct HTTP is not OpenAI usage. Compared with the preceding hardening sample's 3/10 direct requests, enrichment adds 5/1 direct requests and no measured paid cost. No full page or PDF was sent to AI. Normal paid-search budgets remain 1 per radar, unchanged. The live runner explicitly disables paid search and AI; it does not measure the cost of an ambiguous future production fallback. Curation included separate web discovery and a six-source direct inspection, outside these per-run measurements.

## 9. Replay / memory proof

| Exact captured snapshot replay | Radar 3 | Radar 4 |
|---|---:|---:|
| First replay: new rows | 5 | 12 |
| Second replay: new rows | 0 | 0 |
| Existing duplicates recognized | 5 | 12 |
| Final stored rows | 5 | 12 |
| Second paid / AI / input / output | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| First-seen, content hash, review state preserved | Yes | Yes |

Recognized duplicates are existing records, not inserted duplicate rows. Last-seen advanced or remained equal. Separate immediate cached dry-runs made **zero direct HTTP, paid search, AI or token usage**. Replay supplied the captured candidates directly, without fetching sources. Existing unchanged-item analysis skipping and DB review semantics remain untouched.

## 10. Tests and protected scope

**450 tests passed in 22.63 seconds**, including 30 new source-enrichment cases. Compilation passed. `pip check` returned “No broken requirements found.” New tests cover scoped recent role evidence, institution-specific signatories, title order, authors/recruitment, missing dates, role normalization, Arabic/French reference variants, Arabic publication proof, consolidated lookup safety and parliamentary stages. Prior replacement/conflict/obsolete/lifecycle tests also passed.

SHA-256 comparison covered 136 pre-existing application/migration files: 129 were unchanged. The seven changed files are Radar 3/4 source catalog/parsers, their collector integration, role/reference normalization, and the two Radar 3 domain defaults in configuration. Three source modules were added. Radar 1/2/5 implementations, Telegram, multi-user behavior, DB models/migrations/services, deduplication, source-state/cache implementation, review lifecycle and shared cost orchestration remain unchanged.

## 11. Remaining source limitations

- Parliament, CESE, HCP and Culture Ministry news remain unavailable in the final sample. A successful index fetch does not guarantee useful role evidence, as El Jadida demonstrates.
- The curated set is intentionally small. Optional registry URLs are not a broad crawler; new evidence pages still require maintenance as sites and officeholders change.
- PDF reads remain bounded to 5 MB and 30 pages. The Arabic publication support is scoped to reviewed heritage evidence; it is not a general Arabic legal-effectiveness parser or OCR service.
- Existing source state preserves health, last_checked_at, content_hash, ETag and Last-Modified. It has no separate last_success_at column; none was invented or added through a DB migration. PARTIAL is reported at collector level; failed sources keep existing FAILED/BLOCKED/cooldown behavior.
- Unnumbered historical drafts cannot safely be merged with a published law based only on subject similarity. Publication proof is not proof of present applicability, unrepealed status or a verified effective date.

## 12. Is Radar 3 now production-ready?

**The intended current-role quality is demonstrated for this small monitored set: three verified holders. Unqualified production readiness is not claimed.** Overall source health remains PARTIAL, additional institution categories remain unresolved, and the registry needs ongoing dated-evidence maintenance. The confirmed/probable/unverified distinctions are supported by the live sample.

## 13. Is Radar 4 now production-ready?

**Not for comprehensive current legal-effectiveness verification.** It now demonstrates authoritative publication beyond DRAFT at zero measured paid usage. IN_FORCE remains unproven, parliamentary coverage is unavailable, and historical draft-to-law links remain incomplete. These are reported as source/evidence limits rather than manufactured success examples.

Artifacts: `audit-output/source-enrichment-quality.json` (live candidates, source evidence and replay), `audit-output/source-enrichment-summary.json`, `audit-output/source-enrichment-tests.txt`, `audit-output/source-enrichment-scope-check.json`. Reproducible isolated runner: `scripts/validate_source_enrichment.py`.
