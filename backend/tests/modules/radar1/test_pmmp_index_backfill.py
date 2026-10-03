"""One-time PMMP index → Radar 1 business backfill."""
from types import SimpleNamespace
from unittest.mock import Mock

from app.db.extensions import db
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.modules.radar1_markets.collector import MarketsCollector
from app.modules.radar1_markets.pmmp_listing_collector import SOURCE
from app.modules.radar1_markets.pmmp_listing_index import import_baseline
from app.modules.radar1_markets.pmmp_listing_collector import PmmpListing
from app.modules.radar1_markets.pmmp_index_backfill import (
    backfill_from_index, cheap_listing_prefilter, classify_trace_outcomes,
)


def _config(**overrides):
    values = {
        'SOURCE_HTTP_TIMEOUT_SECONDS': 5,
        'RADAR1_SOURCE_WHITELIST': ('marchespublics.gov.ma',),
        'RADAR1_AGGREGATOR_DOMAINS': (),
        'RADAR1_DISCOVERY_DOMAINS': (),
        'RADAR1_KEYWORD_GROUPS': {},
        'RADAR1_DISCOVERY_MODE': 'legacy',
        'RADAR1_MAX_CANDIDATES': 500,
        'MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD': 20_000_000,
        'RADAR1_DISCOVERY_MAX_CALLS': 0,
        'RADAR1_RESOLUTION_MAX_CALLS': 0,
    }
    values.update(overrides)
    return values


def listing(**changes):
    values = dict(
        source=SOURCE, consultation_id='1036481', organization='j8k',
        reference='04/2026/AUS',
        title='Etude de valorisation du patrimoine culturel de Settat',
        buyer='Agence urbaine de Settat', publication_date='03/09/2026',
        deadline='02/10/2026 11:00', procedure="Appel d'offres ouvert",
        category='Services', location='SETTAT',
        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                    'page=entreprise.EntrepriseDetailsConsultation'
                    '&refConsultation=1036481&orgAcronyme=j8k'),
    )
    values.update(changes)
    return PmmpListing(**values)


class AcceptingRadar:
    def validate_candidate(self, candidate):
        return SimpleNamespace(accepted=True, reasons=[])


def test_cheap_prefilter_skips_pure_works():
    gate = cheap_listing_prefilter(listing(
        title='Travaux de construction de route rurale',
        procedure="Appel d'offres ouvert", category='Travaux'))
    assert gate['decision'] == 'reject'


def test_cheap_prefilter_keeps_heritage_study():
    gate = cheap_listing_prefilter(listing())
    assert gate['decision'] == 'continue'


def test_backfill_skips_prefilter_and_processes_plausible(app, monkeypatch):
    processed = []

    def fake_process(self, hit, radar, stats, discovery=None):
        processed.append(hit.reference)
        self.report.candidates.append(SimpleNamespace(
            reference=hit.reference, resolution_state='VERIFIED',
            publication_date=None, business_category='P1_HERITAGE',
            metadata={'business_relevance': {'decision': 'keep',
                                             'business_category': 'P1_HERITAGE',
                                             'reason_code': 'ACCEPT_HERITAGE_PROFESSIONAL_SERVICE'}}))
        self.report.trace.append({
            'reference': hit.reference, 'title': hit.title,
            'reason': 'verified_offer',
            'business_relevance': {
                'decision': 'keep', 'business_category': 'P1_HERITAGE',
                'reason_code': 'ACCEPT_HERITAGE_PROFESSIONAL_SERVICE'},
            'resolution_state': 'VERIFIED_OFFICIAL',
        })

    monkeypatch.setattr(MarketsCollector, '_process', fake_process)
    with app.app_context():
        import_baseline([
            listing(),
            listing(consultation_id='2', organization='x', reference='99/2026',
                    title='Travaux de construction de route', buyer='Commune',
                    detail_url='https://www.marchespublics.gov.ma/?refConsultation=2'),
        ])
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 2
        collector = MarketsCollector(Mock(), _config())
        candidates, stats = backfill_from_index(collector, AcceptingRadar())
        assert stats.indexed_considered == 2
        assert stats.skipped_prefilter == 1
        assert stats.sent_to_detail == 1
        assert processed == ['04/2026/AUS']
        assert len(candidates) == 1
        assert stats.reference_notice['kept'] is True
        assert stats.reference_notice['classification'] == 'P1_HERITAGE'
        outcomes = classify_trace_outcomes(collector.report.trace)
        assert len(outcomes['accepted']) == 1
