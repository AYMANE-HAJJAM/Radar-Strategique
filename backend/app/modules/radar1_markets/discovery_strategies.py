"""Adaptive, source-scoped Radar 1 discovery planning."""
from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlencode


@dataclass(frozen=True)
class DiscoveryQuery:
    strategy: str
    family: str
    text: str
    domains: tuple[str, ...]
    recency_days: int
    phase: int
    base_rank: int
    variant: int = 0


@dataclass(frozen=True)
class DirectDiscovery:
    strategy: str
    family: str
    url: str
    variant: int = 0


# Ordered fallback ladders. Later variants run only after insufficient yield.
# Each provider query uses one compact related-concept family and avoids Boolean syntax.
FAMILY_TERMS = {
    'architecture': ('etudes architecturales patrimoine', 'conception architecturale grand projet', 'diagnostic architectural patrimoine'),
    'competition': ('concours architectural', 'concours de conception architecturale'),
    'major_architecture': ('maitrise oeuvre grand equipement public', 'conception suivi grand projet architectural'),
    'rehabilitation': ('etude restauration conservation patrimoine', 'etude rehabilitation reconversion patrimoine'),
    'urbanism': ('medina ancienne ville', 'revitalisation centre historique'),
    'territorial_studies': ('etude valorisation patrimoine culturel', 'etude circuits sites patrimoniaux'),
    'project_management': ('amo plan sauvegarde patrimoine', 'suivi travaux restauration patrimoniale', 'diagnostic inventaire patrimonial'),
    'built_environment': ('bati ancien menacant ruine', 'remparts murailles fortifications', 'kasbah ksar fondouk'),
    'technical_studies': ('etude technique consolidation batiment historique',),
}

FAMILY_MARKERS = {
    'architecture': ('architect', 'concours architectural'),
    'competition': ('concours architectural', 'concours d architecture', 'concours de conception'),
    'major_architecture': ('grand projet architectural', 'grand equipement public',
                           'complexe architectural', 'conception architecturale'),
    'rehabilitation': ('rehabilitation', 'renovation', 'reconversion', 'restauration'),
    'urbanism': ('urban', 'plan d amenagement', 'charte architecturale'),
    'territorial_studies': ('territorial', 'amenagement du territoire'),
    'project_management': ('maitrise d oeuvre', 'assistance a maitrise', 'suivi des travaux'),
    'built_environment': ('espace public', 'corniche', 'jardin public', 'equipement public'),
    'technical_studies': ('etude technique', 'controle et coordination'),
}


def matches_family(title, family):
    """Diagnostic category matcher; discovery no longer rejects on this basis."""
    value = unicodedata.normalize('NFKD', title or '').casefold().replace('œ', 'oe')
    value = ' '.join(re.sub(r'[^a-z0-9]+', ' ',
        ''.join(c for c in value if not unicodedata.combining(c))).split())
    return any(marker in value for marker in FAMILY_MARKERS.get(family, ()))


def _pmmp_url(term):
    return 'https://www.marchespublics.gov.ma/index.php?' + urlencode({
        'keyWord': term, 'page': 'entreprise.EntrepriseAdvancedSearch', 'searchAnnCons': ''})


def direct_discovery_plan(config):
    whitelist = set(config.get('RADAR1_SOURCE_WHITELIST', ()))
    pmmp = []
    if 'marchespublics.gov.ma' in whitelist:
        for family, terms in FAMILY_TERMS.items():
            for variant, term in enumerate(terms):
                pmmp.append(DirectDiscovery('PMMP', family, _pmmp_url(term), variant))
    aggregator = []
    if 'marchefacile.ma' in whitelist:
        base = 'https://marchefacile.ma/appels-offres/secteur/services-architecturales-et-topographiques'
        aggregator.extend((DirectDiscovery('AGGREGATOR', 'architecture', base),
                           DirectDiscovery('AGGREGATOR', 'architecture', base + '?page=2', 1)))
    # Establish source diversity early, then expand the productive paths.
    return pmmp[:1] + aggregator[:1] + pmmp[1:] + aggregator[1:]


class PmmpDiscoveryStrategy:
    name = 'PMMP'
    def __init__(self, domains): self.domains = tuple(domains)
    def queries(self, mode='normal_coverage'):
        rows = []
        for rank, (family, terms) in enumerate(FAMILY_TERMS.items()):
            for variant, term in enumerate(terms):
                rows.append(DiscoveryQuery(self.name, family,
                    f'site:marchespublics.gov.ma "{term}"', self.domains,
                    (1, 3, 7, 30)[min(variant, 3)], variant + 1, rank, variant))
        return rows


class AggregatorDiscoveryStrategy:
    name = 'AGGREGATOR'
    def __init__(self, domains): self.domains = tuple(domains)
    def queries(self, mode='normal_coverage'):
        if not self.domains: return []
        preferred = sorted(self.domains, key=lambda d: (d != 'marchefacile.ma', d))
        return [DiscoveryQuery(self.name, 'architecture', 'restauration patrimoine Maroc',
            (preferred[0],), 7, 1, 20)]


class InstitutionalDiscoveryStrategy:
    name = 'INSTITUTIONAL'
    def __init__(self, domains): self.domains = tuple(domains)
    def queries(self, mode='normal_coverage'):
        if not self.domains: return []
        return [
            DiscoveryQuery(self.name, 'architecture', 'appels offres etude patrimoniale',
                self.domains, 30, 1, 21),
            DiscoveryQuery(self.name, 'urbanism', 'consultations rehabilitation medina',
                self.domains, 30, 2, 22),
        ]


def build_discovery_plan(config, *, mode='normal_coverage', performance=None):
    whitelist = set(config.get('RADAR1_SOURCE_WHITELIST', ()))
    official = tuple(config.get('RADAR1_OFFICIAL_DOMAINS') or ())
    institutional = tuple(dict.fromkeys((*official, 'culture.gov.ma', 'alomrane.gov.ma')))
    strategies = (PmmpDiscoveryStrategy(('marchespublics.gov.ma',) if 'marchespublics.gov.ma' in whitelist else ()),
                  AggregatorDiscoveryStrategy(tuple(d for d in config.get('RADAR1_AGGREGATOR_DOMAINS', ()) if d in whitelist)),
                  InstitutionalDiscoveryStrategy(tuple(d for d in institutional if d in whitelist)))
    queries = [query for strategy in strategies for query in strategy.queries(mode)]
    history = performance or {}
    def score(query):
        stats = history.get(f'{query.strategy}:{query.family}', {})
        runs = max(1, stats.get('executions', 0))
        quality = (stats.get('usable_observations', 0) + stats.get('relevant_candidates', 0) +
                   2 * stats.get('official_resolution_success', 0) - stats.get('duplicates_skipped', 0) -
                   stats.get('generic_pages', 0) - stats.get('parser_failures', 0)) / runs
        return (query.phase, -quality + stats.get('zero_results', 0) / runs, query.base_rank)
    return sorted(queries, key=score)
