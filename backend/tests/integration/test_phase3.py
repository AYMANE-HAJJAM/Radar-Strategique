from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.app.core.conditions import ConfidenceRules
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.validation import today_in_morocco
from backend.app.core.collector_base import ProviderUnavailable
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.integrations.pmmp.client import is_direct_notice
from backend.app.modules.radar1_markets.parser import normalize_hit
from backend.app.core.collector_registry import COLLECTORS, build_collector
from backend.app.db.extensions import db
from backend.app.db.models import Result, SearchRun
from backend.app.integrations.openai.base import SearchHit, SearchOutput, SearchProviderError, SearchResponse
from backend.app.integrations.openai.search import OpenAISearchProvider
from backend.scripts.test_agent import MockAnalyzer
from backend.tests.integration.test_agent import candidate

CODE = 'RADAR_1_MARKETS'
URL = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=123'


def hit(**changes):
    payload = dict(title='Étude et suivi de restauration du patrimoine historique bâti', url=URL, evidence='Avis de consultation pour étude et suivi de restauration du patrimoine historique bâti à Rabat, Maroc.',
                   institution='Buyer', reference='REF-1', publication_date=today_in_morocco().isoformat(),
                   deadline=(today_in_morocco()+timedelta(days=14)).isoformat(), execution_country='MA', location='Rabat, Maroc',
                   status='open', procedure_type='consultation', official_notice=True)
    payload.update(changes)
    return SearchHit(**payload)


def execute(app, candidates, analyzer=None, dry_run=False):
    return AgentOrchestrator(app, collector=lambda _: candidates, analyzer=analyzer or MockAnalyzer(), dry_run=dry_run).run_radar(CODE)


@pytest.mark.parametrize('changes,reason', [({'morocco_related': False}, 'outside_morocco'),
                                         ({'deadline': today_in_morocco()-timedelta(days=1)}, 'expired_opportunity'),
                                         ({'source_status': 'closed'}, 'excluded:source_status')])
def test_market_hard_rejection_before_ai(app, changes, reason):
    analyzer = Mock()
    summary = execute(app, [candidate(**changes)], analyzer)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.rejected_count == 1
    assert reason.upper().replace(':', '_') in summary.run_metadata['rule_reasons']


def test_current_official_moroccan_notice_can_be_accepted(app):
    item = normalize_hit(hit()).model_copy(update={'detail_verified': True})
    summary = execute(app, [item])
    assert summary.new_results_count == 1 and summary.accepted_count == 1 and summary.candidates_after_rules == 1
    with app.app_context():
        result = db.session.scalar(db.select(Result))
        assert result.radar_metadata['access_mode'] == 'DIRECT_OFFICIAL'
        assert result.radar_metadata['source_quality'] == 'OFFICIAL_PRIMARY'


def test_generic_architecture_is_not_p1():
    radar = RADAR_AGENT_REGISTRY.resolve(CODE)
    item = candidate(title='Études architecturales', raw_text='Construction de bâtiment administratif.')
    analysis = MockAnalyzer().analyze_candidate(item, None, analysis_schema=radar.analysis_schema).analysis
    analysis.commercial_fit, analysis.priority = 'direct', 1
    # Ordinary études architecturales without heritage/competition/major stay rejected.
    assert not radar.validated_analysis(item, analysis).relevant
    heritage = item.model_copy(update={
        'title': 'Étude de valorisation du patrimoine historique',
        'raw_text': 'Étude de valorisation du patrimoine historique au Maroc',
    })
    result = radar.validated_analysis(heritage, analysis)
    assert result.relevant and result.priority == 1


@pytest.mark.parametrize('changes', [dict(morocco_related=None), 
                                   dict(source_quality='DISCOVERY_ONLY'), dict(source_conflict=True),
                                   dict(reference_conflict=True), dict(source_status='unknown'), dict(institution=None)])
def test_uncertainty_goes_to_review_without_ai(app, changes):
    analyzer = Mock()
    summary = execute(app, [candidate(**changes)], analyzer)
    assert summary.manual_review_count == 1 and summary.accepted_count == 0
    analyzer.analyze_candidate.assert_not_called()
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.status == 'manual_review' and row.radar_metadata['review_reason']


def test_source_provenance_and_generic_pmmp_url():
    generic = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'
    assert not is_direct_notice(generic)
    item = normalize_hit(hit(url=generic))
    assert item.url is None and item.access_mode == 'INDIRECT_PMMP_SEARCH' and not item.official_confirmation
    secondary = normalize_hit(hit(url='https://news.example.com/article'))
    assert secondary.source_quality == 'DISCOVERY_ONLY' and not secondary.official_confirmation
    spoof = normalize_hit(hit(url='https://marchespublics.gov.ma.evil.example/notice'))
    assert spoof.source_quality == 'DISCOVERY_ONLY'
    institutional = normalize_hit(hit(url='https://culture.gov.ma/appels-offres/notice'))
    assert institutional.source_quality == 'OFFICIAL_SECONDARY'


@pytest.mark.parametrize('confidence,expected', [(0.9, 'new'), (0.7, 'manual_review'), (0.5, 'manual_review')])
def test_confidence_policy(app, confidence, expected):
    response = MockAnalyzer().analyze_candidate(candidate(), None)
    response.analysis.confidence = confidence
    analyzer = Mock()
    analyzer.analyze_candidate.return_value = response
    execute(app, [candidate(reference=None)], analyzer)
    with app.app_context():
        assert db.session.scalar(db.select(Result)).status == expected


def test_new_confidence_policy_invalidates_cached_decision(app):
    engine = AgentOrchestrator(app, collector=lambda _: [candidate(reference=None)], analyzer=MockAnalyzer())
    assert engine.run_radar(CODE).new_results_count == 1
    app.config['RADAR_CONFIDENCE'][CODE] = {'auto_accept': 0.95, 'manual_review': 0.55}
    summary = engine.run_radar(CODE)
    assert summary.analyzed_count == 1 and summary.manual_review_count == 1


def test_explicit_review_rule_preserved_despite_low_confidence(app):
    response = MockAnalyzer().analyze_candidate(candidate(), None)
    response.analysis.confidence = 0.4
    analyzer = Mock()
    analyzer.analyze_candidate.return_value = response
    summary = execute(app, [candidate(deadline=None)], analyzer)
    assert summary.manual_review_count == 1 and summary.rejected_count == 0


def test_query_limit_failure_isolation_and_candidate_limit(app):
    app.config.update(RADAR1_MAX_QUERIES_PER_RUN=3, RADAR1_MAX_CANDIDATES=2)
    provider = Mock()
    provider.search.side_effect = [SearchProviderError('temporary'), SearchResponse([hit(), hit(reference='REF-2'), hit(reference='REF-3')]), SearchResponse([])]
    from backend.app.integrations.http.html import Page
    pages = Mock()
    pages.get.return_value = (URL, Page('Restauration du patrimoine Buyer REF-1 REF-2 ' + hit().deadline))
    collector = MarketsCollector(provider, app.config, pages=pages)
    items = collector.collect(RADAR_AGENT_REGISTRY.resolve(CODE))
    assert len(items) == 1 and len(collector.report.query_errors) == 1
    assert collector.report.queries_executed <= 3 and 'candidate_limit' in collector.report.truncated


def test_provider_unavailable_fails_run_and_records_queries(app):
    app.config['RADAR1_DIRECT_DISCOVERY_ENABLED'] = False
    provider = Mock()
    provider.search.side_effect = SearchProviderError('network')
    collector = MarketsCollector(provider, app.config)
    with patch('app.core.orchestrator.build_collector', return_value=collector):
        summary = AgentOrchestrator(app).run_radar(CODE)
    assert summary.status == 'failed' and summary.error_kind == 'search_provider_unavailable'
    assert summary.queries_executed == 3 and len(summary.run_metadata['query_errors']) == 3


def test_analysis_limit_and_transient_candidate_isolation(app):
    from backend.app.core.agent_errors import OpenAITimeoutError
    app.config['RADAR1_MAX_AI_ANALYSES'] = 1
    analyzer = Mock()
    analyzer.analyze_candidate.side_effect = OpenAITimeoutError('timeout', attempts=3)
    second = candidate(title='Different historic building restoration notice', url='https://example.com/second', reference='REF2')
    summary = execute(app, [candidate(), second], analyzer)
    assert summary.status == 'completed' and summary.manual_review_count == 2
    assert analyzer.analyze_candidate.call_count == 1 and 'analysis_limit' in summary.run_metadata['truncation']


def test_dry_run_no_classification_no_result_writes(app):
    analyzer = Mock()
    summary = execute(app, [candidate()], analyzer, dry_run=True)
    assert summary.status == 'completed' and summary.analyzed_count == 0
    analyzer.analyze_candidate.assert_not_called()
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(SearchRun)) == 1


def test_all_five_executable_configs_have_live_collectors(app):
    assert set(COLLECTORS) == {CODE, 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING'}
    for code, radar in RADAR_AGENT_REGISTRY.catalog().items():
        conditions = radar.conditions
        assert conditions.source_rules and conditions.mandatory_fields and conditions.freshness_days > 0
        assert isinstance(conditions.confidence_rules, ConfidenceRules)
        if code != CODE:
            assert build_collector(code, app.config) is None and radar.collect() == []


def test_provider_uses_tool_sources_and_drops_invented_urls():
    response = SimpleNamespace(status='completed', usage=None,
        output=[SimpleNamespace(type='web_search_call', action=SimpleNamespace(sources=[SimpleNamespace(url=URL)]))],
        output_parsed=SearchOutput(hits=[hit(), hit(url='https://invented.example/notice')]))
    with patch('app.integrations.openai.search.OpenAI') as sdk:
        sdk.return_value.__enter__.return_value.responses.parse.return_value = response
        report = OpenAISearchProvider('offline-key', 'test-model').search('heritage', recency_days=7, domains=['marchespublics.gov.ma'])
        request = sdk.return_value.__enter__.return_value.responses.parse.call_args.kwargs
    assert len(report.hits) == 1
    assert request['store'] is False and request['tools'][0]['type'] == 'web_search'
    assert request['tools'][0]['filters']['allowed_domains'] == ['marchespublics.gov.ma']
    assert request['text_format'] is SearchOutput
    assert 'previous_response_id' not in request
