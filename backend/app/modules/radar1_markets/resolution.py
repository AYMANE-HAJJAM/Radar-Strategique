"""Official verification is separate from tender lifecycle and business priority."""
from urllib.parse import urlsplit

from app.modules.radar1_markets.policy import aggregate_title, folded, source_role
from app.core.validation import today_in_morocco

VERIFIED = 'VERIFIED_OFFICIAL'
CREDIBLE = 'UNVERIFIED_BUT_CREDIBLE'
UNRESOLVED = 'UNRESOLVED'


def strong_identity(candidate, config):
    url = candidate.metadata.get('discovery_url') or candidate.url
    if not url or urlsplit(url).scheme not in {'http', 'https'}:
        return False
    if source_role(url, config) not in {'PROCUREMENT_AGGREGATOR', 'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}:
        return False
    if candidate.source_conflict or candidate.reference_conflict or aggregate_title(candidate.title):
        return False
    title = folded(candidate.title)
    meaningful = len(title.split()) >= 2 and title != folded(candidate.reference)
    reference = bool(candidate.reference and any(c.isdigit() for c in candidate.reference))
    buyer = bool(candidate.institution and len(folded(candidate.institution)) >= 3)
    return bool((reference and buyer) or (reference and meaningful) or (meaningful and buyer))


def credible_fallback(candidate, config, as_of=None):
    """Known dates keep their freshness guards; absent dates require human review."""
    today = as_of or today_in_morocco()
    if not strong_identity(candidate, config) or candidate.morocco_related is not True:
        return False
    if candidate.source_status in {'closed', 'expired', 'awarded', 'cancelled'}:
        return False
    if candidate.publication_date and candidate.publication_date > today:
        return False
    if candidate.deadline and candidate.deadline < today:
        return False
    if candidate.deadline_at:
        from datetime import datetime, timezone
        if candidate.deadline_at <= datetime.now(timezone.utc):
            return False
    return bool((not candidate.deadline and not candidate.publication_date) or
                (candidate.deadline and candidate.deadline >= today) or
                (candidate.publication_date and 0 <= (today - candidate.publication_date).days <= 30))


def with_resolution(candidate, state, *, error=None, attempts=()):
    discovery = candidate.metadata.get('discovery_url') or candidate.url
    audit = dict(source_status=state, source_type=candidate.source_type,
                 discovery_url=discovery, official_url=candidate.official_url if state == VERIFIED else None,
                 resolution_attempted=True, resolution_error=error,
                 resolution_confidence=1.0 if state == VERIFIED else 0.0,
                 attempts=list(attempts))
    updates = dict(resolution_state=state, resolution_attempted=True, resolution_error=error,
                   metadata={**candidate.metadata, 'resolution': audit},
                   resolution_confidence=audit['resolution_confidence'])
    if state != VERIFIED:
        updates.update(url=discovery, official_url=None, official_confirmation=False, detail_verified=False,
                       official_url_status='SECONDARY_ONLY', source_quality='RELIABLE_SECONDARY',
                       access_mode='SECONDARY_DISCOVERY', dce_available=False, dce_url=None,
                       dce_size=None, dce_access_mode='NOT_FOUND')
    return candidate.model_copy(update=updates)
