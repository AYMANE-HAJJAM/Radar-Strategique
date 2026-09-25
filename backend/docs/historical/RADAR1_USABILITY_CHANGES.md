# Radar 1 usability and precision

Radar 1 now provides five-record Telegram pages for current opportunities and manual review. Cards emphasize official links, buyer, location, procedure, dates, status and reference. Human decisions retain an audit trail. Radars 2–5 rule packages, live-collector availability and menu behavior remain unchanged.

## Validation

- **126 tests passed**; compilation of app, scripts, migrations and entry points passed.
- Migration `d91eac4206b1` applied and rolled back in isolated migration tests; schema comparison and PostgreSQL SQL generation passed.
- Mocked Telegram tests cover review menu dispatch, five-card pages, next-page controls, URL buttons, approval and unauthorized callback rejection.
- Service tests cover rejection, reviewer/time/previous-reason audit data, stale/repeated decisions, unchanged approvals, changed-evidence review, current/expired filtering, specific reasons and official-link matching.
- HTTP is blocked throughout the tests. No paid OpenAI/web calls or live Telegram messages were made for this change.
- The live PostgreSQL database and `.env` were not modified. Actual Telegram delivery and remote-page availability were not exercised; buttons use the best safely validated stored URL.

## Upgrade and test

Stop the old bot process, then run from the project directory:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe run_bot.py
```

In a private chat from an allowlisted account:

1. Send `/start` and choose **Radar 1 — Marchés**.
2. Select **⚠️ À vérifier**. Up to five pending cards appear with pagination.
3. Use **🔗 Ouvrir** to inspect the announcement. Secondary and indirect PMMP fallbacks are labeled.
4. Use **✅ Valider** or **❌ Rejeter**. Approval requires open/current evidence; it appears in **🆕 Voir les nouveautés**. Rejected records remain stored.
5. Reopen the menus to refresh pages after decisions. Clearly obsolete records are hidden without deletion. An empty page can mean no eligible pending records remain.
6. Optionally select **Lancer une recherche** to discover fresh opportunities and resolve links on rediscovery. This uses the existing billable live search/analysis flow.

Existing candidates can be browsed immediately after migration. Opening a menu never launches a paid search. No new environment settings or dependencies are required.

## Implementation and limits

OfficialLinkResolver shares the collector's query/candidate budget. It prefers exact PMMP details, then official institutional notice evidence, then labeled indirect/secondary fallback. A match requires normalized buyer plus reference, or buyer plus exact title when reference is missing. Successful resolution uses the official snapshot and retains the discovery URL. When exact details cannot be found, indirect PMMP paths, buyer and reference remain available. Limits and unavailable sources can still leave review candidates.

Discovery uses seven-day then conditional thirty-day passes. One ninety-day still-open query is possible only when no eligible candidates were found and budget remains. Closed, expired and historical notices without current evidence are excluded. No forms, personal-data submission, protected downloads or browser automation are involved.

Official-link status and current reviewer/decision fields use existing `radar_metadata` JSONB. The new `market_reviews` audit table stores each decision against an evidence hash, with reviewer, time, previous reason and pre-decision snapshot. Existing results and observations remain intact. Approved unchanged records stay visible while current; changed evidence or rule versions can trigger reassessment. Earlier decisions remain in the audit table. Stale buttons cannot approve a newer snapshot or reverse a completed decision. There is no undo button or audit browser; Telegram Historique remains run history.

The Radar 1 medium-confidence exception requires direct confirmed PMMP evidence, Morocco/location, a reference, future deadline, open status, known procedure, business-topic evidence, no deterministic conflicts and no separate AI review flag. Irrelevant and low-confidence analyses remain excluded. Radars 2–5 thresholds are unchanged.

## New files

```text
app/services/official_link_resolver.py
app/services/market_review_service.py
app/models/market_review.py
app/bot/markets.py
migrations/versions/d91eac4206b1_market_review_audit.py
tests/test_market_usability.py
RADAR1_USABILITY_CHANGES.md
```

## Modified files

```text
app/agents/radars/markets/agent.py
app/agents/radars/markets/config.py
app/agents/radars/markets/prompts.py
app/agents/radars/markets/schemas.py
app/agents/radars/markets/validators.py
app/collectors/markets/collector.py
app/collectors/markets/web_discovery.py
app/models/__init__.py
app/bot/callbacks.py
app/bot/keyboards.py
app/bot/handlers.py
app/bot/jobs.py
tests/test_phase3.py
tests/test_jobs_api.py
README.md
```

Generated caches/bytecode are omitted. Shared orchestration and result persistence were not edited. See README.md for complete configuration, source limitations and recovery instructions.
