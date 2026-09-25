# Radar 1 live collection investigation — 2026-09-10

The zero-candidate problem had several concrete causes before final business validation. The fix retains strict final eligibility and separates discovery observations from verified offers. No Radar 2–5 implementation or Telegram navigation/card layout was changed.

## Findings established from live data

1. **Search sources disappeared at the provider boundary.** The code retained only `output_parsed.hits` whose URLs matched tool evidence, then discarded every remaining `web_search_call.action.sources` URL. Live responses contained useful PMMP result pages even when the model extracted no individual notice. Sources in the installed SDK are URL/type records, not guaranteed title/snippet/date records. Citations may add a title. The adapter now preserves these pages for deterministic extraction while continuing to reject unobserved generated URLs. See the [official web-search documentation](https://developers.openai.com/api/docs/guides/tools-web-search).
2. **The default aggregator domain was wrong for the intended site.** The observed Marché Facile site is `marchefacile.ma`, not `marchesfaciles.ma`. The corrected controlled discovery defaults include `cpmaroc.com`, `marchefacile.ma`, and `borjmarchepublic.ma`; the former spelling remains for compatibility. These are aggregator roles and cannot produce final accepted links. Explicit environment whitelist overrides remain authoritative.
3. **The PMMP URL detector was too narrow.** Real offer links use `entreprise.EntrepriseDetailConsultation` as well as `entreprise.EntrepriseDetailsConsultation`. The control's singular route redirects to the plural detail route. Both are recognized; search pages remain invalid final links.
4. **Offline list fixtures did not represent PMMP HTML.** Real PMMP rows combine procedure/category/publication in one cell and reference/object/buyer in another. The detail link may be an icon with no text. The old parser selected JavaScript action URLs and confused `08/09/2026` with a reference. Row-local links, combined-cell parsing, and date exclusion fix this. The live table also contains references such as `26E011`, without slashes.
5. **Discovery used final-result assumptions.** Title relevance was checked before candidate creation, and the original detail verifier required fields already populated rather than enriching them. An observation now needs a source URL/domain and title or reference. Public labelled fields populate missing identity, buyer, location, procedure and dates before final validation. A live extraction also supplied a timezone-less `deadline_at`; this optional value is no longer allowed to destroy usable identity.
6. **A real access failure was hidden.** Direct GET of the control aggregator page returned HTTP 403. That code is now traceable. A bounded hosted public-page inspection can surface an observed official URL. In this control, it surfaced an official public notice URL containing `refConsultation=1034798` and `orgAcronyme=a1t`. The resolver used those actual official identifiers to GET the corresponding detail page and verify the reference against its HTML. No DCE document or protected form was accessed by the local resolver. If verification fails, the candidate is rejected and collection health reflects the limitation.
7. **The dry-run console could lose its own report.** Windows raised `UnicodeEncodeError` when printing a completed run containing certain source characters. The script now writes the UTF-8 JSON report first and prints an ASCII-safe JSON representation to the console.

The control reference is visible on the [public aggregator record](https://cpmaroc.com/appels-offres/109919). Its authoritative verified target is the [PMMP consultation detail](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1034798&orgAcronyme=a1t). The reference is not hard-coded into production collection.

## Resulting pipeline

```text
Tool-observed URLs + structured discoveries
  -> explicit normalized source whitelist
  -> classify/open discovery pages and extract individual rows
  -> create incomplete observations
  -> early identity/memory check
  -> enrich from exposed official links or bounded exact lookup
  -> GET and verify actual official detail
  -> unchanged final geography, freshness and business gates
  -> classification only if needed
  -> existing result workflow
```

Clear negative purposes and fully described irrelevant tenders can be rejected after observation creation, before spending on enrichment. Missing relevance evidence on a reference-only or incomplete discovery is not itself a rejection. Listing containers never become final offers. One generic source page cannot consume the entire candidate budget: per-query fan-out defaults to 20 observations, allowing subsequent query families to run.

## Metrics and health

Each entry in `SearchRun.run_metadata.collection_queries` records:

```text
query_index, query_text, domains, recency_days
raw_results_count, allowed_domain_results, aggregate_pages_detected
individual_tenders_extracted, candidates_created
rejected_by_source, rejected_by_parser, rejected_by_freshness, rejected_by_relevance
official_resolution_attempts, rejected_by_resolution, official_urls_resolved
duplicates_skipped, control_reference_filtered
provider response status, output/action shapes and bounded source/extraction samples
```

No full page bodies or credentials are logged. Each completed query logs a concise counter line; collection logs totals. Existing `procurement_trace` includes query attribution and resolution/fetch rejection reasons. Totals include `search_calls`, `raw_results`, `usable_results`, and `cost_warning`.

`candidates_created` counts incomplete normalized observations, including later rejected or duplicate observations. `official_urls_resolved` counts verified final offers. The legacy run-level `candidates_count` continues to count offers handed to the orchestrator; it is not misrepresented as a raw discovery count. Allowed-source page counts are summed per query, while `pages_discovered` is globally distinct. Rejections can include a failed container parse in addition to rejected tender rows, so rejection counts need not equal candidate counts.

- `HEALTHY`: observations were usable; a zero-result business-filter outcome is distinguishable from broken collection.
- `DEGRADED`: no raw/usable yield, unresolved official details, or parser/access limitations. The workflow execution may finish, but its collector health and warnings remain explicit.
- `FAILED`: the search provider could not perform collection, including three initial failed requests.

After four queries with no usable observations, expansion stops with `zero_yield_stop`, a health warning and `cost_warning=true`. The query budget also covers resolver and hosted page-inspection calls. Actual web-tool calls are tracked separately from API request count.

The only Telegram change is the requested completion-status distinction. Existing buttons/cards/navigation are preserved:

```text
HEALTHY, no new/updated/known result:
✅ Recherche terminée — aucun résultat pertinent

DEGRADED:
⚠️ Recherche terminée mais la collecte semble anormale
```

## Validation

**200 tests passed. Compilation passed.** Tests prohibit real HTTP calls. New regressions cover real-source response projections, optional response fields, www/subdomain normalization, both PMMP detail spellings, icon-only detail links and JavaScript rejection, combined PMMP table cells, aggregator row fields, incomplete observations, optional malformed timestamps, strict final rejection, source-access failures and observed official-ID resolution, zero-yield stopping, health persistence/status messaging, per-query fan-out, and Windows report output. Existing Radar 2–5 tests remain passing.

Final live dry-runs used isolated storage and zero AI classification calls / zero Result writes:

| Metric | Normal bounded run | Known-reference control |
|---|---:|---:|
| Search/API requests | 2 | 3 |
| Raw source results, summed per query | 12 | 3 |
| Allowed-source pages, summed per query | 12 | 3 |
| Distinct discovered pages | 12 | 2 |
| Tender observations | 12 | 2 |
| Candidates created before enrichment/filtering | 12 | 2 |
| Verified official offers | 0 | 1 |
| Freshness rejections | 0 | 0 |
| Relevance rejections | 12 | 0 |
| Parser rejections | 1 | 0 |
| Collector health | DEGRADED | HEALTHY |

The normal smoke test was explicitly limited to 12 observations. It did not prove broad live recall: it rejected the sampled tender purposes and reported one unparseable page. This is no longer reported as a healthy empty search. Its report is [radar1-collection-final-validation.json](radar1-collection-final-validation.json).

**PMMP live detail extraction is now verified end to end for `CA11/2026/APDN`.** The control created a verified official candidate for consultation `1034798`, architectural study and works supervision for a municipal swimming pool in Targuist, with deadline **23/09/2026**. Two observations represent the same opportunity's discovery and official enrichment, not two final offers. The dry-run did not auto-approve or save it; the existing workflow retains manual review where publication-date evidence is missing. Report: [radar1-control-final-validation.json](radar1-control-final-validation.json).

## Commands and configuration

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q app scripts tests

# Normal production-sized dry-run; no classification or Result writes.
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run

# Exact bounded normal validation used above.
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 4 --max-candidates 12 --report-json radar1-collection-final-validation.json

# Development control only; requires --dry-run and is never a production seed.
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 4 --max-candidates 6 --control-reference CA11/2026/APDN --report-json radar1-control-final-validation.json
```

Dry-run prints the requested totals and full structured diagnostics. Exit codes: `0` healthy completion, `2` degraded collection, `1` failed execution. A dry-run without `--isolated` still records its SearchRun in the configured database and uses database memory, but does not write Results. All validations here used isolated SQLite; production PostgreSQL connectivity was not changed or asserted.

```dotenv
RADAR1_SOURCE_WHITELIST=marchespublics.gov.ma,cpmaroc.com,marchefacile.ma,borjmarchepublic.ma,marchesfaciles.ma,culture.gov.ma,alomrane.gov.ma
RADAR1_AGGREGATOR_DOMAINS=cpmaroc.com,marchefacile.ma,borjmarchepublic.ma,marchesfaciles.ma
RADAR1_ZERO_YIELD_QUERY_LIMIT=4
RADAR1_QUERY_OBSERVATION_LIMIT=20
```

Existing `.env` values are not overwritten. If an explicit whitelist was copied from the earlier example, update it to the corrected domains and restart the existing bot process. Source scope remains controlled; no random media domains were added. No production results or Telegram messages were changed/sent during validation.

## Files changed for this investigation

```text
.env.example
README.md
RADAR1_COLLECTION_DIAGNOSTICS.md                         new
app/config.py
app/search/base.py
app/search/openai_provider.py
app/collectors/base.py
app/collectors/markets/collector.py
app/collectors/markets/pages.py
app/collectors/markets/pmmp.py
app/collectors/markets/policy.py
app/collectors/markets/institutional_search.py
app/agents/radars/markets/config.py
app/agents/orchestrator.py
app/services/official_link_resolver.py
app/bot/jobs.py                                         completion health text only
scripts/run_live_radar.py
tests/test_procurement_pipeline.py                      observation-count fixture update
tests/test_collection_diagnostics.py                    new
tests/fixtures/live_search_sources.json                 new, sanitized live-source projection
```

Intermediate diagnostic JSON/console files are retained for the failed attempts described above. The two `*-final-validation.json` files are the final live evidence; `radar1-collection-tests.txt` records the full test result.
