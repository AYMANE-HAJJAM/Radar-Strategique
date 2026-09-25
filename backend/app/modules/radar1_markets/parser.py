from app.core.dates import parse_fr_date
from app.modules.radar1_markets.policy import detail_url, aggregate_title
from urllib.parse import urlsplit

from app.modules.radar1_markets.schemas import MarketCandidate
from app.integrations.pmmp.client import is_pmmp, is_direct_notice
from app.modules.radar1_markets.institutional_search import official_institution
from app.core.validation import today_in_morocco


def parse_date(value):
    return parse_fr_date(value)


def normalize_hit(hit, official_domains=()):
    host = (urlsplit(hit.url).hostname or '').lower()
    direct = is_direct_notice(hit.url)
    official = direct or (not is_pmmp(hit.url) and official_institution(hit.url, official_domains))
    confirmed = official and hit.official_notice and bool(hit.evidence) and detail_url(hit.url) and not aggregate_title(hit.title)
    quality = 'OFFICIAL_PRIMARY' if direct and confirmed else ('OFFICIAL_SECONDARY' if confirmed else 'DISCOVERY_ONLY')
    mode = 'DIRECT_OFFICIAL' if direct else ('INDIRECT_PMMP_SEARCH' if is_pmmp(hit.url) else
                                          'OFFICIAL_INSTITUTION' if official else 'SECONDARY_DISCOVERY')
    pub, deadline = parse_date(hit.publication_date), parse_date(hit.deadline)
    role = 'OFFICIAL_PROCUREMENT' if is_pmmp(hit.url) else 'OFFICIAL_INSTITUTIONAL' if official else 'PROCUREMENT_AGGREGATOR' if host in {'marchesfaciles.ma', 'www.marchesfaciles.ma'} else 'DISCOVERY_ONLY'
    return MarketCandidate(source_type=role, title=hit.title, url=hit.url if mode != 'INDIRECT_PMMP_SEARCH' else None,
        source=host, institution=hit.institution, reference=hit.reference, publication_date=pub, deadline=deadline,
        raw_text=hit.evidence, morocco_related=True if hit.execution_country == 'MA' and hit.location else
        (False if hit.execution_country and hit.execution_country != 'MA' else None),
        location_evidence=hit.location, source_status=hit.status, procedure_type=hit.procedure_type,
        official_url=hit.url if confirmed else None, official_confirmation=confirmed,
        official_date_evidence=hit.official_date_evidence if confirmed else None, source_quality=quality,
        official_url_status='VERIFIED_DIRECT' if confirmed and direct else 'VERIFIED_INSTITUTIONAL' if confirmed else
            'INDIRECT_PMMP' if mode == 'INDIRECT_PMMP_SEARCH' else 'SECONDARY_ONLY',
        access_mode=mode, current_evidence=confirmed and (hit.status == 'open' or bool(deadline and deadline >= today_in_morocco())), deadline_at=hit.deadline_at,
        source_conflict=hit.source_conflict or bool(hit.deadline and deadline is None),
        metadata={'discovery_url': hit.url, 'evidence_origin': 'search_provider_extraction'})
