# Radar 3 / Radar 4 quality hardening — 12 September 2026

Evidence handling improved, but the live sample does **not** establish production readiness for verified current leadership or current legal effectiveness. Both collectors remain PARTIAL. No production results, migrations, or Telegram messages were written. Live validation used public direct HTTP reads, disabled paid search and AI, and a disposable SQLite database.

## 1. Radar 3 quality before / after

Baseline: `audit-output/institution-policy-quality.json`. Final sample: `audit-output/role-status-quality.json`.

| Measured outcome | Before | After |
|---|---:|---:|
| Retained institutions | 1 | 2 |
| Confirmed current officeholders | 0 | 0 |
| Probably current, with warning | 0 | 1 |
| Retained profiles without verified holder | 1 | 1 |

The collector now records explicit role evidence, its source type and date, verification date, confidence and currentness. Undated governance evidence cannot establish VERIFIED_CURRENT. Confirmed flags also fail validation when dated evidence is missing or stale. A profile without a verified holder retains “Responsable actuel non vérifié”. Telegram rendering code was not changed; warnings travel in existing title/activity fields.

Final counters: 4 institution-candidate checks (not four unique institutions), 2 retained profiles, 0 verified holders, 1 probable holder, 1 unverified profile, 0 obsolete holders in the retained sample, 0 appointment changes. The live artifact has no separate generic/recruitment rejection counters; those exclusions are demonstrated by tests, not a claimed live rejection count. The older `officeholders_unverified=3` counter counts intermediate candidates, not final unique profiles.

## 2. Verified current officeholders

**None verified in the live sample.** Fatima Ezzahra El MANSOURI appears on the official government composition page as minister responsible for territorial planning, urbanism, housing and city policy. The role block is undated: retained as PROBABLY_CURRENT, confidence 0.65, with an explicit non-confirmation warning. Fetch date is not used as appointment/evidence date. [Official government composition](https://www.maroc.ma/fr/le-maroc/gouvernement).

## 3. Unresolved institutions

Al Omrane remains an institution profile with no asserted current person. Its official mission page supports institutional relevance, not current leadership. [Al Omrane profile](https://www.alomrane.gov.ma/Le-groupe/A-propos).

The urbanism ministry still needs a recent dated official role cross-check. Culture ministry coverage remains unresolved: its news source fails the existing domain configuration, and the existing institution URL suppression retains only one profile from the shared government page. Deduplication and configuration were deliberately preserved. This limits multi-institution coverage from a single governance URL.

## 4. Appointment / role-change handling

The resolver uses newest official evidence within an institution/role slot, with governance/organigram priority for equally dated evidence. Old evidence (over 180 days), departure evidence, invalid roles and conflicting equally ranked/equally dated names cannot confirm a current holder. Recent professional evidence is only a warned fallback when official evidence is absent. Explicit interim evidence is preserved.

Tests prove that a replacement updates the existing institution row, returns UPDATED/PENDING, and removes the old name from the visible decision-maker list. Role history remains in metadata. The live sample contained no actual replacement. Automatic discovery of new departments, all role wording variants and every replacement remains incomplete; the resolver tests do not prove comprehensive discovery. Current activity cross-checking is bounded and requires a matching known governance name; a differently named replacement still needs discovery evidence.

## 5. Radar 4 quality before / after

| Measured outcome | Before | After |
|---|---:|---:|
| Retained official draft versions | 11 | 11 |
| BO documents successfully read | 0 | 1 |
| Exact-reference publication checks on retained drafts | 0 | 0 |
| Confirmed published retained texts | 0 | 0 |
| Confirmed in-force retained texts | 0 | 0 |

Added PUBLISHED separately from ADOPTED and IN_FORCE, and ANNOUNCED for non-legal policy items. Publication requires an exact instrument reference and type in an official BO PDF heading; incidental mentions do not suffice. Entry into force requires an explicit own-instrument clause with an effective date no later than verification date. Validators reject unsupported publication sources and missing/future effective dates. Official evidence is handled deterministically.

The BO adapter uses the public SGG listing, preserves signed historical timestamps, and converts publication dates to Morocco's calendar date. Regression coverage includes historical 1912 timestamps and BO 7526's 16 July 2026 date.

## 6. Legal-status verification rate

All 11 retained items have official SGG evidence that the linked version is a draft: **11/11 (100%) for the status of that listed version**. This does not establish their present legislative status. All carry a warning that subsequent adoption and current effectiveness are unverified.

**Current publication/effectiveness verification: 0/11 (0%).** All retained drafts lack a verified own-instrument reference in the bounded extraction. References inside titles describing an amendment to another decree are not assumed to identify the amendment itself. No exact-reference publication matches could be performed. Finding nothing in a bounded BO sample must never be reported as proof of non-publication.

Final statuses: DRAFT 11; ADOPTED 0; PUBLISHED 0; IN_FORCE 0; strategies 0; studies 0. Present legal stage remains unresolved for all 11. The combined unrelated/nonofficial rejection counter is 337; it is not an independently measured count of unrelated laws alone.

## 7. Representative examples and manual inspection

- Cultural, natural and geological heritage protection: official Arabic draft listing retained; current adoption/effectiveness unresolved.
- Organisation des opérations de la construction: linked French draft retained. The fetched PDF produced no extractable text; `29.18` in its filename is not promoted to verified evidence.
- Amendment concerning BTP enterprise qualification: a referenced existing decree does not establish the amendment's own legal reference or effectiveness.
- BO 7526: successfully parsed the bounded first 30 pages, with publication date 16 July 2026. No relevant retained draft was verified against it. [Official BO 7526](https://www.sgg.gov.ma/BO/FR/2873/2026/BO_7526_Fr.pdf).

ADOPTED → PUBLISHED → IN_FORCE examples are **synthetic tests**, not live Moroccan-law assertions. Tests demonstrate that parliamentary adoption alone is insufficient, publication without an effectiveness clause remains PUBLISHED, future effectiveness remains PUBLISHED, and supported transitions update one database row. [Official draft listing](https://www.sgg.gov.ma/Legislation/Avant-Projets.aspx).

## 8. Official-source coverage

| Radar | Healthy indexes | Unavailable indexes | Overall |
|---|---|---|---|
| 3 | Government composition; Al Omrane; Morocco appointments | Culture ministry news | PARTIAL |
| 4 | BO French edition listing; SGG drafts | Parliament; CESE; HCP | PARTIAL |

Radar 3 made 3 actual direct HTTP requests. The fourth configured source was unavailable without a successful fetch. No matching recent official-activity links survived the bounded cross-check filter in the final sample.

Radar 4 attempted 5 indexes, 2 BO PDFs and 3 draft PDFs (10 HTTP requests). One BO PDF and two draft PDFs were successfully retained by the verifier. BO 7522-bis and the heritage draft were not retained successfully within the access/size bounds. The helper limits each document to 5 MB and the first 30 PDF pages; BO 7526 has more pages. Arabic/scanned content is not OCR-processed. These are coverage limits, not evidence of legal absence.

## 9. Cost metrics

| Final isolated live run | Radar 3 | Radar 4 |
|---|---:|---:|
| Retained candidates | 2 | 11 |
| Direct HTTP requests | 3 | 10 |
| Paid search requests | 0 | 0 |
| OpenAI requests | 0 | 0 |
| Input tokens | 0 | 0 |
| Output tokens | 0 | 0 |
| Total tokens | 0 | 0 |

Direct HTTP requests are not OpenAI requests and incur no OpenAI token usage. Paid search and AI were explicitly disabled for live validation; these measurements do not estimate ambiguous production AI usage. Existing normal search budgets remain 1 per radar, with no fallback when direct yield suffices. Shared cost logic is unchanged. Evidence extraction adds bounded direct fetches and the local `pypdf` dependency, not a paid service.

## 10. Second-run memory proof

| Exact snapshot replay | Radar 3 | Radar 4 |
|---|---:|---:|
| First replay: new rows | 2 | 11 |
| Second replay: new rows | 0 | 0 |
| Second replay: existing duplicates recognized | 2 | 11 |
| Final stored rows | 2 | 11 |
| Second paid / AI / input / output | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| First-seen, content hash and review state preserved | Yes | Yes |

Duplicate counters mean existing rows recognized, not duplicate rows inserted. Last-seen advanced or remained equal. Separate immediate cached dry-runs made zero direct HTTP requests, paid searches, AI calls and tokens. Exact snapshot replay avoided collection entirely. Existing source cache and deduplication implementation were not modified.

## 11. Tests and scope verification

Full suite: **420 passed in 21.55 seconds**, recorded in `audit-output/role-status-full-tests.txt`. Compilation: `python -m compileall -q app scripts tests` passed. Dependency check: `python -m pip check` returned no broken requirements. New cases cover current-role recency/conflicts, authors/recruitment, interim appointment, replacement identity, unsupported confirmed flags, draft/publication/effectiveness boundaries, legal transitions, unrelated laws, strategies and BO calendar dates.

All **82 protected files** matched pre-pass SHA-256 hashes: Radar 1/2/5 modules, Telegram, database models/migrations/services, shared collection/cache adapter, configuration and registry. Evidence: `audit-output/role-status-protected-check.json`. Shared source-catalog additions are restricted to Radar 3/4. No production migration or messaging was performed.

## 12. Remaining limitations / readiness

The live evidence proves safer uncertainty handling and bounded official-source verification, but not the requested breadth of confirmed current people or current legal statuses. Neither radar is declared production-ready for those stronger claims.

Coverage depends on accessible dated leadership pages, instrument references readable from official documents, broader relevant BO history, and accessible Parliament/ministry sources. The current parser is intentionally conservative and incomplete for scanned/Arabic PDFs, complex effective-date clauses, some legal heading formats and names appearing before/after roles in unsupported arrangements. Existing URL-based institution suppression and historical records that acquire a previously missing legal reference also need attention before claiming universal update-without-duplication behavior; the current tests prove stable institution/reference identities, not every historical identity migration. Those core deduplication changes are outside this authorized pass.

Machine-readable live documents, candidates, counters and replay evidence: `audit-output/role-status-quality.json`. Runner: `scripts/validate_role_status_quality.py`. No paid production run is needed to inspect this report or its artifacts.
