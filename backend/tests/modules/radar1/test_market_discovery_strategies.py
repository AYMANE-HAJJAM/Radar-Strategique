from unittest.mock import Mock

from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.modules.radar1_markets.discovery_strategies import (
    FAMILY_TERMS, build_discovery_plan, direct_discovery_plan)
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import extract_rows
from backend.app.integrations.pmmp.client import is_direct_notice
from backend.app.db.extensions import db
from backend.app.db.models import Radar, SearchRun
from backend.app.integrations.openai.base import SearchHit, SearchResponse
from backend.tests.modules.radar1.test_collection_diagnostics import LIVE_URL, official_page
from test_phase3 import CODE

RADAR = RADAR_AGENT_REGISTRY.resolve(CODE)


def config(app, **changes):
    values = dict(RADAR1_MAX_QUERIES_PER_RUN=12, RADAR1_DISCOVERY_MAX_CALLS=12,
        RADAR1_MIN_SEARCH_QUERIES=1, RADAR1_TARGET_OBSERVATIONS=4,
        RADAR1_TARGET_UNIQUE_OBSERVATIONS=4, RADAR1_MAX_CANDIDATES=100,
        RADAR1_QUERY_OBSERVATION_LIMIT=20)
    values.update(changes)
    app.config.update(values)
    return app.config


def test_short_queries_cover_manual_snapshot_categories(app):
    plan = build_discovery_plan(config(app))
    assert set(FAMILY_TERMS) == {'architecture', 'competition', 'major_architecture', 'rehabilitation', 'urbanism',
        'territorial_studies', 'project_management', 'built_environment', 'technical_studies'}
    assert {q.strategy for q in plan} == {'PMMP', 'AGGREGATOR', 'INSTITUTIONAL'}
    assert all(' OR ' not in q.text and '(' not in q.text for q in plan)
    architecture = [q for q in plan if q.strategy == 'PMMP' and q.family == 'architecture']
    assert [q.variant for q in architecture] == [0, 1, 2]
    assert architecture[0].text == 'site:marchespublics.gov.ma "etudes architecturales patrimoine"'


def test_direct_plan_establishes_source_diversity_then_expands(app):
    plan = direct_discovery_plan(config(app))
    assert [item.strategy for item in plan[:2]] == ['PMMP', 'AGGREGATOR']
    assert 'keyWord=' in plan[0].url
    assert plan[1].url.endswith('services-architecturales-et-topographiques')


def test_productive_history_reorders_first_ladder_steps(app):
    baseline = build_discovery_plan(config(app))
    history = {'PMMP:rehabilitation': {'executions': 3, 'usable_observations': 15,
        'relevant_candidates': 12, 'official_resolution_success': 10, 'zero_results': 0}}
    learned = build_discovery_plan(config(app), performance=history)
    assert baseline[0].family == 'architecture'
    assert learned[0].family == 'rehabilitation'
    assert {q.family for q in learned} == set(FAMILY_TERMS)


def test_zero_yield_uses_explicit_discovery_budget(app):
    provider, pages = Mock(), Mock()
    provider.search.return_value = SearchResponse([])
    run = MarketsCollector(provider, config(app), pages=pages)
    assert run.collect(RADAR) == []
    assert run.report.metrics['discovery_search_calls'] == 12
    assert run.report.metrics['resolution_search_calls'] == 0
    assert run.report.metrics['queries_with_zero_results'] == 12


def test_target_stops_after_minimum_and_unique_yield(app):
    provider, pages = Mock(), Mock()
    hit = SearchHit(title='Etude architecturale patrimoniale', url=LIVE_URL, reference='CA11/2026/APDN')
    provider.search.side_effect = [SearchResponse([hit]), SearchResponse([]), SearchResponse([])]
    pages.get.return_value = (LIVE_URL, official_page())
    run = MarketsCollector(provider, config(app, RADAR1_MIN_SEARCH_QUERIES=3,
        RADAR1_TARGET_OBSERVATIONS=1, RADAR1_TARGET_UNIQUE_OBSERVATIONS=1), pages=pages)
    assert len(run.collect(RADAR)) == 1
    assert provider.search.call_count == 3


def test_permissive_cross_query_dedup_precedes_enrichment(app):
    provider, pages = Mock(), Mock()
    hit = SearchHit(title='Etude architecturale patrimoniale', url=LIVE_URL, reference='CA11/2026/APDN')
    provider.search.return_value = SearchResponse([hit])
    pages.get.return_value = (LIVE_URL, official_page())
    run = MarketsCollector(provider, config(app, RADAR1_MIN_SEARCH_QUERIES=2,
        RADAR1_TARGET_OBSERVATIONS=50, RADAR1_TARGET_UNIQUE_OBSERVATIONS=50), pages=pages)
    assert len(run.collect(RADAR)) == 1
    assert run.report.metrics['deduped_before_enrichment'] > 0
    assert pages.get.call_count == 1


def test_marche_facile_article_parser_extracts_identity_buyer_and_deadline():
    page = Page('<article><span>05/2026/CA/BR</span><span>Services</span>'
        '<h2><a href="/marches/30589-offer">Etude architecturale patrimoniale et suivi des travaux</a></h2>'
        '<p>REGION DE GUELMIM</p><span>Date limite : <strong>05/10/2026 10:30</strong></span></article>')
    row = extract_rows(page, 'https://marchefacile.ma/appels-offres/secteur/x')[0]
    assert (row.reference, row.institution, row.deadline) == (
        '05/2026/CA/BR', 'REGION DE GUELMIM', '05/10/2026')


def test_bdc_path_is_an_official_direct_notice():
    assert is_direct_notice('https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/12345')


def test_query_performance_memory_aggregates_completed_runs(app):
    with app.app_context():
        radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == CODE))
        previous = SearchRun(radar_id=radar_id, status='completed', run_metadata={'collection_queries': [{
            'source_strategy': 'PMMP', 'query_family': 'architecture', 'raw_results_count': 3,
            'candidates_created': 2, 'relevant_candidates': 1, 'official_resolution_success': 1}]})
        current = SearchRun(radar_id=radar_id, status='running')
        db.session.add_all((previous, current))
        db.session.commit()
        memory = AgentOrchestrator(app)._query_performance(current)['PMMP:architecture']
        assert memory['relevant_candidates'] == 1
        assert memory['official_resolution_success'] == 1
