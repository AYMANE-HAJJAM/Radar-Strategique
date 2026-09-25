# Cleanup & Architecture Report

Date: 2026-09-18  
Scope: Full project audit, dead-artifact cleanup, Telegram UX contract alignment, shared review consolidation.

## A. Architecture before

- Telegram: 5 near-duplicate radar modules + specialized `markets.py`; completion CTA inconsistently gated.
- Services: shared orchestrator; `market_review_service` used by all radars despite the name.
- Entrypoints: `run_bot.py` (poller), `run.py` (Flask), many one-shot scripts and root live-validation JSON.
- UI state: callback-driven only; stray messages replied with `/start` tip; partial debounce/inflight locks.
- Docs: ~19 historical MD reports + root audit JSON cluttering the repo root.

## B. Architecture after

```
bot/
  handlers.py      auth, routing, multi-click, stray fallback
  ui_state.py      explicit UI session states + redisplay
  keyboards.py     main / radar / completion / failure
  jobs.py          launch + completion/partial/failure messaging
  compact_review.py shared Radars 2–5 queue/review handlers
  run_queue.py     exact-run queue (Radars 2–5)
  markets.py       Radar 1 specialized queue
  targeted.py      targeted search UX + state hooks
  view_state.py    pagination + message replace
services/ agents/ collectors/ models/  (unchanged business cores)
docs/historical/   archived change reports
```

## C. Files removed

| Path | Why safe |
|------|----------|
| `scripts/run_live_{projects,institutions,policies,funding}.py` | Superseded by `scripts.run_live_radar`; zero imports/docs/tests |
| `scripts/run_cost_dry_runs.py` | Thin unused wrapper; comparison scripts remain |
| `scripts/audit_radar1_queue.py` | One-shot; no references |
| `scripts/inspect_radar_data.py` | One-shot; no references |
| `scripts/probe_enrichment_sources.py` | One-shot; no references |
| `scripts/verify_clean_start.py` | Post-reset helper; no operational refs |
| `scripts/verify_source_migration.py` | Asserted obsolete Alembic head |
| `scripts/validate_institution_policy_quality.py` | Duplicate of documented validators; no refs |
| `scripts/safe_source_migration.py` | Stale head `c83d2e5f9a31`; replaced by targeted-search guard |
| `scripts/audit_passive_usage.py` | Historical one-shot |
| `app/radars/radar_*.py`, `app/radars/base.py` | Alias modules never imported; catalog uses agent registry |
| Root `radar*.json/txt`, `test-results.txt` | Disposable live-validation artifacts |
| `waitress` from `requirements.txt` | Zero project imports |

## D. Files consolidated

| Before | After |
|--------|-------|
| `projects.py` / `institutions.py` / `policies.py` / `funding.py` duplicated queue logic | `compact_review.build_handlers()` + thin per-radar formatters; projects now use `run_queue` |
| Completion keyboard variants | Single `radar_completion_keyboard` + `radar_failure_keyboard` |
| Stray-message tips scattered | `ui_state.redisplay_current` |

## E. Files retained and why

- `run_bot.py` — production Telegram poller  
- `run.py` — Flask factory / migrations / seed  
- `scripts/run_live_radar.py`, `reset_radar_data.py`, `usage_audit.py`, `check_openai.py`, `test_agent.py`, validation/comparison scripts still documented  
- `app/radars/__init__.py` — live catalog facade for menus/seed  
- Full `migrations/versions` through `f19a7c4d2e61` — **unchanged**  
- `markets.py` — Radar 1 presentation/details/back remain specialized  

## F. Dead code removed

Unused radar alias modules, obsolete scripts, root audit JSON, unused `waitress` dependency, dead `radar1_completion_keyboard` / unreachable legacy keyboard branch.

## G. Duplicate logic consolidated

Shared compact review builder for Radars 2–5; exact-run path unified via `run_queue` (including Radar 2); shared completion/failure keyboards; shared UI state fallback.

## H. Startup / entrypoint cleanup

**Production Telegram:** `python run_bot.py`  
**Migrations/seed:** `flask --app run db upgrade` then `flask --app run seed-radars`  
**Optional HTTP:** `python run.py`  
No alternate poller remains.

## I. Telegram UI / state architecture

`UIState` values: MAIN_MENU, RADAR_MENU, RADAR_RUNNING, RADAR_COMPLETION, RADAR_QUEUE, RADAR_DETAILS, TARGETED_*.  
Stored in `context.user_data['ui_state']` (transient, not DB).

## J. Global stray-message behavior

Outside text-expecting states → `redisplay_current` (same menu/options).  
Targeted input + non-text → guidance + prompt; state preserved.

## K. Global multi-click behavior

Kept: `concurrent_updates=False`, per-(user, callback) inflight set, 1s debounce.  
DB-backed SearchRun lock unchanged.  
First valid click wins until render completes.

## L. Radar behavior verification (contract)

| Rule | Status |
|------|--------|
| Shared radar menu (🔎/À traiter/Validés/Rejetés/History/Retour) | Yes |
| Launch ack `🔄 Radar X lancé…` | Yes |
| Completion with actionable → Voir + Retour only | Yes |
| Completion zero actionable → Retour only | Yes |
| No History on completion | Yes |
| Exact-run Voir queue | Yes (`run_actionable_count` includes `manual_review` obs) |
| Partial → `⚠️ Radar X terminé partiellement` | Yes |
| Failed → message + Réessayer/Retour | Yes |
| Active run → `⏳ Une recherche est déjà en cours.` | Yes |

## M. Targeted Search verification

Menu / free-text prompt / confirmation / no-result Affiner+Retour / refinement session / UI state hooks updated. Stale brief lock unchanged in service.

## N. Cost behavior

Zero-cost UI paths unchanged (menus, queues, history, validate/reject, drafting). Search/AI still only on launch paths with daily caps.

## O. Tests before / after

Added `tests/test_ui_contract.py`. Updated jobs/bot/run-scoped/market-usability/collection-diagnostics for new keyboards and messages. Full suite run as part of validation.

## P. Production migrations changed?

**NO.** No schema migrations added or rewritten.

## Q. Config / env cleanup

Removed unused `waitress` dependency. Required env remains documented in `.env.example` / README. Historical reports moved to `docs/historical/`.

## R. Remaining technical debt

1. Rename `market_review_service` / `MarketReview` to radar-neutral names (behavior OK).  
2. Move Telegram ACL out of `decide()` into bot layer.  
3. Markets still uses custom queue message tracking vs `view_state`.  
4. Unused agent `PROMPT` string attributes (runtime uses `get_analysis_prompt()`).  
5. `audit-output/` still gitignored local evidence (not cleaned; disposable).  
6. Further presenter consolidation for Radars 2–5 cards.

## S. Exact production restart command

```powershell
# Stop the running bot (Ctrl+C in the bot terminal), then:
cd "c:\Users\Aymane_Hajjam\Documents\My Project\Boot Telegram"
.\.venv\Scripts\python.exe run_bot.py
```

No DB upgrade required for this cleanup.
