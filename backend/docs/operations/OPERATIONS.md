# Operations

## Start / stop bot

```powershell
cd "c:\Users\Aymane_Hajjam\Documents\My Project\Boot Telegram"
.\.venv\Scripts\python.exe run_bot.py
```

Stop with Ctrl+C (graceful worker shutdown).

Only one poller per `TELEGRAM_BOT_TOKEN`.

## Database migrations

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app db current
.\.venv\Scripts\python.exe -m flask --app app:create_app db upgrade
.\.venv\Scripts\python.exe -m flask --app app:create_app seed-radars
```

Current head: `f19a7c4d2e61` (targeted search). Do not rewrite historical revisions.

## Add a Telegram user

Set `ALLOWED_TELEGRAM_USER_IDS` in `.env` to comma-separated numeric IDs.
Restart the bot. Empty allowlist denies everyone.

## Backups

- Directory: `backups/` (gitignored).
- Produced by `scripts/reset_radar_data.py` and migration guard scripts.
- Naming: `radar-data-*`, `*-migration-*` with checksums.
- **Never delete production backups** as part of cleanup.

Restore: use the matching restore path documented by the script that created the snapshot
(`reset_radar_data.py --help`).

## Stale-run recovery

Active runs older than `SEARCH_RUN_STALE_MINUTES` are marked failed on the next reserve.
Manual: `flask --app app:create_app fail-orphan-run <id> --worker-stopped`.

## Monitoring API

- `GET /api/health`, `/api/ready` — process health.
- Token-gated `/api/radars`, `/api/runs` — internal ops (`INTERNAL_API_TOKEN`).

Optional HTTP (health/API only; does **not** poll Telegram):

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app run --host 127.0.0.1 --port 5000
```

## Usage / cost

```powershell
.\.venv\Scripts\python.exe -m scripts.usage_audit
.\.venv\Scripts\python.exe -m scripts.check_openai
```

Live radar dry-runs (isolated DB only when experimenting):

```powershell
.\.venv\Scripts\python.exe -m scripts.run_live_radar RADAR_1_MARKETS --help
```

## Troubleshooting

| Symptom | Check |
|---------|--------|
| Accès non autorisé | User id in allowlist; private chat |
| Une recherche est déjà en cours | Wait or recover stale run |
| Conflict / another poller | Kill duplicate `run_bot.py` |
| Migration mismatch | `db current` vs head `f19a7c4d2e61` |
| Empty allowlist warning | Set `ALLOWED_TELEGRAM_USER_IDS` |

## Safety

No production searches from ad-hoc scripts against the live bot DB without an explicit ops decision.
Do not reset production data without a verified backup.
