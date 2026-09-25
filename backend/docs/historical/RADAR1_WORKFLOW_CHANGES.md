# Radar 1 workflow lifecycle

Radar 1 now has one operational queue: **📥 À traiter**. Every new actionable result waits for a human decision. **✅ Validés** and **❌ Rejetés** are decision archives, while **🕘 Recherches précédentes** is paginated execution history. The prior Nouveautés, À vérifier and Historique labels are removed from the Radar 1 menu. Radars 2–5 keep their existing menus and empty live collectors.

## State model

Two database columns represent independent dimensions:

```text
Discovery: NEW → UNCHANGED
               ↘ UPDATED → UNCHANGED

Review:    PENDING → APPROVED
                 ↘ REJECTED
APPROVED/REJECTED → PENDING when a meaningful commercial update is saved
```

A new relevant result is `NEW + PENDING`. Approval/rejection changes only the human state. Rediscovery without meaningful change sets `UNCHANGED`, preserves the human state, updates `last_seen_at`, skips AI and does not requeue processed results. A commercial change sets `UPDATED + PENDING`; prior decisions stay in audit history. Metadata-only cleanup does not reopen review and is treated as unchanged before classification.

Meaningful fields are title, institution, reference, deadline, source status, official URL, procedure type and official confirmation. This covers extensions, relaunches, reopened status, improved official links and material identity/scope changes. Existing deterministic rules still reject expired, closed or irrelevant candidates before they become actionable.

The legacy `Result.status` column remains synchronized for compatibility and for unchanged Radars 2–5. Radar 1 queue queries use only `review_status`. Automatic pipeline rejection leaves `review_status` empty because no human decision occurred; the run still counts it under “Rejetés automatiquement.”

## Migration

Migration `e42f6d3a901c` adds nullable, indexed `discovery_status`, `review_status`, `reviewed_by`, `reviewed_at` and JSON `update_reason` fields plus validated state constraints. It also adds `result_audit_events` with event type, result, actor, time and JSON metadata.

Existing Radar 1 data maps as follows:

- Latest `market_reviews` approval → `APPROVED`.
- Latest `market_reviews` rejection → `REJECTED`.
- Existing `new`, `updated` or `manual_review` row without a human decision → `PENDING`.
- Existing automatic rejection has no human review status.
- Discovery state maps from the legacy discovery value when available; mixed review/rejection rows conservatively become `UNCHANGED`.

All existing results, observations, human review records, fingerprints, first/last-seen timestamps, analysis and radar metadata remain. The migration seeds DISCOVERED events for existing Radar 1 rows and APPROVED/REJECTED events from the complete prior review table. It does not reset data. Downgrade removes the new state/event fields but leaves all pre-existing data and `market_reviews` intact.

## Telegram workflow

Radar 1 menu:

```text
🔍 Lancer une recherche
📥 À traiter
✅ Validés
❌ Rejetés
🕘 Recherches précédentes
⬅️ Retour
```

À traiter sorts by latest discovery/update, then closest deadline and priority. Updated records show `🔄 Mise à jour`. It retains the five-card pagination, compact presentation, direct-link button, details and stale-button protection. Validés/Rejetés show five compact cards per page with open/details buttons and no decision controls.

The completion message contains new, updated, already-known, automatically rejected and pending counts. Its buttons open À traiter or Recherches précédentes. Run history shows date/time, found/new/updated/already-known/automatic-rejection counts and duration, five runs per page.

## Validation and deployment

Tests block network calls. The suite covers state migration, exclusive queues, decisions, unchanged approved/rejected rediscovery, AI skipping, meaningful reopening, metadata-only changes, audit events, menu labels, run counts/history, stale callbacks, pagination and existing official-link/filtering behavior.

Stop the bot, back up PostgreSQL, then apply the additive migration and restart:

```powershell
.\.venv\Scripts\python.exe -m flask --app run db upgrade
.\.venv\Scripts\python.exe run_bot.py
```

From an allowlisted private Telegram account: send `/start`, choose Radar 1, run a search, open À traiter, approve one item and reject another, then verify each appears only in its respective archive. Run the same search again and confirm unchanged processed results do not return to À traiter. Recherches précédentes should display the completed run metrics and duration.

## Files

New:

```text
app/models/result_audit_event.py
app/services/result_workflow_service.py
migrations/versions/e42f6d3a901c_separate_discovery_and_review_state.py
tests/test_result_workflow.py
RADAR1_WORKFLOW_CHANGES.md
```

Modified:

```text
app/models/result.py
app/models/__init__.py
app/agents/radars/base.py
app/agents/radars/markets/agent.py
app/agents/orchestrator.py
app/services/result_service.py
app/services/market_review_service.py
app/bot/callbacks.py
app/bot/keyboards.py
app/bot/handlers.py
app/bot/jobs.py
app/bot/markets.py
app/bot/presenters/result_presenter.py
tests/test_market_usability.py
tests/test_result_presenter.py
tests/test_jobs_api.py
tests/test_migrations.py
README.md
```
