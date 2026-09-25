"""Shared constants for Telegram UX (single source of truth)."""

from app.core.constants import PAGE_SIZE  # re-export for bot packages

RADAR_CODES = (
    'RADAR_1_MARKETS',
    'RADAR_2_PROJECTS',
    'RADAR_3_INSTITUTIONS',
    'RADAR_4_POLICIES',
    'RADAR_5_FUNDING',
)

RADAR_PREFIXES = {
    'RADAR_1_MARKETS': 'm',
    'RADAR_2_PROJECTS': 'p',
    'RADAR_3_INSTITUTIONS': 'i',
    'RADAR_4_POLICIES': 'l',
    'RADAR_5_FUNDING': 'f',
}

COMPLETION_LABELS = {
    'RADAR_1_MARKETS': '📥 Voir les offres',
    'RADAR_2_PROJECTS': '📥 Voir les projets',
    'RADAR_3_INSTITUTIONS': '📥 Voir les institutions',
    'RADAR_4_POLICIES': '📥 Voir les politiques',
    'RADAR_5_FUNDING': '📥 Voir les financements',
}

__all__ = ['PAGE_SIZE', 'RADAR_CODES', 'RADAR_PREFIXES', 'COMPLETION_LABELS']
