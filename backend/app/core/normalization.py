"""Shared generic text normalization."""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r'[^a-z0-9]+')
_NON_ALNUM_AR = re.compile(r'[^a-z0-9\u0600-\u06ff]+')


def fold_text(value, *, oe_ligature=False, keep_arabic=False):
    """NFKD casefold + strip combining marks; optional œ→oe and Arabic letter retention."""
    text = unicodedata.normalize('NFKD', value or '').casefold()
    if oe_ligature:
        text = text.replace('œ', 'oe')
    stripped = ''.join(c for c in text if not unicodedata.combining(c))
    pattern = _NON_ALNUM_AR if keep_arabic else _NON_ALNUM
    return ' '.join(pattern.sub(' ', stripped).split())
