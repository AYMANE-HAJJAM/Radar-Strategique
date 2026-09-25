from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.core.agent_errors import ActiveRunError, InvalidAnalysisError, OpenAITimeoutError
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.agent_schemas import AnalysisResponse, Candidate, Stage, TokenUsage
from backend.app.db.extensions import db
from backend.app.db.models import Result, ResultObservation, SearchRun
from backend.app.core.dedup import canonical_url
from backend.scripts.test_agent import MockAnalyzer
from backend.app.modules.radar1_markets.schemas import MarketCandidate
from backend.app.core.validation import today_in_morocco
from datetime import timedelta

CODE = 'RADAR_1_MARKETS'


def candidate(**changes):
    values = dict(title='Etude architecturale patrimoniale', url='https://example.com/item', source='official-test-source',
                  reference='REF-1', institution='Institution', raw_text='Etude architecturale patrimoniale au Maroc',
                  morocco_related=True, location_evidence='Rabat, Maroc', publication_date=today_in_morocco(),
                  deadline=today_in_morocco()+timedelta(days=30), source_status='open', procedure_type='tender',
                  source_quality='OFFICIAL_PRIMARY', official_confirmation=True, detail_verified=True,
                  official_url='https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=123')
    values.update(changes)
    if 'title' in changes and 'raw_text' not in changes:
        values['raw_text'] = changes['title']
    return MarketCandidate(**values)


def agent(app, items, analyzer=None):
    return AgentOrchestrator(app, collector=lambda radar: items, analyzer=analyzer or MockAnalyzer())


def test_lifecycle_and_same_run_cannot_execute_twice(app):
    engine = agent(app, [])
    summary = engine.run_radar(CODE, triggered_by=123)
    assert summary.status == 'completed' and summary.ai_calls == 0
    with app.app_context():
        row = db.session.get(SearchRun, summary.id)
        assert [entry['stage'] for entry in row.stage_history] == [stage.value for stage in Stage if stage != Stage.FAILED]
        assert row.triggered_by == 123 and row.finished_at is not None
    with pytest.raises(ActiveRunError):
        engine.execute(summary.id)


def test_rediscovery_skips_ai_and_preserves_content_timestamp(app):
    analyzer = Mock(wraps=MockAnalyzer())
    engine = agent(app, [candidate()], analyzer)
    first = engine.run_radar(CODE)
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        original_id, original_updated, original_seen = row.id, row.updated_at, row.first_seen_at
    second = engine.run_radar(CODE)
    assert first.new_results_count == 1
    assert second.duplicate_count == 1 and second.ai_calls == 0
    assert analyzer.analyze_candidate.call_count == 1
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.id == original_id and row.updated_at == original_updated and row.first_seen_at == original_seen
        assert row.status == 'unchanged' and row.last_seen_at >= original_updated
        observations = db.session.scalars(db.select(ResultObservation).order_by(ResultObservation.id)).all()
        assert [item.state for item in observations] == ['new', 'unchanged']


def test_meaningful_update_keeps_identity_and_versions(app):
    original = candidate(deadline=date(2026, 10, 1))
    first = agent(app, [original]).run_radar(CODE)
    updated = original.model_copy(update={'title': 'Programme architectural patrimonial modifié', 'deadline': date(2026, 11, 1),
                                          'metadata': {'budget': 200}, 'source_status': 'open'})
    second = agent(app, [updated]).run_radar(CODE)
    assert second.updated_results_count == 1 and second.new_results_count == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 1
        row = db.session.scalar(db.select(Result))
        assert row.deadline == date(2026, 11, 1) and row.status == 'updated'
        observations = db.session.scalars(db.select(ResultObservation).order_by(ResultObservation.id)).all()
        assert observations[0].snapshot['deadline'] == '2026-10-01'
        assert observations[1].snapshot['deadline'] == '2026-11-01'


def test_ai_rejected_plausible_candidate_is_review_memory_and_not_reanalyzed(app):
    response = MockAnalyzer().analyze_candidate(candidate(), None)
    response.analysis.relevant = False
    analyzer = Mock()
    analyzer.analyze_candidate.return_value = response
    engine = agent(app, [candidate()], analyzer)
    assert engine.run_radar(CODE).manual_review_count == 1
    assert engine.run_radar(CODE).duplicate_count == 1
    assert analyzer.analyze_candidate.call_count == 1
    with app.app_context():
        assert db.session.scalar(db.select(Result)).status == 'manual_review'


def test_url_and_reference_dedup_before_ai(app):
    item = candidate()
    same_url = item.model_copy(update={'url': 'https://EXAMPLE.com:443/item/?utm_source=x#section'})
    same_ref = item.model_copy(update={'url': 'https://elsewhere.example/item'})
    summary = agent(app, [item, same_url, same_ref]).run_radar(CODE)
    assert summary.duplicate_count == 2 and summary.analyzed_count == 1 and summary.new_results_count == 1
    assert canonical_url('https://EXAMPLE.com:443/Path/?id=1&utm_source=x') == 'https://example.com/Path?id=1'
    assert canonical_url('https://example.com/A') != canonical_url('https://example.com/a')
    assert canonical_url('http://example.com') != canonical_url('https://example.com')


def test_one_invalid_candidate_does_not_stop_valid_candidate(app):
    analyzer = Mock()
    analyzer.analyze_candidate.side_effect = [InvalidAnalysisError('bad', attempts=1),
        MockAnalyzer().analyze_candidate(candidate(), None)]
    second = candidate().model_copy(update={'title': 'Different historic building restoration program', 'url': 'https://example.com/second', 'reference': 'REF-2'})
    summary = agent(app, [{'title': ''}, candidate(), second], analyzer).run_radar(CODE)
    assert summary.status == 'completed' and summary.new_results_count == 1
    assert summary.candidate_errors_count == 2 and summary.rejected_count == 2


def test_untrusted_analyzer_output_is_validated_before_save(app):
    from types import SimpleNamespace
    analyzer = Mock()
    analyzer.analyze_candidate.return_value = SimpleNamespace(
        analysis={'relevant': 'yes'}, usage=TokenUsage(input_tokens=100), model='test', attempts=1)
    summary = agent(app, [candidate()], analyzer).run_radar(CODE)
    assert summary.candidate_errors_count == 1 and summary.input_tokens == 100
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 0


def test_collector_timeout_and_database_failures_have_distinct_kinds(app):
    engine = agent(app, [])
    engine.collector = Mock(side_effect=RuntimeError('secret document'))
    summary = engine.run_radar(CODE)
    assert summary.error_kind == 'collector' and 'secret' not in summary.error_message
    analyzer = Mock()
    analyzer.analyze_candidate.side_effect = OpenAITimeoutError('timeout', attempts=3)
    summary = agent(app, [candidate()], analyzer).run_radar(CODE)
    assert summary.status == 'completed' and summary.manual_review_count == 1 and summary.ai_calls == 3
    engine = agent(app, [candidate()])
    with patch.object(engine.results, 'save', side_effect=OperationalError('secret', {}, None)):
        summary = engine.run_radar(CODE)
    assert summary.error_kind == 'database' and summary.new_results_count == 0


def test_active_run_protected_by_service_and_database(app):
    engine = agent(app, [])
    run_id = engine.reserve(CODE)
    with pytest.raises(ActiveRunError):
        engine.reserve(CODE)
    with app.app_context():
        original = db.session.get(SearchRun, run_id)
        db.session.add(SearchRun(radar_id=original.radar_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
    other = engine.run_radar('RADAR_2_PROJECTS')
    assert other.status == 'completed'
    engine.execute(run_id)
    assert engine.run_radar(CODE).status == 'completed'


def test_cost_aggregation_and_unknown_model(app):
    app.config.update(OPENAI_MODEL='test', OPENAI_INPUT_PRICE_PER_MILLION='1',
                      OPENAI_CACHED_PRICE_PER_MILLION='0.1', OPENAI_OUTPUT_PRICE_PER_MILLION='2')
    response = MockAnalyzer().analyze_candidate(candidate(), None)
    response.model = 'test'
    response.usage = TokenUsage(input_tokens=1000, cached_tokens=200, output_tokens=100)
    analyzer = Mock()
    analyzer.analyze_candidate.return_value = response
    second = candidate().model_copy(update={'title': 'Second historic building restoration program', 'url': 'https://example.com/b', 'reference': 'b'})
    summary = agent(app, [candidate(), second], analyzer).run_radar(CODE)
    assert (summary.input_tokens, summary.output_tokens, summary.cached_tokens) == (2000, 200, 400)
    assert summary.estimated_ai_cost == Decimal('0.00204000')
    assert summary.ai_calls == 2
