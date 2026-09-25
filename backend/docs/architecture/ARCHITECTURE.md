# Architecture

## Purpose

Internal Telegram monitoring for ARCHERITAGE / Innova across five Radars plus Targeted Search.
This document describes **layers and dependency direction**, not product marketing.

## Entrypoints

| Command | Role |
|---------|------|
| `python run_bot.py` | **Production Telegram poller** (only process that talks to Telegram) |
| `python -m flask --app app:create_app …` | Migrations, seed, CLI ops, optional local HTTP |

Never start two pollers with the same bot token.

## Layer diagram

```
Telegram updates
    → app/bot            (handlers, keyboards, presenters, state, routing)
    → app/modules        (radar1…5 + targeted_search business features)
    → app/core           (shared: dedup, review, pagination, orchestrator)
    → app/integrations   (pmmp, openai, http)
    → app/db             (models, repositories, extensions)
```

**Dependency rule:**

```
bot → modules → core / db / integrations
```

- `core` must not depend on `bot` or a specific Radar module
- `integrations` must not depend on Telegram or Radar policy
- `db` must not depend on Telegram rendering

## Packages

### `app/bot`
Telegram only: `handlers/`, `keyboards/`, `presenters/`, `state.py`, `routing.py`.

### `app/modules`
Feature homes — open these first when changing product rules:

| Module | Responsibility |
|--------|----------------|
| `radar1_markets` | markets policy, collector, PMMP orchestration hooks, adaptive feedback |
| `radar2_projects` | projects pipeline |
| `radar3_institutions` | institutions pipeline |
| `radar4_policies` | policies pipeline |
| `radar5_funding` | funding pipeline |
| `targeted_search` | brief parse, session lifecycle, refinement |

### `app/integrations`
External systems only (no business acceptance rules):

- `pmmp/` — PMMP client (URLs/fetch helpers) + parser + schemas
- `openai/` — OpenAI client, web search provider, prompts, cost
- `http/` — generic HTML fetch (`html.py`), adapters, verification

### `app/core`
Genuinely shared application logic: `dedup`, `review`, `pagination`, `normalization`,
`dates`, `errors`, `enums`, `constants`, plus shared orchestration (`orchestrator`,
collector registry, radar agent base).

### `app/db`
SQLAlchemy models (`db/models/`), shared repositories, `extensions.py` (db + migrate).

### Flask factory / CLI
- `app/__init__.py` → `create_app()`
- `app/cli.py` → `seed-radars`, `cleanup-test-radar-data`, `fail-orphan-run`, `test-openai`
- Internal HTTP health/runs blueprint: `app/core/internal_api.py` (registered under `/api`)

## Radar 1 pipeline (unchanged behavior)

1. listing discovery → cheap `preliminary_plausible`
2. early identity dedup
3. PMMP/official detail enrich (`integrations.pmmp.parser.enrich_detail` → `metadata.pmmp`)
4. hard role+domain policy (`modules.radar1_markets.policy.evaluate_relevance`)
5. local adaptive feedback (`modules.radar1_markets.feedback`; never overrides hard reject; 0 paid calls)
6. validate → persist

## SearchRun lifecycle

DB-enforced one active run per radar (`initialized`/`running`).
Stale runs recovered after `SEARCH_RUN_STALE_MINUTES`.
Completion messaging is shared in `bot/handlers/jobs.py`.

## Result lifecycle

Discovery: `NEW` | `UPDATED` | `UNCHANGED`  
Review: `PENDING` | `APPROVED` | `REJECTED`  
Exact-run actionable = observation state in `{new, updated, manual_review}` + live `PENDING`.

## Telegram UI state

Explicit `UIState` in `app/bot/state.py`. Stray text/media → `redisplay_current`.
Multi-click: inflight set + debounce + transition flag; SearchRun uses DB lock.

## Dedup

Canonical module: `app/core/dedup.py` (URL/identity/content + cross-radar `global_source`).

## Targeted Search

`app/modules/targeted_search/` + Telegram UX in `app/bot/handlers/targeted.py`.

## Maintenance CLI

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app cleanup-test-radar-data --radars 2,3,4,5 --dry-run
```

then `--confirm` (backup first). Never deletes Radar 1.
