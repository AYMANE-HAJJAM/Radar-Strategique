# Radar 1 procurement pipeline correction

The previous collector normalized each search hit directly into a candidate. It did not establish that the URL represented one tender, used broad queries without domain filters, resolved links before database deduplication, and allowed unresolved discoveries into the human review queue.

The collector now uses five business query clusters, searches PMMP first, then explicitly whitelisted institutional and discovery sources, and verifies the public offer page before emitting a candidate. Generic pages are containers: individual table rows or linked notices become separate discoveries. An aggregator can supply identity, but only a verified official detail can proceed. Unresolved discoveries are rejected internally and recorded in the run trace. No new database migration is needed: existing JSON metadata holds provenance, source role, verification and DCE fields.

## Configuration

```dotenv
RADAR1_MAX_QUERIES_PER_RUN=12
RADAR1_SOURCE_WHITELIST=marchespublics.gov.ma,marchesfaciles.ma,culture.gov.ma,alomrane.gov.ma
RADAR1_AGGREGATOR_DOMAINS=marchesfaciles.ma
RADAR1_DISCOVERY_DOMAINS=
RADAR1_KEYWORD_GROUPS={}
```

Add verified institutional domains to `RADAR1_SOURCE_WHITELIST`. Whitelisted domains other than PMMP, aggregator and discovery entries are treated as official institutions. Domain matching allows subdomains but rejects lookalikes. The former `RADAR1_OFFICIAL_DOMAINS` setting alone does not authorize collection from an additional domain.

`RADAR1_KEYWORD_GROUPS` accepts a JSON object whose optional keys are `HERITAGE_STRONG`, `ARCHITECTURE`, `TERRITORIAL`, and `NEGATIVE`, each containing an array of terms. Supplied arrays replace their default group. Matching normalizes accents, punctuation and case, and uses word boundaries. Negative signals take precedence. Query families live in `app/agents/radars/markets/config.py`.

The first five query families target PMMP and recent publication. If yield is low, institutional and aggregator discovery expand the search, followed by older still-open PMMP discovery. Resolution consumes the same hard query budget. API requests and actual web-tool calls are counted separately; a request may report multiple web-tool calls. The existing `.env` is not overwritten, so explicitly change an existing limit of 20 if desired.

## Acceptance and memory

- A live candidate must be relevant, Moroccan, have a buyer and active deadline, and pass official detail verification. Search snippets alone cannot enter `À traiter`.
- Public HTML must contain the individual identity, title, buyer and deadline. Generic URLs, articles, listing headings and institutional containers are rejected. PMMP detail URLs are preferred during exact identity resolution.
- Expired, closed, cancelled and awarded notices are excluded. Old notices without an active deadline cannot pass on the strength of a generic “open” claim.
- Existing legacy queue entries without detail verification are hidden until rediscovery establishes a valid detail page. Old aggregate cards cannot be approved through stale buttons.
- The existing database identity lookup runs before resolution and classification. A matching, complete discovery snapshot skips detail work and changes only `last_seen_at`. This preserves human rejection. Incomplete discovery metadata cannot establish “unchanged,” so it is refreshed. Material changes continue through the existing `UPDATED` workflow.
- `procurement_metrics` and bounded `procurement_trace` are saved on the search run. Candidate JSON records original discovery URL, resolved official URL, resolution provenance and DCE metadata.
- DCE inspection makes public HTML GET requests only. It records availability, size, access mode and a public attachment URL when exposed. Forms are never submitted and attachments are never downloaded. Form presence is treated conservatively as manual access.

## Verification on 2026-09-10

Commands:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q app scripts tests
.venv/Scripts/python.exe -m scripts.radar1_regression_dry_run
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 8
```

The suite passed **174 tests**, with all real HTTP disabled in tests. Compilation passed. Tests cover the Al Hoceima multi-offer case, individual extraction, negative business filters, whitelist roles, generic/article URLs, official resolution, detail verification, freshness, early memory including human rejection, material updates, DCE and GET-only form handling. Existing Radars 2–5 tests remain passing and their implementations are unchanged.

| Metric | Offline Al Hoceima fixture | Final live dry-run |
|---|---:|---:|
| Query requests | 11 | 8 |
| Unique discovered pages | 2 | 3 |
| Individual tender observations | 2 | 4 |
| Relevant candidates | 1 | 0 |
| Verified official URLs | 1 | 0 |
| Duplicates skipped | 0 | 0 |
| Rejections | 2 | 4 |
| Classification calls / result writes | 0 / 0 | 0 / 0 |

Fixture rejections include the aggregate container and the guarding tender. Live rejections were ordinary development/servicing/planting works outside the configured architecture, heritage and territorial-study focus. The final live search reported 14 underlying web-tool calls for eight API requests. No current verified live opportunity was found; successful live PMMP detail extraction is therefore **not established by this run**. The fixture proves the offer-resolution path without pretending that its synthetic reference is a real live opportunity.

The first network-restricted attempt failed with connection errors; the permitted network retry completed. Reports: `radar1-dry-run.json` (first completed live check), `radar1-dry-run-final.json` (final live check), `radar1-fixture-dry-run.json`, and `test-results.txt`.

The public HTML adapter is intentionally conservative. JavaScript-only, blocked, document-only or differently structured detail pages may be rejected. It never substitutes an aggregate link when verification fails. This can reduce recall; the trace identifies the reason for each processed rejection. The live dry-run used isolated SQLite, so production PostgreSQL connectivity was not exercised; early-memory behavior is covered by database integration tests.

## Exact Telegram live-test steps

1. Set the whitelist and limit above in `.env`, keeping the configured PostgreSQL, Telegram credentials and authorized user IDs. No schema migration is required by this change.
2. Restart the existing bot process with `.venv/Scripts/python.exe run_bot.py`. Avoid starting a second polling process alongside an existing instance.
3. From an authorized Telegram account, send `/start`, select **Radar 1 / Marchés**, then **Lancer une recherche**. This performs billable live search and may classify verified candidates.
4. Wait for completion, then open **À traiter**. Every new card must represent one verified official offer. An empty queue is valid if no candidate passes.
5. Use **Ouvrir** to check the specific PMMP consultation or institutional detail. It must not open a listing, article or generic search. Use **Détails** to check reference, buyer, location and deadline. Where found, the compact card displays DCE availability; protected access says manual download.
6. **Valider** one appropriate result and **Rejeter** another if available. Run the search again: unchanged items must preserve those decisions and avoid new classification/detail work. A materially changed deadline should re-enter as **UPDATED**.
7. Open **Recherches précédentes** and inspect the latest run. For investigation, read `run_metadata.procurement_metrics` and `run_metadata.procurement_trace`; those internal fields are not added to Telegram cards.

No Telegram messages were sent and no production results were changed during this implementation.

## Exact changed source files

```text
.env.example
README.md
RADAR1_PROCUREMENT_CHANGES.md
app/config.py
app/agents/orchestrator.py
app/agents/radars/markets/agent.py
app/agents/radars/markets/config.py
app/agents/radars/markets/schemas.py
app/agents/radars/markets/validators.py
app/collectors/base.py
app/collectors/markets/collector.py
app/collectors/markets/institutional_search.py
app/collectors/markets/pages.py                 (new)
app/collectors/markets/policy.py                (new)
app/collectors/markets/web_discovery.py
app/search/openai_provider.py
app/services/dedup_service.py
app/services/official_link_resolver.py
app/services/market_review_service.py
app/bot/presenters/result_presenter.py
scripts/radar1_regression_dry_run.py            (new)
tests/conftest.py
tests/test_agent.py
tests/test_market_usability.py
tests/test_phase3.py
tests/test_specialized_agents.py
tests/test_procurement_pipeline.py             (new)
```

The folder has no Git repository, so this is the explicit edit inventory rather than a Git diff. Verification artifacts listed above were also created.
