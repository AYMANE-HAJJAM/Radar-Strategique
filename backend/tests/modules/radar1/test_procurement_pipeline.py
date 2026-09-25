from datetime import timedelta
from unittest.mock import Mock, patch

import pytest

from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import extract_rows, dce_metadata, verify_detail
from backend.app.integrations.http.html import PublicPages
from backend.app.modules.radar1_markets.policy import source_role, relevant, detail_url
from backend.app.modules.radar1_markets.parser import normalize_hit
from backend.app.db.extensions import db
from backend.app.db.models import Result
from backend.app.integrations.openai.base import SearchResponse
from backend.app.core.review import page as review_page
from test_phase3 import hit, URL, CODE, execute

RADAR = RADAR_AGENT_REGISTRY.resolve(CODE)
LIST_URL = 'https://marchesfaciles.ma/services/al-hoceima'


def detail(hit_value=None, form=False):
    item = hit_value or hit()
    return Page(f'<h1>{item.title}</h1><p>{item.reference} {item.institution} {item.deadline}</p>' +
                ('<form>Dossier de consultation DCE 4 Mo identification</form>' if form else
                 '<a href="/docs/DCE.zip">DCE 4 Mo</a>'))


@pytest.mark.parametrize('title', ['Etudes architecturales patrimoniales', 'Etude de restauration du patrimoine historique bâti',
    'Plan amenagement tissu ancien', 'Charte architecturale patrimoniale', 'Etude de rehabilitation architecturale medina',
    'Etudes architecturales et topographiques pour rehabilitation patrimoniale'])
def test_business_accepts(title):
    assert relevant(title)


@pytest.mark.parametrize('title', ['Gardiennage de la medina', 'Nettoyage monument historique',
    'Fournitures de bureau', 'Informatique', 'Restauration collective', 'Acquisition de vehicules',
    'Etude territoriale', 'Charte paysagere', 'AMO amenagement du territoire',
    'Topographie pour lotissement', 'Etudes techniques suivi reseau assainissement',
    'Prestations topographiques par LiDAR', 'Controle topographique', 'Topographic surveys'])
def test_noise_rejected(title):
    assert not relevant(title)


@pytest.mark.parametrize('url', ['https://culture.gov.ma/', 'https://culture.gov.ma/news/patrimoine',
    'https://culture.gov.ma/appels-offres', 'https://culture.gov.ma/search?q=architecture',
    'https://marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'])
def test_generic_urls_rejected(url):
    assert not detail_url(url)


def test_whitelist_and_source_roles(app):
    assert source_role(URL, app.config) == 'OFFICIAL_PROCUREMENT'
    assert source_role(LIST_URL, app.config) == 'PROCUREMENT_AGGREGATOR'
    assert source_role('https://culture.gov.ma/avis/123', app.config) == 'OFFICIAL_INSTITUTIONAL'
    assert source_role('https://random.gov.ma/avis/123', app.config) is None
    assert source_role('https://marchespublics.gov.ma.evil.test/avis', app.config) is None
    app.config['RADAR1_DISCOVERY_DOMAINS'] = ('culture.gov.ma',)
    assert source_role('https://culture.gov.ma/avis/123', app.config) == 'DISCOVERY_ONLY'


def test_al_hoceima_rows_are_resolved_individually(app):
    listing = Page('<h1>10 appels d’offres de services à Al Hoceima</h1><table>'
        '<tr><td>CA11/2026/APDN</td><td>Etude architecturale et suivi des travaux de restauration des remparts</td></tr>'
        '<tr><td>12/2026/APDN</td><td>Gardiennage</td></tr></table>')
    assert len(extract_rows(listing, LIST_URL)) == 2
    official = hit(title='Etude architecturale et suivi des travaux de restauration des remparts', reference='CA11/2026/APDN')
    provider, pages = Mock(), Mock()
    def search(query, **kwargs):
        if 'CA11/2026/APDN' in query:
            return SearchResponse([official])
        if kwargs['domains'] == ('marchesfaciles.ma',):
            return SearchResponse([hit(title='10 appels d’offres de services à Al Hoceima', url=LIST_URL)])
        return SearchResponse([])
    provider.search.side_effect = search
    pages.get.side_effect = lambda url: (url, listing if url == LIST_URL else detail(official))
    app.config['RADAR1_SOURCE_WHITELIST'] = ('marchespublics.gov.ma', 'marchesfaciles.ma', 'culture.gov.ma')
    collector = MarketsCollector(provider, app.config, pages=pages)
    items = collector.collect(RADAR)
    assert len(items) == 1 and items[0].reference == 'CA11/2026/APDN'
    assert items[0].official_url == URL and items[0].detail_verified
    assert items[0].metadata['original_discovery_url'] == LIST_URL
    assert not any('12/2026/APDN' in call.args[0] for call in provider.search.call_args_list)
    assert collector.report.metrics['individual_tenders_extracted'] == 3  # two discoveries plus official confirmation
    assert collector.report.metrics['query_scope_filtered'] == 0
    assert collector.report.metrics['official_urls_resolved'] == 1
    summary = execute(app, items)
    assert summary.new_results_count == 1
    with app.app_context():
        assert db.session.scalar(db.select(Result)).url == URL


@pytest.mark.parametrize('changes', [dict(title='10 appels d’offres de services à Al Hoceima'),
    dict(url='https://culture.gov.ma/news/patrimoine'), dict(url=LIST_URL),
    dict(url='https://marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'),
    dict(deadline=(today_in_morocco()-timedelta(days=1)).isoformat()), dict(status='awarded')])
def test_bad_results_never_enter_queue(app, changes):
    item = normalize_hit(hit(**changes)).model_copy(update={'detail_verified': True})
    execute(app, [item])
    assert not review_page(app, 'pending', 0)[0]


def test_snippet_without_detail_verification_is_rejected(app):
    summary = execute(app, [normalize_hit(hit())])
    assert summary.rejected_count == 1 and summary.analyzed_count == 0
    assert not review_page(app, 'pending', 0)[0]


def test_detail_mismatch_and_old_without_deadline_rejected():
    pages = Mock()
    pages.get.return_value = (URL, Page('Unrelated notice'))
    with pytest.raises(ValueError):
        verify_detail(normalize_hit(hit()), pages)
    item = normalize_hit(hit(publication_date='2024-01-01', deadline=None)).model_copy(update={'detail_verified': True})
    assert not RADAR.validate_candidate(item).accepted


def test_institutional_listing_with_specific_row_is_not_a_detail(app):
    url = 'https://culture.gov.ma/fr/appels-offres'
    assert not detail_url(url)
    pages = Mock()
    pages.get.return_value = ('https://culture.gov.ma/procurement/2026',
                             Page('<h1>Appels d’offres</h1>' + detail().text))
    with pytest.raises(ValueError, match='container'):
        verify_detail(normalize_hit(hit(url='https://culture.gov.ma/procurement/2026')), pages)


def test_configurable_keywords_and_discovery_only_cannot_be_accepted(app):
    assert not relevant('Diagnostic des ponts', {'TERRITORIAL': ['diagnostic des ponts']})
    app.config['RADAR1_DISCOVERY_DOMAINS'] = ('culture.gov.ma',)
    item = normalize_hit(hit(url='https://culture.gov.ma/avis/123')).model_copy(update={'detail_verified': True})
    execute(app, [item])
    assert not review_page(app, 'pending', 0)[0]


def test_dce_direct_and_protected_are_metadata_only():
    direct = dce_metadata(detail(), URL)
    assert direct['dce_available'] and direct['dce_url'].endswith('/docs/DCE.zip')
    assert direct['dce_access_mode'] == 'DIRECT_DOWNLOAD' and direct['dce_size'] == '4 Mo'
    protected = dce_metadata(detail(form=True), URL)
    assert protected['dce_access_mode'] == 'FORM_REQUIRED' and protected['dce_url'] is None
    assert dce_metadata(Page('No documents'), URL)['dce_access_mode'] == 'NOT_FOUND'


def test_public_inspection_only_uses_get_and_never_submits_form():
    response = Mock()
    response.headers.get.side_effect = lambda name, default='': 'text/html' if name == 'Content-Type' else default
    response.headers.get_content_charset.return_value = 'utf-8'
    response.read.return_value = b'<form method="post">DCE identification</form>'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with patch('app.integrations.http.html.build_opener') as opener:
        opener.return_value.open.return_value = response
        _, parsed = PublicPages(('marchespublics.gov.ma',)).get(URL)
        request = opener.return_value.open.call_args.args[0]
        assert request.get_method() == 'GET' and request.data is None
        assert opener.return_value.open.call_count == 1
        assert dce_metadata(parsed, URL)['dce_access_mode'] == 'FORM_REQUIRED'


@pytest.mark.parametrize('rejected', [False, True])
def test_memory_skips_detail_and_ai_before_resolution(app, rejected):
    app.config.update(RADAR1_MIN_DISCOVERIES=1, RADAR1_MAX_QUERIES_PER_RUN=12,
                      RADAR1_MIN_SEARCH_QUERIES=1, RADAR1_TARGET_OBSERVATIONS=1)
    provider, pages = Mock(), Mock()
    provider.search.return_value = SearchResponse([hit()])
    pages.get.return_value = (URL, detail())
    def build(*args):
        return MarketsCollector(provider, app.config, pages=pages)
    with patch('app.core.orchestrator.build_collector', side_effect=build):
        from backend.scripts.test_agent import MockAnalyzer
        engine = AgentOrchestrator(app, analyzer=MockAnalyzer())
        assert engine.run_radar(CODE).new_results_count == 1
        with app.app_context():
            row = db.session.scalar(db.select(Result))
            if rejected:
                row.review_status, row.status = 'REJECTED', 'rejected'
                db.session.commit()
            before = row.updated_at
        pages.reset_mock()
        summary = engine.run_radar(CODE)
        pages.get.assert_not_called()
        assert summary.analyzed_count == 0 and summary.duplicate_count == 1
        with app.app_context():
            row = db.session.scalar(db.select(Result))
            assert row.updated_at == before
            if rejected:
                assert row.review_status == 'REJECTED'
        provider.search.return_value = SearchResponse([hit(deadline=(today_in_morocco()+timedelta(days=40)).isoformat())])
        pages.get.return_value = (URL, detail(provider.search.return_value.hits[0]))
        assert engine.run_radar(CODE).updated_results_count == 1
        assert pages.get.called
