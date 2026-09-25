# Access Code Authentication Report

## Architecture and migration

The previous web authentication used one environment-configured email and password hash and had no durable user entity. The final implementation has one authentication path: `POST /api/auth/access`.

`User` stores display name, ADMIN/USER role, active status, access-code hash, session version, and lifecycle timestamps. `AuthAuditEvent` stores meaningful authentication and management events without secrets. Migration `31a4c96de702` adds only these two tables. Existing Radar runs, results, reviews, Targeted Search data, and historical numeric actor values remain untouched; new business actions use the new database user ID.

## Code and session security

Codes contain ten cryptographically random characters formatted `XXXX-XXXX-XX`, excluding ambiguous characters. A salted Werkzeug hash is stored. Raw codes appear only in create, regenerate, and reactivate responses and are never logged.

Signed HttpOnly Flask sessions last 30 days. Production cookies use Secure and SameSite=None for Vercel-to-Render credentials. Each protected request reloads the user and checks active status and session version. Regeneration and deactivation therefore revoke existing sessions immediately.

Login applies a process-local limit of five failed attempts per IP and a 15-minute cooldown. This is suitable for the current small single-instance deployment; multiple workers or instances would require a shared limiter.

## Roles and lifecycle

USER can use all Radar, review, history, and Targeted Search features. ADMIN adds user management. Server-side authorization protects all admin endpoints. Reactivation always generates a fresh code, and the last active ADMIN cannot be deactivated.

Bootstrap:

```bash
flask --app wsgi create-admin --name "Aymane"
```

## Endpoints and frontend

- `POST /api/auth/access`, `GET /api/auth/me`, `POST /api/auth/logout`
- `GET/POST /api/admin/users`
- `POST /api/admin/users/{id}/regenerate-code`
- `POST /api/admin/users/{id}/deactivate`
- `POST /api/admin/users/{id}/reactivate`
- `/login` contains only the application label, access-code field, and submit action.
- `/admin/users` provides creation, one-time copy, regeneration, deactivation, and reactivation.

Login, user lifecycle, Radar launch, approval, and rejection actions are audited without raw access codes. The backend suite covers login, inactive users, sessions, logout, authorization, creation, hash storage, regeneration, revocation, reactivation, last-admin protection, and audit safety.
