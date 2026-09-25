# Phase 3 implementation record

## Delivered behavior

Radar 1 has bounded live discovery behind a configurable SearchProvider, executable business gates, source provenance checks, official-confirmation searches, pre-classification deduplication, confidence gates and review storage. Radars 2–5 have stronger executable conditions and no live collectors. Telegram authorization remains intact. Existing secrets were neither printed nor edited.

Flow: Telegram/CLI → SearchRun → live discovery → normalization and rules → deduplication → bounded classification → validation → database results/observations → concise summary.

## Validation on 2026-09-09

- Full suite: **103 passed**. HTTP is blocked in tests; providers and classification are mocked. No tests spent real API credit.
- Compilation: `python -m compileall -q app scripts migrations run.py run_bot.py` passed.
- Dependencies: `python -m pip check` reported no broken requirements.
- Isolated offline Radar 1 demo: completed, one accepted fictional result and one duplicate; zero real API usage.
- Explicit real OpenAI connection check: successful using `gpt-5.6-luna`, 9 input and 6 output tokens. An initial sandbox-network attempt failed before the successful permitted retry.
- Explicit live dry-run: `python -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 2` completed. Two provider requests, three candidates, one duplicate, two review candidates; zero candidate classifications and zero result writes. Returned usage: 26,606 input tokens, 1,151 output tokens, 4,747 cached input tokens; four reported web-search tool calls. Total cost is unknown because web-search charges are separate from token pricing. Search was billable despite dry-run.
- The live dry-run validates search connectivity and deterministic review behavior. It did not establish an automatically accepted live opportunity or end-to-end live Telegram/PostgreSQL operation. Later rule-reason instrumentation and review-rule fixes were validated by the offline suite, without repeating paid discovery.

Migration tests cover isolated upgrade/downgrade, metadata consistency, preservation and PostgreSQL SQL generation. The configured PostgreSQL database has **not** been migrated in this turn. Apply `flask --app run db upgrade` before restarting. No live Telegram notifications were sent during validation.

## New files

```text
app/agents/conditions.py
app/search/__init__.py
app/search/base.py
app/search/openai_provider.py
app/search/registry.py
app/collectors/__init__.py
app/collectors/base.py
app/collectors/registry.py
app/collectors/markets/__init__.py
app/collectors/markets/collector.py
app/collectors/markets/pmmp.py
app/collectors/markets/institutional_search.py
app/collectors/markets/web_discovery.py
scripts/check_openai.py
scripts/run_live_radar.py
migrations/versions/6598d37405be_phase_3_search_metrics_and_radar_.py
tests/test_phase3.py
PHASE3_CHANGES.md
```

## Modified files

```text
.env.example
README.md
app/config.py
app/agents/schemas.py
app/agents/validation.py
app/agents/orchestrator.py
app/agents/radars/base.py
app/agents/radars/markets/agent.py
app/agents/radars/markets/config.py
app/agents/radars/markets/schemas.py
app/agents/radars/markets/validators.py
app/agents/radars/projects/agent.py
app/agents/radars/projects/config.py
app/agents/radars/projects/schemas.py
app/agents/radars/institutions/agent.py
app/agents/radars/institutions/config.py
app/agents/radars/institutions/schemas.py
app/agents/radars/institutions/validators.py
app/agents/radars/policies/agent.py
app/agents/radars/policies/config.py
app/agents/radars/policies/schemas.py
app/agents/radars/funding/agent.py
app/agents/radars/funding/config.py
app/agents/radars/funding/schemas.py
app/agents/radars/funding/validators.py
app/models/search_run.py
app/models/result.py
app/services/result_service.py
app/services/dedup_service.py
app/api/routes.py
app/bot/jobs.py
scripts/test_agent.py
tests/conftest.py
tests/test_agent.py
tests/test_specialized_agents.py
```

Generated test caches/bytecode are omitted. `.env`, requirements and dependency versions were not changed. Earlier phase reports describe their historical implementations.

## Start and test from Telegram

From this project directory, stop the previous polling process, back up PostgreSQL and run:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe -m flask --app run seed-radars
.\.venv\Scripts\python.exe run_bot.py
```

Keep the existing credentials and allowlist in `.env`. Set `SEARCH_PROVIDER=openai` if an existing environment override disables it. Optional search/analysis limits and per-radar confidence settings are documented in [README.md](README.md) and `.env.example`.

From your allowlisted account, send `/start`, choose **Radar 1 — Marchés**, then **Lancer une recherche**. This is a real billable search. Wait for the concise counts; results remain in the database. Radars 2–5 retain empty live collection. Full dry-run/live CLI commands, source limitations, metrics and recovery instructions are in the README.
