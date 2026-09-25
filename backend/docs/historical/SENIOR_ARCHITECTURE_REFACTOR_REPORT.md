# Senior Architecture Refactor Report

Date: 2026-09-18

## 1. Architecture problems found

- Misleading `market_review_service` name (shared by all radars)
- Telegram allowlist enforced inside review service
- Dual-looking entrypoints (`run.py` vs `run_bot.py`) without clear docs
- Stale `requirements-lock.txt` still listing removed `waitress`
- Missing architecture/ops handoff docs for a new engineer
- Callback answer sometimes after DB work (spinner latency)
- Radar 1 gate named `architecture_pending` while rules are broader
- No stable `domain/` import surface for Radar 1 relevance

## 2. Target architecture

Proportional layers: `bot` → `services` → `agents`/`collectors`/`domain` → `models`.
No DI frameworks, CQRS, or microservice split.

## 3. Files moved

- `CLEANUP_REPORT.md` → `docs/historical/CLEANUP_REPORT.md`

## 4. Files merged / consolidated

- Keyboard labels/prefixes sourced from `app/bot/constants.py`
- `PAGE_SIZE` centralized in `app/common/constants.py`
- Review service canonical module: `result_review_service.py`

## 5. Files renamed

| Before | After |
|--------|-------|
| (logic in) `market_review_service.py` | `result_review_service.py` |
| `architecture_pending` | `business_queue_eligible` (+ alias) |

## 6. Files deleted

| Path | Why safe |
|------|----------|
| `requirements-lock.txt` | Stale (contained `waitress`); strategy is ranges via requirements.txt + requirements-dev.txt |

Compatibility shim retained: `market_review_service.py` re-exports `result_review_service` for older imports/tests.

## 7. Why deletions were safe

Lockfile was not the install path documented in README (`requirements-dev.txt`). Regenerating was optional; removing avoids contradictory pins.

## 8. Entry points before / after

| Before | After |
|--------|--------|
| Bot: `run_bot.py` | Unchanged (documented as sole poller) |
| Flask: `flask --app run` via `run.py` | **`flask --app app:create_app` only**; `run.py` removed |

## 9. Requirements strategy before / after

| Before | After |
|--------|--------|
| requirements.txt + requirements-dev.txt + stale lock | **requirements.txt** (runtime) + **requirements-dev.txt** (includes runtime + pytest). Lock removed |

## 10. Dependency removals

- `waitress` already removed from requirements.txt; lock that still listed it was deleted

## 11. Root tree before / after

Root remains professional: `app/`, `docs/`, `migrations/`, `scripts/`, `tests/`, `run_bot.py`, requirements*, README, pytest.ini, `.env.example`.
Historical reports under `docs/historical/`. Architecture/ops under `docs/architecture/` and `docs/operations/`.

## 12. Telegram state architecture

`UIState` + version + transition flag in `ui_state.py`. Stray messages → `redisplay_current`. Inflight + debounce + transition in handlers.

## 13. Shared UI consolidation

Already from prior cleanup (`compact_review`, completion/failure keyboards). This pass: constants, faster callback ack on review/details, docs.

## 14. Service / repository boundaries

- Review use case: `result_review_service` (no Telegram ACL)
- Bot remains the allowlist gate (`handlers.authorized`)
- Repositories not exploded into empty wrappers (proportional)

## 15. Radar domain organization

- `app/domain/markets/` exposes `decide_relevance` / `evaluate_relevance`
- Implementation remains in `collectors.markets.policy` (preserve behavior)

## 16. Targeted Search organization

Unchanged structure; documented. No god-object split forced in this pass (remaining debt).

## 17. Dedup architecture

Unchanged canonical `dedup_service` (documented).

## 18. Error / logging improvements

- `app/common/errors.py` application error types for future mapping
- Logging categories documented in architecture/ops docs

## 19. Config cleanup

- Single PAGE_SIZE source
- Env still centralized in `app/config.py`
- `.env.example` retained as template (no obsolete vars stripped aggressively this pass)

## 20. Test cleanup

- Updated unauthorized decide expectation (ACL is bot-layer)
- Compatibility imports via shim keep older tests green

## 21. Docs created

- `docs/architecture/ARCHITECTURE.md`
- `docs/operations/OPERATIONS.md`
- Rewritten `README.md`
- This report

## 22. Performance before / after

| Path | Change |
|------|--------|
| Callback review/details | `query.answer()` before DB work |
| Menu / queue | Unchanged hot paths |

No abstraction added that slows simple renders.

## 23. Tests passed

**702 passed.** Alembic head unchanged: `f19a7c4d2e61`. `compileall` + `app:create_app` import OK. No migration.

## 24. Remaining technical debt

1. Split `targeted_search_service` into parser/pipeline/result modules when next edited
2. Move more policy entrypoints under `domain/{projects,institutions,policies,funding}`
3. Optionally fold Radar 1 queue tracking into `view_state` (careful UX)
4. Remove `market_review_service` shim once all imports migrated
5. Wire or delete unused agent `PROMPT` attributes
6. Move Telegram ACL tests to dedicated bot suite only

## 25. Exact production commands

```powershell
# Bot
.\.venv\Scripts\python.exe run_bot.py

# Migrations
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
.\.venv\Scripts\python.exe -m flask --app app:create_app seed-radars

# Tests
.\.venv\Scripts\python.exe -m pytest -q
```

## 26. Restart requirement

**Yes** — restart `run_bot.py` to load handler/service changes. No DB migration.
