from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.agent_schemas import TokenUsage
from backend.app.core.collector_base import query_batches
from backend.app.db.extensions import db
from backend.app.db.models import Result
from backend.app.core.evidence import compact_candidate, relevant_snippets
from backend.app.integrations.openai.client import OpenAIService
from backend.scripts.test_agent import MockAnalyzer
from backend.tests.integration.test_agent import candidate


def test_context_selects_relevant_sections_and_obeys_limits():
    text = 'Navigation ' * 200 + '. Convention signée avec budget pour réhabilitation du patrimoine. ' + 'Footer ' * 200
    snippets = relevant_snippets(text, max_chars=120, snippet_chars=100, max_items=2)
    assert len(snippets) <= 2 and sum(map(len, snippets)) <= 120
    assert 'Convention' in ' '.join(snippets)
    item = candidate(raw_text=text, metadata={'content': 'urbanisme ' * 500})
    payload = compact_candidate(item, max_chars=120, snippet_chars=100, max_items=2)
    assert len(payload) < len(item.model_dump_json()) / 2
    assert 'Footer Footer Footer Footer Footer' not in payload


def test_runtime_prompts_are_compact():
    for agent in RADAR_AGENT_REGISTRY.catalog().values():
        prompt = agent.get_analysis_prompt()
        assert len(prompt) < 500
        assert 'Required output JSON schema' not in prompt


def test_search_themes_are_batched_without_dropping_a_theme():
    queries = ['one', 'two', 'three', 'four', 'five', 'six']
    batches = list(query_batches(queries, 3))
    assert len(batches) == 2
    assert [theme for _, themes in batches for theme in themes] == queries


def test_openai_candidate_input_and_output_are_bounded():
    item = candidate(raw_text='irrelevant ' * 1500 + ' convention patrimoine budget')
    client = MagicMock()
    client.responses.parse.return_value = SimpleNamespace(status='completed', model='test',
        output_parsed=MockAnalyzer().analyze_candidate(item, None).analysis,
        usage=SimpleNamespace(input_tokens=50, output_tokens=10,
            input_tokens_details=SimpleNamespace(cached_tokens=0)))
    with patch('app.integrations.openai.client.OpenAI') as sdk:
        sdk.return_value.__enter__.return_value = client
        OpenAIService('key', max_source_chars=200, max_snippet_chars=100,
                      max_evidence_items=2, max_output_tokens=300).analyze_candidate(
            item, RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS').get_analysis_context())
    sent = client.responses.parse.call_args.kwargs
    assert len(sent['input']) < 4000
    assert sent['max_output_tokens'] == 300


def test_no_ai_mode_and_explicit_signal_use_zero_ai(app):
    code = 'RADAR_2_PROJECTS'
    agent = RADAR_AGENT_REGISTRY.resolve(code)
    explicit = agent.normalize_candidate({'title': 'Convention signee pour rehabilitation de la medina',
        'signal_type': 'convention',
        'signal_evidence': 'Convention signee pour rehabilitation de la medina'})
    analyzer = Mock()
    summary = AgentOrchestrator(app, collector=lambda _: [explicit], analyzer=analyzer, no_ai=True).run_radar(code)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.ai_calls == 0 and summary.new_results_count == 1
    assert summary.run_metadata['no_ai'] is True


def test_cached_evidence_skips_ai_but_changed_evidence_invalidates(app):
    app.config['RADAR1_AI_ENABLED'] = 'conditional'
    analyzer = Mock(wraps=MockAnalyzer())
    first = AgentOrchestrator(app, collector=lambda _: [candidate()], analyzer=analyzer).run_radar('RADAR_1_MARKETS')
    assert first.new_results_count == 1
    analyzer.reset_mock()
    cached = AgentOrchestrator(app, collector=lambda _: [candidate()], analyzer=analyzer).run_radar('RADAR_1_MARKETS')
    analyzer.analyze_candidate.assert_not_called()
    assert cached.run_metadata['ai_skipped_reasons']['ALREADY_CACHED'] == 1
    changed = candidate().model_copy(update={'title': 'Changed architectural patrimonial project'})
    AgentOrchestrator(app, collector=lambda _: [changed], analyzer=analyzer).run_radar('RADAR_1_MARKETS')
    analyzer.analyze_candidate.assert_called_once()


def test_token_budget_degrades_to_review_without_extra_call(app):
    app.config['RADAR1_MAX_INPUT_TOKENS_PER_RUN'] = 1
    with app.app_context():
        radar = db.session.scalar(db.select(__import__('app.db.models', fromlist=['Radar']).Radar))
    analyzer = Mock()
    engine = AgentOrchestrator(app, collector=lambda _: [candidate()], analyzer=analyzer)
    original = engine.reserve('RADAR_1_MARKETS')
    with app.app_context():
        from backend.app.db.models import SearchRun
        run = db.session.get(SearchRun, original); run.input_tokens = 1; db.session.commit()
    summary = engine.execute(original)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.manual_review_count == 1
