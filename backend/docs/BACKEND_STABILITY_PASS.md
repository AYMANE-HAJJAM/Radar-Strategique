# Backend stability pass

**Date:** 2026-09-29

The backend suite now finishes and passes twice. No production search was run, no paid API was called, and no production data was changed.

## 1. Initial failing and hanging tests

The suite before this pass did not finish. Failures clustered like this:

| Group | What showed up |
|---|---|
| A. Import / module | `AnalysisResponse` type error: a `MarketAnalysis` from `app` was rejected by an `AnalysisResponse` from `backend.app`. The same split created a second SQLAlchemy instance (`Flask app is not registered with this SQLAlchemy instance`). |
| B. Unit | Radar, bot, and core tests that save results or call the orchestrator failed for the same split. |
| C. Integration | Agent, phase-3, jobs, and production-acceptance tests failed the same way. |
| D. Hang | `test_inflight_callback_stays_deduplicated_after_debounce` waited forever on `entered.wait()`. The full suite stopped there. |
| E. Flaky | None isolated. The hang was deterministic. |
| F. Stale | `test_flask_factory_imports_without_network` expected a `phase` field the public health route no longer returns. `test_bot_entry_point_supplies_event_loop` imported `backend.run_bot`. `test_internal_api_requires_separate_token_and_limits_output` called the old bearer-token `/api/runs` list. |
| G. Environment | `pytest.ini` put both `backend/` and the repo root on `sys.path`, so `app` and `backend.app` both loaded. The test app did not pin `ALLOWED_TELEGRAM_USER_IDS`, so fixture user `123` depended on `.env`. |
| H. Product gaps the tests exposed | `load_config()` no longer returned `ALLOWED_TELEGRAM_USER_IDS`. `GET /api/ready` was missing, so a GET fell through the OPTIONS catch-all and returned 405. Migration `c4d8e1a72b05` created a foreign key outside SQLite batch mode, so upgrade-from-base failed on SQLite. |

## 2. AnalysisResponse import split

There is one class: `app.core.agent_schemas.AnalysisResponse`.

`pytest.ini` used `pythonpath = . ..`. Tests and scripts imported `backend.app` and `backend.scripts`. Python loaded the same files a second time under the `backend` package. Pydantic then refused the other copy of `MarketAnalysis`, and Flask-SQLAlchemy rejected the other `db` object.

The running application, `wsgi.py`, and the orchestrator already import `app`. That is the canonical path. Test, script, and `run_bot.py` imports were changed from `backend.app`, `backend.scripts`, and `backend.tests` to `app`, `scripts`, and `tests`. Pytest now keeps only `backend/` on the path, so a second copy cannot load.

No second `AnalysisResponse` was added.

## 3. Production-acceptance hang

`test_inflight_callback_stays_deduplicated_after_debounce` starts a callback and waits until a patched `launch_search` sets an event.

Two things kept that event unset:

- The test patched `app.bot.handlers.common.launch_search` while the handler object it called had been imported as `backend.app`. The patch never wrapped the function that ran.
- `load_config()` did not publish the Telegram allowlist. With user `123` unauthorized, `on_callback` returned before `launch_search`. `await entered.wait()` then blocked the suite.

The import unification makes the patch hit the function that runs. The allowlist is restored and the test app allows user `123`. The wait is now `asyncio.wait_for(..., timeout=2)`, so a future miss fails the test instead of stalling the process.

## 4. Files changed

- `pytest.ini` — test path is only `backend/`
- `tests/**/*.py`, `scripts/*.py`, `run_bot.py` — imports use `app`, `scripts`, and `tests`
- `app/config.py` — `ALLOWED_TELEGRAM_USER_IDS` is parsed again (positive integers, empty means an empty set)
- `tests/conftest.py` — test app uses user `123`, a fake bot token, and shuts the job runner down without waiting
- `app/core/job_runner.py` — `shutdown` accepts `wait` and `cancel_futures`
- `app/api/health.py` — `GET /api/ready` checks the database and returns 503 when it is down. `GET /api/health` stays `{status: ok}`
- `migrations/versions/c4d8e1a72b05_search_run_launcher.py` — the launcher foreign key is added inside `batch_alter_table` so SQLite can upgrade from base
- `tests/integration/test_production_acceptance.py` — bounded wait
- `tests/integration/test_startup.py` — health contract and `import run_bot`
- `tests/integration/test_jobs_api.py` — run detail is covered through the session API
- `scripts/validate_source_enrichment.py` — removed a leading BOM that stopped compilation

Radar relevance rules were not changed. The estimate-normalization helper is unchanged.

## 5. Stale code removed

No product module was deleted. The duplicate import path is what was removed. `app/core/internal_api.py` still holds the old bearer-token helpers; `database_available` is used by `/api/ready`. The operator list routes on that module are not mounted on the public API.

## 6. Obsolete tests replaced

`test_internal_api_requires_separate_token_and_limits_output` called the unmounted bearer list. It is now `test_run_detail_requires_session_and_hides_secrets`: unauthenticated radar and run reads are 401, an authenticated run detail shows `COMPLETED`, the access code is not echoed, and a missing run is 404. Session coverage for launch, pagination, and review stays in `tests/api/test_api.py`.

## 7. Database and session

Candidate failures still roll back inside the orchestrator and continue with the next candidate. API database errors roll back and return 503. The migration round trip on a disposable SQLite file now reaches head and downgrades to base. Test teardown still removes the session, drops the tables, and disposes the engine.

## 8. Background runner

`LocalJobRunner.shutdown` can return without waiting and can cancel queued work. The test app fixture calls that after each test so a leftover worker does not hold the process. No Celery or Redis was added.

## 9. Configuration

The test factory overrides the database to in-memory SQLite, disables search, clears the OpenAI key, sets the frontend URL to `http://localhost:3000`, and sets the allowlist to `{123}`. `TESTING` is true. Production cookie rules are still driven by `FLASK_ENV` and `RENDER` in `load_config`, and `tests/api/test_api.py` still checks both modes.

## 10. Final test counts

| Run | Result | Duration |
|---|---|---|
| First full suite after the fixes | **806 passed** | 132.13s |
| Second full suite | **806 passed** | 162.94s |

Skipped tests: none reported. Warnings summary: none. Failures: 0. Hangs: none. The estimate-normalization tests passed in both runs.

## 11. Suite duration

About 2 minutes 12 seconds, then 2 minutes 43 seconds. Nothing over 5 seconds.

## 12. Slowest tests

| Test | Time | Why |
|---|---:|---|
| `test_page_size_and_adjacent_pages_have_unique_ids` | 3.97s | Several full queue pages |
| `test_review_pagination` | 3.26s | Review queue pagination |
| `test_local_action_timings` | 2.56s | Timed local actions |
| `test_migration_round_trip` | 2.31s | Upgrade to head and downgrade to base |
| `test_run_33_placeholders_replay_without_normalization_error` | 1.61s | Two offline Radar 1 runs |
| `test_run_35_placeholders_normalize_and_persist` | 1.54s | Offline Radar 1 replay |
| `test_ten_clicks_execute_once[next]` | 1.43s | Repeated callback handling |
| `test_regenerate_invalidates_old_code_and_sessions` | 1.35s | Access-code hashing |
| `test_i_rapid_suivant_one_effective_transition` | 1.34s | Queue transition |
| `test_strong_evidence_resolves_medium_confidence...` | 1.33s | Persistence plus review |

The second run's slowest items were the same access-code and queue tests, all under 3 seconds.

## 13. Repeated-run stability

Both complete runs were 806 passed. The production-acceptance inflight test finished in the full suite instead of blocking it.

## 14. Alembic state

`flask db heads` and `flask db current` are both `c4d8e1a72b05 (head)`.

## 15. Migration status

No new revision. The launcher migration that is already at head was edited to use batch mode. Databases already stamped `c4d8e1a72b05` do not re-run it. A fresh upgrade, including the SQLite test databases, applies the same launcher column, foreign key, and index.

## 16. Remaining limitations

- `app/core/internal_api.py` still describes an unmounted bearer-token run list. The public session routes are the API under test.
- Tests block real `httpx` and `urllib` opens, and the test search provider is `disabled`. A script that is launched by hand can still load `.env`.
- `run_bot.py` still retries Telegram polling forever when the network fails. Tests patch that entry point; the suite does not start polling.
