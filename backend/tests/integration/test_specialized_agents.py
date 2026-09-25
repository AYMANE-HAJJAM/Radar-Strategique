import ast
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from backend.app.core.agent_errors import InvalidCandidateError
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY, RadarAgentRegistry, UnknownRadarError
from backend.app.modules.radar1_markets.service import MarketsRadarAgent
from backend.app.modules.radar2_projects.service import ProjectsRadarAgent
from backend.app.modules.radar3_institutions.service import InstitutionsRadarAgent
from backend.app.modules.radar4_policies.service import PoliciesRadarAgent
from backend.app.modules.radar5_funding.service import FundingRadarAgent
from backend.app.core.agent_schemas import AnalysisResponse, TokenUsage
from backend.app.db.extensions import db
from backend.app.db.models import Result, ResultObservation, SearchRun
from backend.app.integrations.openai.client import OpenAIService
from backend.scripts.test_agent import MockAnalyzer

TODAY = date(2026, 9, 9)
AGENTS = (MarketsRadarAgent, ProjectsRadarAgent, InstitutionsRadarAgent, PoliciesRadarAgent, FundingRadarAgent)


def analysis(agent, **changes):
    payload = dict(relevant=True, priority=3, score=85, category='other', summary='Résumé.',
                   reason='Source fournie.', confidence=0.9, needs_manual_review=False)
    payload.update(changes)
    return agent.analysis_schema(**payload)


@pytest.mark.parametrize('agent_type', AGENTS)
def test_registry_and_empty_run_identity(app, agent_type):
    resolved = RADAR_AGENT_REGISTRY.resolve(agent_type.code)
    assert type(resolved) is agent_type
    assert resolved.get_code() == agent_type.code
    assert resolved.get_source_strategy().collection_enabled
    assert resolved.collect() == []
    assert resolved.get_validation_rules()
    assert resolved.analysis_schema.__name__ in resolved.get_analysis_prompt()
    result = AgentOrchestrator(app).run_radar(agent_type.code)
    assert result.agent_name == agent_type.__name__ and result.status == 'completed'
    assert result.ai_calls == 0
    with app.app_context():
        assert db.session.get(SearchRun, result.id).agent_name == agent_type.__name__


def test_registry_unknown_duplicate_and_rules():
    assert len(RADAR_AGENT_REGISTRY.catalog()) == 5
    with pytest.raises(UnknownRadarError):
        RADAR_AGENT_REGISTRY.resolve('UNKNOWN')
    with pytest.raises(ValueError):
        RadarAgentRegistry([MarketsRadarAgent, MarketsRadarAgent])
    assert MarketsRadarAgent().get_relevance_rules() != ProjectsRadarAgent().get_relevance_rules()
    assert 'PMMP' in MarketsRadarAgent().get_source_strategy().preferred_sources


def test_unknown_run_creates_no_database_record(app):
    with pytest.raises(UnknownRadarError):
        AgentOrchestrator(app).run_radar('UNKNOWN')
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(SearchRun)) == 0


def test_market_deadline_and_commercial_priority():
    agent = MarketsRadarAgent()
    from backend.tests.integration.test_agent import candidate as fixture_candidate
    candidate = fixture_candidate(title='Étude et suivi de restauration du patrimoine historique bâti', deadline=TODAY, publication_date=TODAY, procedure_type='consultation')
    assert agent.validate_candidate(candidate, as_of=TODAY).accepted
    result = agent.validated_analysis(candidate, analysis(agent, commercial_fit='direct'), as_of=TODAY)
    assert result.priority == 1 and result.deadline_status == 'active'
    expired = candidate.model_copy(update={'deadline': TODAY - timedelta(days=1)})
    assert not agent.validate_candidate(expired, as_of=TODAY).accepted
    foreign = candidate.model_copy(update={'morocco_related': False})
    assert not agent.validate_candidate(foreign, as_of=TODAY).accepted


@pytest.mark.parametrize('evidence,expected', [({'financing_secured': True}, 'A'),
                                            ({'officially_announced': True}, 'B'), ({'signal_type': 'study'}, 'C')])
def test_project_maturity_is_evidence_based(evidence, expected):
    agent = ProjectsRadarAgent()
    candidate = agent.normalize_candidate({'title': 'Future heritage rehabilitation project', **evidence})
    assert agent.validated_analysis(candidate, analysis(agent, maturity='A')).maturity == expected
    assert not agent.validate_candidate(candidate.model_copy(update={'published_tender': True})).accepted
    assert not agent.validate_candidate(candidate.model_copy(update={'project_completed': True})).accepted
    assert agent.validate_candidate(candidate.model_copy(update={'project_completed': True, 'new_phase_confirmed': True})).accepted


def test_institutions_cannot_self_verify_or_use_stale_role():
    agent = InstitutionsRadarAgent()
    candidate = agent.normalize_candidate({'title': 'Director of heritage agency', 'person': 'Example',
        'position': 'Director', 'mission': 'Heritage conservation',
        'institution_relevant': True, 'nomination_unconfirmed': True})
    result = agent.validated_analysis(candidate, analysis(agent, current_position_verified=True), as_of=TODAY)
    assert not result.relevant and not result.current_position_verified
    verified = candidate.model_copy(update={'role_verified': True, 'role_verified_at': TODAY,
                                            'official_source': 'https://example.com/organization'})
    assert agent.validated_analysis(verified, analysis(agent), as_of=TODAY).current_position_verified
    stale = verified.model_copy(update={'role_verified_at': TODAY - timedelta(days=181)})
    assert not agent.validate_candidate(stale, as_of=TODAY).accepted
    future = verified.model_copy(update={'role_verified_at': TODAY + timedelta(days=1)})
    assert not agent.validate_candidate(future, as_of=TODAY).accepted


def test_policy_claims_require_consistent_reliable_status():
    agent = PoliciesRadarAgent()
    draft = agent.normalize_candidate({'title': 'Draft urban heritage law', 'document_type': 'draft_law', 'reported_status': 'preparation',
                                       'reliable_status_evidence': True, 'official_source': 'https://example.com/draft',
                                       'status_evidence': 'Officially in preparation.'})
    result = agent.validated_analysis(draft, analysis(agent))
    assert result.policy_status == 'C' and result.legal_status == 'UNDER_PREPARATION'
    with pytest.raises(InvalidCandidateError):
        agent.validated_analysis(draft, analysis(agent, legal_status='ADOPTED'))
    assert not agent.validate_candidate(draft.model_copy(update={'reported_status': 'adopted'})).accepted
    unsupported = agent.normalize_candidate({'title': 'Law', 'document_type': 'law', 'reported_status': 'in_force'})
    assert not agent.validate_candidate(unsupported).accepted
    law = draft.model_copy(update={'document_type': 'law', 'reported_status': 'in_force', 'publication_verified':True,
        'status_source_url':'https://sgg.gov.ma/BO/2026/BO_7000_Fr.pdf', 'effective_date':date(2026,1,1)})
    assert agent.validated_analysis(law, analysis(agent)).policy_status == 'A'


@pytest.mark.parametrize('status,expected', [('open', 'A'), ('active', 'B'), ('preparation', 'C'),
                                          ('pipeline', 'D'), ('closed', 'E'), ('unknown', 'D')])
def test_funding_status_and_access(status, expected):
    agent = FundingRadarAgent()
    candidate = agent.normalize_candidate({'title': 'Heritage urban development program', 'morocco_related': True,
                                           'reported_funding_status': status, 'access_mode_evidence': 'direct_application', 'strategically_relevant': True})
    result = agent.validated_analysis(candidate, analysis(agent, access_mode='DIRECT_ACCESS'))
    assert result.funding_status == expected and result.access_mode == 'MONITORING_ONLY' and result.needs_manual_review
    eligible = candidate.model_copy(update={'eligibility': 'Consulting SMEs eligible', 'direct_eligibility_confirmed': True,
                                            'official_source': 'https://example.com/eligibility'})
    assert agent.validated_analysis(eligible, analysis(agent)).access_mode == 'DIRECT_ACCESS'
    assert not agent.validate_candidate(candidate.model_copy(update={'morocco_related': False})).accepted


def test_rejection_precedes_ai_and_extensions_are_persistent(app):
    analyzer = Mock(wraps=MockAnalyzer())
    items = [{'title': 'Foreign grant', 'url': 'https://example.com/foreign', 'morocco_related': False, 'funder': 'Example donor'}]
    engine = AgentOrchestrator(app, collector=lambda radar: items, analyzer=analyzer)
    summary = engine.run_radar(FundingRadarAgent.code)
    assert summary.rejected_count == 1 and summary.ai_calls == 0
    analyzer.analyze_candidate.assert_not_called()
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.status == 'rejected'
        assert row.source_metadata['radar_fields']['funder'] == 'Example donor'
        assert row.analysis['funding_status'] == 'D'
    assert engine.run_radar(FundingRadarAgent.code).duplicate_count == 1


def test_specialized_field_change_updates_same_row(app):
    items = [{'title': 'Heritage rehabilitation program', 'url': 'https://example.com/project', 'program_approved': True,
              'source': 'Official', 'source_quality': 'OFFICIAL_PRIMARY', 'morocco_related': True,
              'publication_date': TODAY.isoformat(), 'signal_evidence': 'Official program approval'}]
    engine = AgentOrchestrator(app, collector=lambda radar: items, analyzer=MockAnalyzer())
    assert engine.run_radar(ProjectsRadarAgent.code).new_results_count == 1
    items[0]['program_approved'] = False
    items[0]['officially_announced'] = True
    assert engine.run_radar(ProjectsRadarAgent.code).updated_results_count == 1
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.analysis['maturity'] == 'B'
        observations = db.session.scalars(db.select(ResultObservation).order_by(ResultObservation.id)).all()
        assert [obs.snapshot['analysis']['maturity'] for obs in observations] == ['A', 'B']


def test_expired_after_rediscovery_revalidates_without_ai(app):
    from backend.tests.integration.test_agent import candidate
    items = [candidate(deadline=TODAY, publication_date=TODAY).model_dump()]
    engine = AgentOrchestrator(app, collector=lambda radar: items, analyzer=MockAnalyzer())
    with patch('app.core.orchestrator.today_in_morocco', return_value=TODAY):
        assert engine.run_radar(MarketsRadarAgent.code).new_results_count == 1
    with patch('app.core.orchestrator.today_in_morocco', return_value=TODAY + timedelta(days=1)):
        summary = engine.run_radar(MarketsRadarAgent.code)
    assert summary.rejected_count == 1 and summary.ai_calls == 0


@pytest.mark.parametrize('agent_type', AGENTS)
def test_sdk_receives_specialized_prompt_and_schema(agent_type):
    agent = agent_type()
    candidate = agent.normalize_candidate({'title': 'Example'})
    service = OpenAIService('offline-test-key')
    with patch.object(service, '_request', return_value=(analysis(agent), TokenUsage(), 'mock', 1)) as request:
        response = agent.analyze_candidate(candidate, service)
    assert request.call_args.args[2] is agent.analysis_schema
    assert agent.prompt not in request.call_args.args[1]
    assert len(request.call_args.args[1]) < 500
    assert type(response.analysis) is agent.analysis_schema
    assert response.model_dump()['analysis'].keys() == agent.analysis_schema.model_fields.keys()


def test_orchestrator_has_no_radar_business_branching():
    source = Path('app/core/orchestrator.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert not any(isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(('RADAR_1_', 'RADAR_2_', 'RADAR_3_', 'RADAR_4_', 'RADAR_5_'))
                   for node in ast.walk(tree))
    assert 'RADAR_AGENT_REGISTRY.resolve(radar_code)' in source


def test_evidence_url_and_cross_radar_fields_are_validated():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        InstitutionsRadarAgent().normalize_candidate({'title': 'Example', 'official_source': 'javascript:bad'})
    with pytest.raises(ValidationError):
        ProjectsRadarAgent().normalize_candidate({'title': 'Example', 'reported_funding_status': 'open'})
