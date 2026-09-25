# Structure Reorganization Report

Date: 2026-09-19  
Scope: physical file/folder reorganization only. Product behavior unchanged.

## 1. Old architecture

Feature logic was spread across parallel packages:

- `app/agents/` — orchestrator + per-radar agents
- `app/collectors/` — fetch/parse per radar (Radar 1 markets was richest)
- `app/domain/` — thin policy façades
- `app/services/` — review, dedup, targeted search, OpenAI, jobs
- `app/sources/` — curated source catalogs/adapters
- `app/search/` — OpenAI web-search provider
- `app/models/` + `app/extensions.py` — persistence
- `app/common/`, `app/utils/` — shared helpers dumping grounds
- `app/api/` — health/internal HTTP
- `app/bot/` — flat Telegram modules
- `app/radars/` — thin catalog façade

## 2. Final architecture

```
app/
  bot/           Telegram interface
  modules/       business features (radar1…5 + targeted_search)
  integrations/  pmmp, openai, http
  core/          shared application logic
  db/            models, repositories, extensions
  cli.py
  config.py
  __init__.py    create_app()
```

Dependency direction: `bot → modules → core / db / integrations`.

## 3. Exact old → new file mapping (primary)

| Old | New |
|-----|-----|
| `app/extensions.py` | `app/db/extensions.py` |
| `app/models/*` | `app/db/models/*` |
| `app/common/constants.py` | `app/core/constants.py` |
| `app/common/errors.py` | `app/core/errors.py` |
| `app/common/text.py` | `app/core/normalization.py` + `app/core/dates.py` |
| `app/utils/logger.py` | `app/core/logging.py` |
| `app/services/dedup_service.py` | `app/core/dedup.py` |
| `app/services/result_review_service.py` + `result_workflow_service.py` | `app/core/review.py` |
| `app/services/result_service.py` | `app/db/repositories/results.py` |
| `app/services/search_run_service.py` | `app/db/repositories/search_runs.py` |
| `app/services/source_state_service.py` | `app/db/repositories/source_state.py` |
| `app/services/radar_service.py` | `app/db/repositories/radars.py` |
| `app/services/openai_service.py` | `app/integrations/openai/client.py` |
| `app/services/cost_service.py` | `app/integrations/openai/cost.py` |
| `app/search/*` | `app/integrations/openai/*` |
| `app/collectors/markets/pages.py` | `app/integrations/http/pages.py` |
| `app/collectors/markets/pmmp.py` | `app/integrations/pmmp/client.py` |
| `app/sources/adapters.py` | `app/integrations/http/adapters.py` |
| `app/collectors/markets/policy.py` | `app/modules/radar1_markets/policy.py` |
| `app/collectors/markets/collector.py` | `app/modules/radar1_markets/collector.py` |
| `app/services/radar1_feedback_service.py` | `app/modules/radar1_markets/feedback.py` |
| `app/agents/radars/markets/*` | `app/modules/radar1_markets/{service,constants,schemas,validators,prompts}.py` |
| `app/collectors/{projects,institutions,policies,funding}/*` | `app/modules/radar{2,3,4,5}_*/` |
| `app/agents/radars/{projects,institutions,policies,funding}/*` | matching module `service/constants/schemas/…` |
| `app/services/targeted_search_*.py` | `app/modules/targeted_search/` |
| `app/agents/orchestrator.py` | `app/core/orchestrator.py` |
| `app/api/routes.py` | `app/core/internal_api.py` |
| `app/bot/handlers.py` | `app/bot/handlers/common.py` |
| `app/bot/{markets,projects,…,targeted,jobs,compact_review,run_queue}.py` | `app/bot/handlers/*` |
| `app/bot/keyboards.py` | `app/bot/keyboards/main.py` |
| `app/bot/ui_state.py` + `view_state.py` | `app/bot/state.py` |
| `app/bot/callbacks.py` | `app/bot/routing.py` |
| `app/cli_cleanup.py` | merged into `app/cli.py` |

## 4. Files merged

- `result_workflow_service.py` + `result_review_service.py` → `app/core/review.py`
- `ui_state.py` + `view_state.py` → `app/bot/state.py`
- `cli_cleanup.py` → `app/cli.py`
- `domain/markets/relevance.decide_relevance` appended into `radar1_markets/policy.py`

## 5. Files deleted

- Entire legacy packages after migration (see §6)
- One-shot helper scripts `scripts/_reorganize_structure.py`, `scripts/_rewrite_imports.py`

## 6. Folders deleted

`app/agents`, `app/api`, `app/collectors`, `app/common`, `app/domain`, `app/models`,
`app/radars`, `app/search`, `app/services`, `app/sources`, `app/utils`, root `audit-output/`
(historical contents moved under `docs/historical/audits/`).

## 7. Imports updated

All active `app/`, `tests/`, `scripts/`, and `run_bot.py` imports rewritten to the new paths.
No active references remain to:
`app.agents`, `app.api`, `app.collectors`, `app.common`, `app.domain`, `app.models`,
`app.radars`, `app.search`, `app.services`, `app.sources`, `app.utils`.

## 8. Legacy shims removed

No compatibility re-export packages left for old paths. Callers updated directly.
`app/integrations/pmmp/parser.py` re-exports PMMP parse helpers from `integrations.http.pages`
(single implementation; organizational façade only).

## 9. Root files moved

| From root | To |
|-----------|----|
| `CODE_REVIEW_REFACTOR_REPORT.md` | `docs/historical/` |
| `RADAR1_RELEVANCE_FEEDBACK_PMMP_REPORT.md` | `docs/historical/` |
| `SENIOR_ARCHITECTURE_REFACTOR_REPORT.md` | `docs/historical/` |
| `audit-output/*` | `docs/historical/audits/` |

## 10. Tests reorganized

```
tests/bot/
tests/modules/radar1|radar2|radar3|radar4|radar5|targeted_search/
tests/core/
tests/integration/
tests/fixtures/
```

`tests/conftest.py` adds nested test directories to `sys.path` so existing
`from test_bot import …` helpers keep working.

## 11. Test result

**729 passed** (same baseline count).

## 12. Alembic state

```
db current = f19a7c4d2e61 (head)
db heads   = f19a7c4d2e61 (head)
```

## 13. Schema migration status

**No migration created.**  
`flask db check` reports a JSON dialect representation difference
(`JSON(astext_type=Text())` vs `JSON()`) on two existing Targeted Search columns.
This is autogenerate noise from type reflection, not a model/schema change from this move.
Table names, columns, relationships, and constraints were not edited.

## 14. Final repository tree (summary)

```
BOOT_TELEGRAM/
├── app/
│   ├── bot/ (handlers/, keyboards/, presenters/, state.py, routing.py)
│   ├── modules/ (radar1_markets … radar5_funding, targeted_search)
│   ├── integrations/ (pmmp/, openai/, http/)
│   ├── core/
│   ├── db/ (models/, repositories/, extensions.py)
│   ├── cli.py
│   ├── config.py
│   └── __init__.py
├── migrations/
├── tests/ (bot/, modules/, core/, integration/, fixtures/)
├── scripts/
├── docs/ (architecture/, operations/, historical/)
├── backups/
├── .env / .env.example / .gitignore
├── pytest.ini
├── requirements.txt / requirements-dev.txt
├── README.md
└── run_bot.py
```

## 15. Unavoidable deviations from the literal target list

1. **`app/core/` contains additional shared modules** beyond the eight named files
   (`orchestrator.py`, `radar_agent_base.py`, `collector_registry.py`, `logging.py`,
   `internal_api.py`, etc.). These are shared cross-radar infrastructure that has no
   other approved home without inventing new top-level folders.

2. **`app/core/internal_api.py`** holds the former Flask `/api` blueprint (health/ready/runs).
   Active HTTP behavior preserved without recreating top-level `app/api/`.

3. **Radar modules keep a few extra implementation files** next to the prescribed names
   (`validators.py`, `prompts.py`, `discovery_strategies.py`, …) so logic was moved, not rewritten.

4. **`integrations/pmmp/parser.py`** re-exports parse helpers implemented in
   `integrations/http/pages.py` to avoid splitting a tightly coupled 585-line module mid-behavior.

5. **Empty placeholder files** (`repository.py`, `brief.py`, `feedback.py`, `schemas.py` stubs)
   exist where the target structure requires them but logic already lives in `service.py` /
   shared repos — kept concise, no ceremonial abstractions.

6. **Ephemeral `audit-output/`** removed from root; acceptance evidence now writes under
   `docs/historical/audits/` (still listed in `.gitignore` historically as `audit-output/`).

## Acceptance checklist

- [x] Radar 1 primarily under `app/modules/radar1_markets/`
- [x] Radars 2–5 under matching modules
- [x] Targeted Search under `app/modules/targeted_search/`
- [x] Telegram under `app/bot/`
- [x] Integrations under `app/integrations/`
- [x] Shared logic under `app/core/`
- [x] Persistence under `app/db/`
- [x] No `common/` / `utils/` dumping grounds
- [x] No active agents/domain/services/sources/collectors/radars packages
- [x] Root clean; reports under `docs/historical/`
- [x] `run_bot.py` sole root runtime entrypoint
- [x] Flask `app:create_app`
- [x] No migration created; Alembic current=head
- [x] 729 tests passed
- [x] Product behavior unchanged (reorganize only)
