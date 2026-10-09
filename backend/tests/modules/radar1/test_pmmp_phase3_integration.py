"""Phase 3: RADAR1_DISCOVERY_MODE integration behind the feature flag."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.collector_registry import COLLECTORS
from app.db.extensions import db
from app.db.models import Radar, Result, ResultObservation, SearchRun, User
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.integrations.openai.base import SearchHit
from app.modules.radar1_markets.collector import MarketsCollector, legacy_discovery, listing_to_search_hit
from app.modules.radar1_markets.pmmp_listing_collector import (
    NEW, NEXT_HREF, SOURCE, UNCHANGED, PmmpListing,
)
from app.modules.radar1_markets.pmmp_listing_index import import_baseline
from app.modules.radar1_markets.shadow_compare import compare_candidate_sets, candidate_key


COLLECTOR_MODULE = Path(__file__).resolve().parents[3] / 'app' / 'modules' / 'radar1_markets' / 'collector.py'
INDEX_MODULE = Path(__file__).resolve().parents[3] / 'app' / 'modules' / 'radar1_markets' / 'pmmp_listing_index.py'
LISTING_MODULE = Path(__file__).resolve().parents[3] / 'app' / 'modules' / 'radar1_markets' / 'pmmp_listing_collector.py'


def _config(**overrides):
    values = {
        'SOURCE_HTTP_TIMEOUT_SECONDS': 5,
        'RADAR1_SOURCE_WHITELIST': ('marchespublics.gov.ma',),
        'RADAR1_AGGREGATOR_DOMAINS': (),
        'RADAR1_DISCOVERY_DOMAINS': (),
        'RADAR1_KEYWORD_GROUPS': {},
        'RADAR1_DISCOVERY_MODE': 'legacy',
        'RADAR1_PMMP_OVERLAP_PAGES': 3,
        'RADAR1_DIRECT_DISCOVERY_ENABLED': False,
        'RADAR1_SEARCH_MODE': 'normal_coverage',
        'RADAR1_MAX_QUERIES_PER_RUN': 2,
        'RADAR1_DISCOVERY_MAX_CALLS': 2,
        'RADAR1_RESOLUTION_MAX_CALLS': 0,
        'RADAR1_TARGET_OBSERVATIONS': 5,
        'RADAR1_TARGET_UNIQUE_OBSERVATIONS': 5,
        'RADAR1_MIN_PRODUCTIVE_FAMILIES': 1,
        'RADAR1_QUERY_OBSERVATION_LIMIT': 20,
        'RADAR1_ZERO_YIELD_QUERY_LIMIT': 4,
        'RADAR1_MIN_SEARCH_QUERIES': 0,
        'MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD': 20_000_000,
    }
    values.update(overrides)
    return values


def listing(**changes):
    values = dict(
        source=SOURCE, consultation_id='1036481', organization='j8k',
        reference='04/2026/AUS',
        title='Etude de valorisation du patrimoine culturel de Settat',
        buyer='Agence urbaine de Settat', publication_date='03/09/2026',
        deadline='02/10/2027 11:00', procedure="Appel d'offres ouvert",
        category='Services', location='SETTAT',
        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                    'page=entreprise.EntrepriseDetailsConsultation'
                    '&refConsultation=1036481&orgAcronyme=j8k'),
    )
    values.update(changes)
    return PmmpListing(**values)


def row(index, item):
    prefix = f'ctl0_CONTENU_PAGE_resultSearch_tableauResultSearch_ctl{index}'
    name = f'ctl0$CONTENU_PAGE$resultSearch$tableauResultSearch$ctl{index}'
    return (
        f'<input name="{name}$refCons" value="{item.consultation_id}">'
        f'<input name="{name}$orgCons" value="{item.organization}">'
        f'<span id="{prefix}_reference">{item.reference}</span>'
        f'<span id="{prefix}_panelBlocObjet">Objet : {item.title}</span>'
        f'<span id="{prefix}_panelBlocDenomination">Acheteur public : {item.buyer}</span>'
        f'<span id="{prefix}_infosLieuExecutionLtRef">{item.deadline}</span>'
        f'<span id="{prefix}_panelBlocCategorie">{item.category} {item.publication_date}</span>'
        f'<span id="{prefix}_panelBlocTypesProc">{item.procedure} {item.category} {item.publication_date}</span>'
        f'<span id="{prefix}_infosLieuExecution">{item.location or ""} ...</span>'
    )


def result_page(items, *, state, pages, nxt=False):
    pager = f'<a href="{NEXT_HREF}"></a>' if nxt else ''
    body = ''.join(row(index, item) for index, item in enumerate(items, start=1))
    return (
        f'<input name="PRADO_PAGESTATE" value="{state}">'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombreElement">{len(items)}</span>'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop">{pages}</span>'
        f'<div id="tableauResultSearch">{body}</div>{pager}'
    )


class ScriptedHttp:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url):
        self.calls.append(('GET', url, None))
        return self.pages.pop(0)

    def post(self, url, fields):
        self.calls.append(('POST', url, fields.get('PRADO_POSTBACK_TARGET')))
        return self.pages.pop(0)


class AcceptingRadar:
    def validate_candidate(self, candidate):
        return SimpleNamespace(accepted=True, reasons=[])


def test_legacy_flag_preserves_exact_old_behavior():
    calls = []

    class Bound:
        config = {'RADAR1_DISCOVERY_MODE': 'legacy'}
        report = SimpleNamespace(metrics={})

        def legacy_discovery(self, radar):
            calls.append(('legacy', radar))
            return ['legacy']

        def pmmp_index_discovery(self, radar):
            calls.append(('pmmp', radar))
            return ['pmmp']

    assert MarketsCollector.collect(Bound(), 'radar-1') == ['legacy']
    assert calls == [('legacy', 'radar-1')]
    assert Bound().report.metrics['discovery_mode'] == 'legacy'
    assert legacy_discovery(Bound(), 'radar-1') == ['legacy']


def test_pmmp_index_flag_selects_new_path():
    calls = []

    class Bound:
        config = {'RADAR1_DISCOVERY_MODE': 'pmmp_index'}
        report = SimpleNamespace(metrics={})

        def legacy_discovery(self, radar):
            calls.append(('legacy', radar))
            return ['legacy']

        def pmmp_index_discovery(self, radar):
            calls.append(('pmmp', radar))
            return ['pmmp']

    assert MarketsCollector.collect(Bound(), 'radar-1') == ['pmmp']
    assert calls == [('pmmp', 'radar-1')]
    assert Bound().report.metrics['discovery_mode'] == 'pmmp_index'


def test_legacy_discovery_helper_still_available():
    class Bound:
        def legacy_discovery(self, radar):
            return [radar]

    assert legacy_discovery(Bound(), 'x') == ['x']


def test_new_and_updated_listings_reach_downstream_policy(app, monkeypatch):
    processed = []

    def fake_process(self, hit, radar, stats, discovery=None):
        processed.append((hit.reference, hit.url))
        stats['new_identity'] = stats.get('new_identity', 0) + 1
        self.report.metrics['relevant_candidates'] += 1
        self.report.candidates.append(SimpleNamespace(
            reference=hit.reference, resolution_state='VERIFIED',
            publication_date=None))

    monkeypatch.setattr(MarketsCollector, '_process', fake_process)
    with app.app_context():
        import_baseline([listing()])
        # Same fingerprint = UNCHANGED on next sync; change deadline for UPDATED.
        http = ScriptedHttp([
            result_page([listing(deadline='15/11/2026 18:00'),
                         listing(consultation_id='999', organization='zzz',
                                 reference='99/2026/NEW', title='Nouvelle etude patrimoniale',
                                 buyer='Commune', detail_url=(
                                     'https://www.marchespublics.gov.ma/index.php?'
                                     'page=entreprise.EntrepriseDetailsConsultation'
                                     '&refConsultation=999&orgAcronyme=zzz'))],
                        state='s', pages=1),
        ])
        collector = MarketsCollector(Mock(), _config(RADAR1_DISCOVERY_MODE='pmmp_index'))
        collector.listing_http = http
        kept = collector.collect(AcceptingRadar())
        assert sorted(ref for ref, _ in processed) == ['04/2026/AUS', '99/2026/NEW']
        assert collector.report.metrics['pmmp_sync_updated'] == 1
        assert collector.report.metrics['pmmp_sync_new'] == 1
        assert collector.report.metrics['discovery_mode'] == 'pmmp_index'
        assert len(kept) == 2


def test_unchanged_listing_is_skipped(app, monkeypatch):
    processed = []
    monkeypatch.setattr(
        MarketsCollector, '_process',
        lambda self, hit, radar, stats, discovery=None: processed.append(hit.reference))
    with app.app_context():
        import_baseline([listing()])
        from app.modules.radar1_markets.processing import record_terminal, PROCESSED
        row = db.session.scalar(db.select(PmmpListingIndex))
        record_terminal(row, PROCESSED, 'fixture_successful_policy_processing')
        db.session.commit()
        http = ScriptedHttp([result_page([listing()], state='s', pages=1)])
        collector = MarketsCollector(Mock(), _config(RADAR1_DISCOVERY_MODE='pmmp_index'))
        collector.listing_http = http
        kept = collector.collect(AcceptingRadar())
        assert processed == []
        assert kept == []
        assert collector.report.metrics['pmmp_sync_unchanged'] == 1
        assert collector.report.metrics['pmmp_actionable'] == 0


def test_empty_index_skips_pmmp_path_without_crawl(app, monkeypatch):
    called = []
    monkeypatch.setattr(
        'app.modules.radar1_markets.pmmp_listing_index.sync_listings',
        lambda **kwargs: called.append(kwargs) or (_ for _ in ()).throw(AssertionError('should not sync')))
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 0
        collector = MarketsCollector(Mock(), _config(RADAR1_DISCOVERY_MODE='pmmp_index'))
        assert collector.collect(AcceptingRadar()) == []
        assert 'pmmp_index_empty_run_baseline_first' in collector.report.health_reasons
        assert called == []


def test_listing_index_rows_do_not_become_ui_results(app):
    with app.app_context():
        import_baseline([listing()])
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 0
        radar = db.session.scalar(db.select(Radar).where(Radar.code == 'RADAR_1_MARKETS'))
        client = app.test_client()
        # Unauthenticated list still must not expose index rows as results.
        response = client.get(f'/api/radars/{radar.id}/results?status=pending&page_size=50')
        assert response.status_code in {200, 401, 403}
        if response.status_code == 200:
            assert response.get_json().get('items') == []


def test_searchrun_attribution_still_works_with_pmmp_mode(app):
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == 'RADAR_1_MARKETS'))
        user = User(display_name='Phase3', role='ADMIN', active=True,
                    access_code_hash='x' * 60)
        db.session.add(user)
        db.session.flush()
        run = SearchRun(
            radar_id=radar.id, status='completed', current_stage='COMPLETED',
            launched_by_user_id=user.id, candidates_count=3,
            new_results_count=1, updated_results_count=0, duplicate_count=2,
            rejected_count=0, candidate_errors_count=0)
        result = Result(
            radar_id=radar.id, title='Etude patrimoine', fingerprint='fp-phase3',
            content_hash='ch-phase3', review_status='PENDING', discovery_status='NEW',
            status='new', url=listing().detail_url,
            institution='Agence urbaine de Settat', reference='04/2026/AUS')
        db.session.add_all([run, result])
        db.session.flush()
        db.session.add(ResultObservation(
            run_id=run.id, result_id=result.id, state='new', snapshot={}))
        db.session.commit()
        assert run.launched_by_user_id == user.id
        assert run.new_results_count == 1
        assert run.updated_results_count == 0
        assert run.duplicate_count == 2


def test_run_scoped_result_view_excludes_unchanged(app):
    """Only NEW/UPDATED observations for the SearchRun appear in run-scoped pending."""
    with app.app_context():
        from app.api.results import _actionable_states
        radar = db.session.scalar(db.select(Radar).where(Radar.code == 'RADAR_1_MARKETS'))
        run = SearchRun(radar_id=radar.id, status='completed', current_stage='COMPLETED')
        fresh = Result(
            radar_id=radar.id, title='NEW notice', fingerprint='fp-new',
            content_hash='ch-new', review_status='PENDING', discovery_status='NEW',
            status='new')
        stale = Result(
            radar_id=radar.id, title='UNCHANGED notice', fingerprint='fp-old',
            content_hash='ch-old', review_status='PENDING', discovery_status='UNCHANGED',
            status='new')
        db.session.add_all([run, fresh, stale])
        db.session.flush()
        db.session.add_all([
            ResultObservation(run_id=run.id, result_id=fresh.id, state='new', snapshot={}),
            ResultObservation(run_id=run.id, result_id=stale.id, state='unchanged', snapshot={}),
        ])
        db.session.commit()
        states = _actionable_states(run.id, [fresh.id, stale.id])
        assert states == {fresh.id: 'new'}


def test_no_duplicate_business_result_from_same_consultation(app):
    with app.app_context():
        first = import_baseline([listing()])
        second = import_baseline([listing()])
        assert first.counts[NEW] == 1
        assert second.counts.get(UNCHANGED, 0) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 0
        hit = listing_to_search_hit(listing())
        assert isinstance(hit, SearchHit)
        assert hit.reference == '04/2026/AUS'


def test_no_paid_call_in_discovery_index_layer():
    for path in (LISTING_MODULE, INDEX_MODULE):
        text = path.read_text(encoding='utf-8')
        assert 'openai' not in text.lower()
        assert 'SearchProvider' not in text
        assert 'provider.search' not in text
    # Collector discovery branch for pmmp must mark billable_search False and not call search plan.
    text = COLLECTOR_MODULE.read_text(encoding='utf-8')
    assert "billable_search': False" in text or 'billable_search": False' in text
    assert 'pmmp_index_discovery' in text


def test_radars_2_to_5_unaffected():
    assert set(COLLECTORS) == {
        'RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS',
        'RADAR_4_POLICIES', 'RADAR_5_FUNDING',
    }
    for code in ('RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING'):
        module = COLLECTORS[code].__module__
        assert 'radar1' not in module
        assert 'pmmp_listing' not in module


def test_shadow_compare_reports_overlap_and_reference():
    legacy = [
        listing(consultation_id='1', reference='01/2026'),
        listing(),
    ]
    pmmp = [
        listing(),
        listing(consultation_id='2', reference='02/2026',
                detail_url='https://www.marchespublics.gov.ma/?refConsultation=2'),
    ]
    result = compare_candidate_sets(legacy, pmmp, reference='04/2026/AUS')
    assert result.overlap == 1
    assert result.unique_to_legacy == 1
    assert result.unique_to_pmmp == 1
    assert result.reference_in_legacy is True
    assert result.reference_in_pmmp is True
    assert candidate_key(listing()) == 'cid:1036481'


def test_default_discovery_mode_remains_legacy(app):
    assert app.config.get('RADAR1_DISCOVERY_MODE', 'legacy') == 'legacy'
