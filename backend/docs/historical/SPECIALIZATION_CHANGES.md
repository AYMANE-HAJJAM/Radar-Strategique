# Specialized radar agents — delivery record

## Architecture

The existing shared core remains at `app/agents/` rather than moving it into a new `core/` directory. This preserves Phase 2 imports and avoids a migration of unrelated infrastructure. Its orchestrator, schemas, generic prompt composition, exceptions and shared validation helpers are used by all five specialized agents.

```text
app/
  agents/
    __init__.py
    orchestrator.py
    schemas.py
    validation.py
    prompts.py
    exceptions.py
    radars/
      __init__.py
      base.py
      registry.py
      markets/
        __init__.py
        agent.py          MarketsRadarAgent
        config.py
        prompts.py
        schemas.py
        validators.py
      projects/
        __init__.py
        agent.py          ProjectsRadarAgent
        config.py
        prompts.py
        schemas.py
        validators.py
      institutions/
        __init__.py
        agent.py          InstitutionsRadarAgent
        config.py
        prompts.py
        schemas.py
        validators.py
      policies/
        __init__.py
        agent.py          PoliciesRadarAgent
        config.py
        prompts.py
        schemas.py
        validators.py
      funding/
        __init__.py
        agent.py          FundingRadarAgent
        config.py
        prompts.py
        schemas.py
        validators.py
  services/              shared infrastructure only
  models/                common database memory
  bot/                   existing menus, callbacks and allowlist
  radars/                compatibility aliases/catalog; no duplicated business rules
```

`RadarAgentRegistry` maps each stable code to its specialized class. `SearchRunService.reserve()` validates that code and records the selected class. `AgentOrchestrator.execute()` resolves the class again, records the actual executing agent and invokes the common contract. Unknown codes fail cleanly before reservation. No radar-specific branches were added to the orchestrator.

## Modified existing files (19)

```text
README.md
app/agents/orchestrator.py
app/agents/prompts.py
app/agents/schemas.py
app/api/routes.py
app/bot/handlers.py
app/models/search_run.py
app/radars/__init__.py
app/radars/base.py
app/radars/radar_1_markets.py
app/radars/radar_2_projects.py
app/radars/radar_3_institutions.py
app/radars/radar_4_policies.py
app/radars/radar_5_funding.py
app/services/dedup_service.py
app/services/openai_service.py
app/services/result_service.py
app/services/search_run_service.py
scripts/test_agent.py
```

## Added files (37)

```text
SPECIALIZATION_CHANGES.md
app/agents/validation.py
app/agents/radars/__init__.py
app/agents/radars/base.py
app/agents/radars/registry.py
app/agents/radars/markets/__init__.py
app/agents/radars/markets/agent.py
app/agents/radars/markets/config.py
app/agents/radars/markets/prompts.py
app/agents/radars/markets/schemas.py
app/agents/radars/markets/validators.py
app/agents/radars/projects/__init__.py
app/agents/radars/projects/agent.py
app/agents/radars/projects/config.py
app/agents/radars/projects/prompts.py
app/agents/radars/projects/schemas.py
app/agents/radars/projects/validators.py
app/agents/radars/institutions/__init__.py
app/agents/radars/institutions/agent.py
app/agents/radars/institutions/config.py
app/agents/radars/institutions/prompts.py
app/agents/radars/institutions/schemas.py
app/agents/radars/institutions/validators.py
app/agents/radars/policies/__init__.py
app/agents/radars/policies/agent.py
app/agents/radars/policies/config.py
app/agents/radars/policies/prompts.py
app/agents/radars/policies/schemas.py
app/agents/radars/policies/validators.py
app/agents/radars/funding/__init__.py
app/agents/radars/funding/agent.py
app/agents/radars/funding/config.py
app/agents/radars/funding/prompts.py
app/agents/radars/funding/schemas.py
app/agents/radars/funding/validators.py
migrations/versions/c7e41a9b2803_specialized_radar_agent_identity.py
tests/test_specialized_agents.py
```

No existing tests were removed or relaxed. Dependency files, `.env`, Telegram keyboard definitions, authorization conditions, job-runner implementation, cost service and active-run protection remain intact.

## Validation results

- Complete suite: **79 passed**, including all 50 existing Phase 2 tests.
- Python compilation passed for app, scripts, tests, migrations and both entry points.
- Dependency check passed: no broken requirements and no new dependencies.
- Migration upgrade/downgrade and model/schema consistency tests passed; PostgreSQL SQL compilation passed. Migration `c7e41a9b2803` only adds nullable `agent_name`; historical executions are not relabeled.
- All five codes resolve to the expected class and complete empty runs without AI. Run summaries and database rows contain the class name.
- Tests cover distinct rules, A/B/C maturity, current-role verification and expiry, policy claims, funding A–E/access modes, and unknown-code rejection.
- SDK adapter tests prove each agent supplies its specialized prompt and schema and retains extended analysis fields.
- Persistence tests confirm specialized fields survive in shared Result/ResultObservation JSON; extension changes update the same result row.
- Deterministic business rejection precedes AI. Expired-on-rediscovery markets are rejected without a new AI request.
- Existing authorization, `/start`, five-radar keyboards, background launch and failure-message tests passed.
- AST regression check confirms the orchestrator contains no radar-code-specific branching.
- Isolated Markets demo completed with one new result, one duplicate and `agent_name=MarketsRadarAgent`; mock analysis only.

No real OpenAI or Telegram requests were made. Test HTTP access remains blocked. No live PostgreSQL migration was applied during this change; validation used isolated test databases and PostgreSQL DDL compilation. No live web search, collectors, scraping, schedules, alerts, dashboard, production prompts or reports were added.

## Run locally

Stop the existing bot, back up PostgreSQL, then from the project folder:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe run_bot.py
```

Use the same authorized private-chat flow: `/start` -> select radar -> `Lancer une recherche`. Empty collectors still complete with zero results. Check history/logs or the authenticated `/api/runs` endpoint for the agent class. Keep your current `.env` and allowlist.
