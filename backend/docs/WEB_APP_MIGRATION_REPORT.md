# Web application migration report

## Architecture

The previous interface was a `python-telegram-bot` runtime whose handlers called the Radar services directly. The new architecture keeps Flask and the existing `modules/`, `integrations/`, `core/`, `db/`, schema, migrations, deduplication, cost controls and PMMP persistence. A modular JSON API in `app/api/` now connects those services to a Next.js application in `frontend/`.

The replacement layer no longer imports the Telegram runtime, and its dependency and environment configuration were removed. Physical deletion of `app/bot/`, `run_bot.py`, Telegram tests, and the obsolete internal API module remains approval-gated by the workspace safety policy.

## API and flows

- Health: `GET /api/health`
- Authentication: login/session/logout under `/api/auth/*`
- Radars: list, launch, run history and run polling under `/api/radars/*` and `/api/runs/*`
- Results: filtered pagination, detail, approve and reject under `/api/radars/*/results` and `/api/results/*`
- Targeted search: history, create, detail/poll, refine, run and result feedback under `/api/targeted-search/*`

Radar launch reserves the existing process-safe run lock before submitting `AgentOrchestrator.execute` to the bounded local runner. The POST returns immediately and the browser polls. Review endpoints call the canonical compare-and-set review service, retaining audit records and Radar 1 feedback invalidation. Details read persisted PMMP metadata only. Targeted search retains its persistent versioned brief and bounded discovery service.

## Authentication

No suitable User table existed, and no schema migration was created. One internal account is configured through `INTERNAL_USER_EMAIL` and a Werkzeug `INTERNAL_USER_PASSWORD_HASH`. Flask uses secure HTTP-only cookies, CSRF tokens and exact-origin credentialed CORS. There is no registration route.

## Frontend routes

- `/login`
- `/`
- `/radars/[radarId]`
- `/radars/[radarId]/runs`
- `/radars/[radarId]/results/[resultId]`
- `/targeted-search`

The UI includes server cold-start messaging, run polling, status views, tabular review, persisted detail metadata and targeted-search brief confirmation.

## Deployment

Render uses root `backend`, `pip install -r requirements.txt`, and `gunicorn wsgi:app --bind 0.0.0.0:$PORT`. Vercel uses root `frontend` with `NEXT_PUBLIC_API_URL` set to the Render origin. Set `FRONTEND_URL` on Render to the exact Vercel origin.

## Database and validation

Alembic history is unchanged and no revision was created. The new API suite passes (4 tests), Python compilation succeeds, `pip check` reports no broken requirements, and Alembic head is `f19a7c4d2e61`. Frontend typecheck, lint, and the Next.js 16.3.6 production build pass. The legacy full test collection remains blocked by the deletion-gated Telegram tests and their old package imports.
