import json
from pathlib import Path

import pytest

from backend.app.modules.radar1_markets.policy import evaluate_relevance, folded
from backend.app.modules.radar1_markets.service import MarketsRadarAgent
from backend.scripts.test_agent import MockAnalyzer
from test_agent import candidate
from test_phase3 import execute
from backend.app.db.extensions import db
from backend.app.db.models import Result

EXAMPLES = json.loads(Path('tests/fixtures/manual_market_relevance.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('example', EXAMPLES, ids=[str(i) for i in range(len(EXAMPLES))])
def test_manual_examples_survive_ai_veto_and_keep_priority(example):
    item = candidate(title=example['title'])
    business = evaluate_relevance(item.title)
    architectural_corniche = 'etudes architecturales' in folded(example['title']) and 'corniche' in folded(example['title'])
    consultation = 'consultation architecturale' in folded(example['title'])
    execution_only = folded(example['title']).startswith(('travaux de', 'restauration d un monument'))
    if business['decision'] == 'reject' or execution_only:
        assert business['decision'] == 'reject'
        assert not MarketsRadarAgent().validate_candidate(item).accepted
        return
    assert business['score'] >= 2
    expected_priority = example['priority']
    if architectural_corniche or business.get('business_category') == 'P2_REVIEW':
        expected_priority = 2
    if business.get('business_category') == 'P1_CONCOURS' or consultation:
        expected_priority = 1
    assert business['priority'] == expected_priority
    radar = MarketsRadarAgent()
    analysis = MockAnalyzer().analyze_candidate(item, None, analysis_schema=radar.analysis_schema).analysis
    analysis.relevant, analysis.confidence = False, 0.1
    result = radar.validated_analysis(item, analysis)
    assert result.relevant and result.needs_manual_review
    assert result.priority == expected_priority
    assert radar.candidate_review_analysis(item, ('analysis_unavailable',)).priority == expected_priority
    assert not radar.validated_analysis(item.model_copy(update={'source_status': 'closed'}), analysis).relevant
    assert not radar.validated_analysis(item.model_copy(update={'official_confirmation': False}), analysis).relevant


@pytest.mark.parametrize('title', ['Gardiennage de la médina', 'Nettoyage monument historique',
    'Restauration collective dans un bâtiment public', 'Fournitures informatiques',
    'Consommables de laboratoire', 'Achat de véhicules', 'Mobilier standard',
    'Maintenance informatique', 'Fournitures médicales', 'Sécurité privée',
    'Achat de matériel médico-technique', 'Achat de médicaments'])
def test_obvious_noise_rejected(title):
    assert evaluate_relevance(title)['decision'] == 'reject'


@pytest.mark.parametrize('example', [EXAMPLES[2], EXAMPLES[10]])
def test_all_priorities_enter_pending_workflow(app, example):
    summary = execute(app, [candidate(title=example['title'])])
    assert summary.new_results_count == 1
    with app.app_context():
        result = db.session.scalar(db.select(Result))
        assert int(result.priority) == example['priority']
        assert result.review_status == 'PENDING'


def test_neutral_purpose_is_rejected_and_repeated_keywords_do_not_inflate_score():
    radar = MarketsRadarAgent()
    item = candidate(title='Mission à préciser')
    analysis = MockAnalyzer().analyze_candidate(item, None, analysis_schema=radar.analysis_schema).analysis
    assert not radar.validated_analysis(item, analysis).relevant
    assert evaluate_relevance('Architecture architecturale architectural')['decision'] == 'reject'


@pytest.mark.parametrize('title', [
    'Etudes techniques et suivi de construction au port de Ksar Sghir',
    'Organisation de la participation au salon international du batiment et de urbanisme',
    'Etude de conservation des eaux et des sols et collecte des eaux pluviales',
])
def test_geographic_or_generic_terms_do_not_fake_architecture_scope(title):
    assert evaluate_relevance(title)['decision'] == 'reject'


def test_explicit_ksar_restoration_requires_professional_service_role():
    assert evaluate_relevance('Restauration et sauvegarde du ksar historique')['decision'] == 'reject'
    assert evaluate_relevance('Etude de restauration et sauvegarde du ksar historique')['decision'] == 'keep'
