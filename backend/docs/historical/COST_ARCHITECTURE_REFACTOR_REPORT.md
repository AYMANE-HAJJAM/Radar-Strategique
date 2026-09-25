# Direct-source cost architecture refactor

Date: 2026-09-12

## Cause of the previous cost

Radars 2–5 used OpenAI web search as their default discovery loop, and Radar 1 used five resolution searches after direct collection. A full cycle therefore made 27 web-search-backed OpenAI requests. Web search supplied most of the roughly 300,000 input tokens; shortening classification prompts could only reduce output and classification overhead.

## Implemented architecture

Normal execution now follows: official source registry → conditional local HTTP fetch → local HTML/table/feed/JSON extraction → normalized item-set hash → deterministic radar rules and early DB dedup → bounded paid-search fallback only below the direct-yield threshold → optional ambiguity analysis.

`BaseSourceAdapter` supports `HTML_LIST`, `HTML_ARTICLE` through the generic HTML representation, `TABLE`, `RSS`, `ATOM`, and `JSON_API`; the interface is open to custom adapters. It performs GET-only requests with a timeout, a same-domain redirect limit, a response-size limit, ETag and Last-Modified request headers, 304 handling, and per-source refresh cooldowns. List hashes contain normalized title, date, reference, and URL, so navigation/footer changes do not invalidate a source.

The `source_states` table persists source URL, name, ETag, Last-Modified, content hash, last check/change time, source health, and HTTP status. The migration is `b72c1d4e8f20_direct_source_state.py`. A failed or blocked source observes its refresh cooldown rather than causing immediate paid-search expansion.

Early item dedup remains at the collector boundary, followed by the existing database identity lookup before AI. Unchanged items reuse their stored analysis. AI inputs remain bounded to compact structured evidence; Radar 1 AI is disabled by default and Radars 2–5 use conditional AI.

Normal fallback budgets are 2, 2, 1, 1, and 2 paid searches for Radars 1–5. Direct yield suppresses the fallback entirely. `--direct-only` disables paid search and AI. CLI-only `--deep-search` restores the larger diagnostic budgets and requires both `--isolated` and `--dry-run`. Telegram uses normal low-cost defaults.

## Direct sources

| Radar | Direct sources/adapters |
|---|---|
| Markets | Existing PMMP public listings/details, BDC/list pages, Marché Facile and institutional procurement adapters; paid discovery and resolution capped to two each in normal mode |
| Projects | Morocco official news index pages, Ministry of Culture news, Al Omrane news and APDN project news; relevant article pages are fetched locally within a bounded detail budget |
| Institutions | Morocco official appointments/news, Ministry of Culture news and Al Omrane governance with 7–21 day refresh intervals |
| Policies | SGG draft-law table, Parliament legislation, CESE publications and HCP publications; SGG table extraction produced useful records without search |
| Funding | World Bank Morocco Projects JSON API, AfDB Morocco, EIB Morocco and EBRD Morocco; World Bank project IDs, amounts, status, approval/closing fields and beneficiary fields are parsed locally |

Some configured sites blocked or failed the Python client during the sample. Per-source health records expose those failures. Healthy sources continued without automatic broad escalation. The strongest observed direct connectors were the existing Radar 1 adapters, Morocco official news, SGG, World Bank, and EBRD.

## Measured baseline versus low-cost mode

All after measurements used isolated temporary databases and dry-run mode. No production Telegram search or production database write occurred. OpenAI requests equal paid-search requests in this sample because classification calls were zero.

| Radar | Direct HTTP after | Paid search before | Paid search after | OpenAI before | OpenAI after | Input before | Input after | Output before | Output after | Kept before | Kept after | Health after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Markets | 60 | 5 | 2 | 5 | 2 | 26,226 | 10,490 | 384 | 141 | 20 | 28 | PARTIAL |
| Projects | 6 | 6 | 2 | 6 | 2 | 71,459 | 26,239 | 1,310 | 354 | 1 | 2 | HEALTHY |
| Institutions | 2 | 5 | 1 | 5 | 1 | 65,207 | 12,993 | 4,607 | 955 | 4 | 2 | HEALTHY |
| Policies | 4 | 5 | 0 | 5 | 0 | 57,422 | 0 | 3,495 | 0 | 3 | 2 | HEALTHY |
| Funding | 4 | 6 | 0 | 6 | 0 | 79,275 | 0 | 7,824 | 0 | 17 | 24 | HEALTHY |
| **Total** | **76** | **27** | **5** | **27** | **5** | **299,589** | **49,722** | **17,620** | **1,450** | **45** | **58** | — |

- Input-token reduction: **83.40%**.
- Total-token reduction: **83.87%** (317,209 → 51,172).
- Paid-request reduction: **81.48%** (27 → 5).
- Kept results in the live samples: **45 → 58**. Counts are not a fixed recall benchmark because live source and search results vary.

Representative checks included open architecture studies, rehabilitation/restoration tenders, a launched Medina heritage study, current institutional/leadership signals, SGG building-sector legal texts, and World Bank urban/municipal development programs. The inspected samples remained within each radar’s approved scope. Radar 1 remains PARTIAL because some official-detail resolution is unavailable; its useful open opportunities were retained.

## Direct-only benchmark

| Radar | Direct HTTP | Paid search | OpenAI | Input | Output | Kept | Health |
|---|---:|---:|---:|---:|---:|---:|---:|
| Markets | 60 | 0 | 0 | 0 | 0 | 28 | PARTIAL |
| Projects | 6 | 0 | 0 | 0 | 0 | 0 | DEGRADED |
| Institutions | 2 | 0 | 0 | 0 | 0 | 0 | DEGRADED |
| Policies | 4 | 0 | 0 | 0 | 0 | 2 | HEALTHY |
| Funding | 4 | 0 | 0 | 0 | 0 | 24 | HEALTHY |
| **Total** | **76** | **0** | **0** | **0** | **0** | **54** | — |

The direct-only result shows that paid discovery currently adds value primarily to Projects and Institutions. It adds two results to each in the measured low-cost run. Markets, Policies, and Funding received no additional result from paid discovery, so their normal adapters suppress it when direct yield is sufficient.

## Usage and health metrics

Every run now records direct HTTP requests, 304s, changed/unchanged pages, per-source health, paid and resolution searches, OpenAI requests, skipped AI, AI cache hits, input/output tokens, final kept count, escalation level, partial-analysis state, and per-kept token/search/AI/direct-fetch ratios.

## Configuration

- `RADAR1_NORMAL_SEARCH_BUDGET=2`, `RADAR1_NORMAL_RESOLUTION_BUDGET=2`, `RADAR1_AI_ENABLED=false`
- `RADAR2_NORMAL_SEARCH_BUDGET=2`, `RADAR2_DIRECT_MIN_YIELD=2`, `RADAR2_AI_ENABLED=conditional`
- `RADAR3_NORMAL_SEARCH_BUDGET=1`, `RADAR3_DIRECT_MIN_YIELD=1`, `RADAR3_AI_ENABLED=conditional`
- `RADAR4_NORMAL_SEARCH_BUDGET=1`, `RADAR4_DIRECT_MIN_YIELD=1`, `RADAR4_AI_ENABLED=conditional`
- `RADAR5_NORMAL_SEARCH_BUDGET=2`, `RADAR5_DIRECT_MIN_YIELD=2`, `RADAR5_AI_ENABLED=conditional`
- `RADAR2_SOURCES`, `RADAR3_SOURCES`, `RADAR4_SOURCES`, `RADAR5_SOURCES`: optional JSON arrays of source definitions (`name`, `index_url`, `source_type`, `parser_type`, `refresh_days`, `priority`, `enabled`).
- Existing AI evidence and per-run token limits remain configurable through `AI_MAX_SOURCE_CHARS`, `AI_MAX_SNIPPET_CHARS`, `AI_MAX_EVIDENCE_ITEMS`, `AI_CLASSIFICATION_MAX_OUTPUT_TOKENS`, and `RADAR*_MAX_INPUT_TOKENS_PER_RUN`.

## Recommended production schedule

- Radar 1: daily.
- Radar 2: Monday, Wednesday, Friday.
- Radar 3: weekly; high-priority pages may retain a seven-day interval and stable governance pages 21–30 days.
- Radar 4: weekly, or twice weekly while an active consultation is expected.
- Radar 5: weekly.

## Commands and verification

```text
python -m pytest -q
python -m scripts.run_low_cost_comparison
python -m scripts.run_live_radar RADAR_2_PROJECTS --isolated --dry-run --direct-only
python -m scripts.run_live_radar RADAR_2_PROJECTS --isolated --dry-run
python -m scripts.run_live_radar RADAR_2_PROJECTS --isolated --dry-run --deep-search
flask db upgrade
```

The final suite passed **348 tests in 26.60 seconds**. Tests cover direct-source precedence, bounded fallback budgets, unchanged evidence/cache behavior, 304 handling, refresh skipping, meaningful list hashes, structured JSON extraction, bounded AI context, all five radar pipelines, and unchanged Telegram workflows.

Remaining expensive paths are the two Radar 1 discovery calls and the Project/Institution fallback calls. Projects still returned zero in the direct-only sample, so its two-call fallback remains justified. Institutions also needed its single fallback in the final quality-filtered sample. Adding another stable official RSS/API source for those two radars is the next useful cost improvement; automatic budget expansion remains disabled.
