"""Shared enums and status constants used across modules."""
from __future__ import annotations

# Canonical discovery / review statuses also live on ResultWorkflowService in
# app.core.review; re-exported here for a stable shared import path.
from app.core.review import DiscoveryStatus, ReviewStatus

__all__ = ['DiscoveryStatus', 'ReviewStatus']
