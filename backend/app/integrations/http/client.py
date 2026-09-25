"""Shared HTTP session helpers used by page fetchers."""
from __future__ import annotations

# Concrete fetch behavior lives in app.integrations.http.html (PublicPages).
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = 'BootTelegramBot/1.0'
