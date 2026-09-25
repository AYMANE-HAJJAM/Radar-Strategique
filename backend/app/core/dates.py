"""Shared datetime parsing helpers."""
from __future__ import annotations

from datetime import datetime

_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y')


def parse_fr_date(value):
    """Parse common ISO / FR date prefixes; return date or None."""
    if not value:
        return None
    text = str(value).strip()
    for candidate in dict.fromkeys((text[:10], text)):
        for pattern in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    return None
