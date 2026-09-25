"""DB access for TargetedSearch* models."""
from __future__ import annotations

from app.db.models import (
    TargetedSearchBriefVersion,
    TargetedSearchFeedback,
    TargetedSearchResultLink,
    TargetedSearchSession,
)

__all__ = [
    'TargetedSearchSession', 'TargetedSearchBriefVersion',
    'TargetedSearchResultLink', 'TargetedSearchFeedback',
]
