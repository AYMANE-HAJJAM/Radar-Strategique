# Radar 1 Telegram presentation update

This update changes presentation only. Search, deduplication, AI analysis, deterministic validation, persistence, official-link selection, pagination size, review decisions, audit behavior and Radars 2–5 are unchanged.

Radar 1 cards now show a shortened title plus only populated buyer, location, reference and deadline fields. Review cards show one prioritized French reason; current cards show a readable status when useful. URLs stay out of message bodies and are available through **🔗 Ouvrir**. Each result has **ℹ️ Détails**, which opens a separate concise plain-text message containing the full title and additional readable fields without raw JSON, internal flags or enum codes.

Manual-review buttons use two compact rows: open/details, then approve/reject. Current results use only open/details. Approval and rejection edit the original card to `✅ Validé` or `❌ Rejeté` and remove its buttons. Invalid or stale actions receive `Cette action n’est plus disponible.` without database details. Pagination remains five records per page, with one navigation message showing `Page N/T` and a separate return row.

All result text explicitly uses Telegram plain-text mode. Titles containing `&`, `<`, `>`, `_`, `*` or parentheses therefore need no markup escaping and cannot break formatting. Callback data contains only a compact action, result ID, existing 12-character evidence-version token and page number; tests verify the Telegram 64-byte limit. Message text is bounded below Telegram’s limit.

## Validation

- Full suite: **135 passed**.
- Compilation: `python -m compileall -q app scripts migrations run.py run_bot.py` passed.
- Dependencies: `python -m pip check` reported no broken requirements.
- Tests block all HTTP; no real OpenAI, web search or Telegram calls were made.
- Presenter tests cover compact cards, intelligent title truncation, omitted empty fields, URLs hidden from bodies, French reason/status/type/link labels, PMMP/domain labels, special-character safety and details output.
- Handler tests cover open/details/return buttons, in-place reject/approve behavior, stale actions and unchanged five-result pagination.
- The existing backend and migration tests remain green. No migration or environment change is required for this presentation update.

## Changed files

New:

```text
app/bot/presenters/__init__.py
app/bot/presenters/result_presenter.py
tests/test_result_presenter.py
RADAR1_TELEGRAM_UX_CHANGES.md
```

Modified:

```text
app/bot/markets.py
app/bot/handlers.py
app/services/market_review_service.py
tests/test_market_usability.py
README.md
```

`market_review_service.page()` gained an optional total-page count for display and `detail()` gained a read-only single-record lookup. Neither changes eligibility, ordering, review decisions or storage.

## Telegram check

Restart the bot so Python loads the new presentation code:

```powershell
.\.venv\Scripts\python.exe run_bot.py
```

In a private chat from an allowlisted account:

1. Send `/start` and select **Radar 1 — Marchés**.
2. Open **🆕 Voir les nouveautés** or **⚠️ À vérifier**.
3. Confirm each page has at most five short cards and one `Page N/T` navigation message.
4. Tap **🔗 Ouvrir** and verify Telegram opens the existing best source URL.
5. Tap **ℹ️ Détails**, then **⬅️ Retour** to reload the current page.
6. On a review card, tap **✅ Valider** or **❌ Rejeter** and confirm that card changes in place. Backend audit records are preserved exactly as before.

No database upgrade is needed if migration `d91eac4206b1` was already applied for the existing manual-review feature. If it was not, run `python -m flask --app run db upgrade` before testing review decisions.
