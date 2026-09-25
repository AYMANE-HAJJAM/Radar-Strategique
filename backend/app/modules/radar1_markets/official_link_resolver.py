"""Radar 1 official-link resolution using the collector's bounded query callback."""
from app.modules.radar1_markets.policy import detail_url, aggregate_title
from app.integrations.pmmp.client import is_direct_notice, is_pmmp
from app.modules.radar1_markets.institutional_search import official_institution
from app.core.dedup import normalize_text
from app.modules.radar1_markets.policy import folded
import re


class OfficialLinkResolver:
    def __init__(self, official_domains=()):
        self.domains = official_domains
        self.attempts = []

    def classify(self, candidate):
        url = candidate.official_url
        verified = candidate.official_confirmation and detail_url(url) and not aggregate_title(candidate.title)
        status = ('VERIFIED_DIRECT' if verified and is_direct_notice(url) else
                  'VERIFIED_INSTITUTIONAL' if verified and official_institution(url, self.domains) and not is_pmmp(url) else
                  'INDIRECT_PMMP' if is_pmmp(candidate.metadata.get('discovery_url') or candidate.url or '') else
                  'SECONDARY_ONLY' if candidate.url or candidate.metadata.get('discovery_url') else 'NOT_FOUND')
        return candidate.model_copy(update={'official_url_status': status})

    @staticmethod
    def matches(original, found):
        # Never promote an unrelated notice returned by a confirmation search.
        if original.reference and not original.institution:
            return (folded(original.reference) == folded(found.reference) and
                    (folded(original.title) == folded(original.reference) or
                     len(folded(found.title).split()) >= 2 and folded(found.title) in folded(original.title)))
        def buyer(value):
            return folded(re.sub(r'^[A-Z0-9 ]+/[A-Z0-9 ]+\s+-\s+', '', value or ''))
        if not original.institution or buyer(original.institution) != buyer(found.institution):
            return False
        if original.reference:
            return folded(original.reference) == folded(found.reference)
        return normalize_text(original.title) == normalize_text(found.title)

    @classmethod
    def merge_secondary_procurement(cls, original, found):
        """Use a secondary estimate only after strong tender identity matching."""
        if found.estimated_amount is not None or original.estimated_amount is None or not cls.matches(original, found):
            return found
        return found.model_copy(update={
            'estimated_amount': original.estimated_amount,
            'estimated_currency': original.estimated_currency,
            'estimated_amount_tax_mode': original.estimated_amount_tax_mode,
            'estimated_amount_source': original.estimated_amount_source,
            'estimated_amount_verified': False,
            'estimated_lots': original.estimated_lots})

    def resolve(self, candidate, search):
        candidate = self.classify(candidate)
        if candidate.official_url_status == 'VERIFIED_DIRECT':
            return candidate
        self.attempts = []
        queries = []
        if candidate.reference:
            queries.append(f'site:marchespublics.gov.ma "{candidate.reference}"')
            variant = folded(candidate.reference)
            queries.append(f'site:marchespublics.gov.ma "{variant}" "{candidate.institution or ""}"')
        fragment = ' '.join(candidate.title.split()[:14]).replace('"', '')
        queries.append(f'site:marchespublics.gov.ma "{fragment}" "{candidate.institution or ""}"')
        # Buyer/institution domains are restricted to the existing official whitelist.
        for domain in self.domains:
            if domain != 'marchespublics.gov.ma':
                queries.append(f'site:{domain} "{candidate.reference or fragment}" "{candidate.institution or ""}" consultation')
        found = []
        for query in dict.fromkeys(queries):
            self.attempts.append(query)
            batch = [self.classify(item) for item in search(query)]
            found.extend(batch)
            if any(item.official_url_status in {'VERIFIED_DIRECT', 'VERIFIED_INSTITUTIONAL'}
                   and self.matches(candidate, item) for item in batch):
                break
        options = [item for item in found if self.matches(candidate, item) and
                   item.official_url_status in {'VERIFIED_DIRECT', 'VERIFIED_INSTITUTIONAL'}]
        if candidate.official_url_status == 'VERIFIED_INSTITUTIONAL':
            options.append(candidate)
        if not candidate.institution and len({(item.reference, item.institution) for item in options}) > 1:
            return candidate
        if not options:
            return candidate
        best = min(options, key=lambda item: item.official_url_status != 'VERIFIED_DIRECT')
        # Use the official snapshot, not a merge of unverified secondary facts.
        return best.model_copy(update={'url': best.official_url, 'metadata': {
            **best.metadata, 'discovery_url': candidate.metadata.get('discovery_url') or candidate.url,
            'resolved_from': candidate.url, 'official_resolved_from': candidate.url,
            'original_discovery_url': candidate.metadata.get('original_discovery_url') or candidate.url,
            'pipeline': candidate.metadata.get('pipeline')}})
