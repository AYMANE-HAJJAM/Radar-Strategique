import json
from pathlib import Path

import pytest

from backend.app.bot.presenters.result_presenter import format_result_card
from backend.app.modules.radar1_markets.discovery_strategies import FAMILY_TERMS, build_discovery_plan
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import procurement_metadata
from backend.app.modules.radar1_markets.policy import evaluate_relevance
from backend.app.core.review import page as review_page
from test_agent import candidate
from test_phase3 import execute, URL


THRESHOLD = 20_000_000


@pytest.mark.parametrize('title', [
    'Études architecturales pour un grand musée régional',
    'Conception architecturale d’un grand centre culturel structurant',
    'Études architecturales et suivi du nouveau siège régional',
    'Conception architecturale d’un complexe hospitalier majeur',
    'Études architecturales du nouveau campus universitaire',
    'Conception architecturale d’un projet urbain de redéveloppement majeur',
    'Conception architecturale d’un grand équipement public',
])
def test_strong_major_architecture_without_budget_is_p1(title):
    result = evaluate_relevance(title, threshold_mad=THRESHOLD)
    assert (result['decision'], result['business_category']) == ('keep', 'P1_MAJOR_ARCH')


@pytest.mark.parametrize('title', [
    'Construction de six unités préscolaires',
    'Construction d’un petit centre communal',
    'Maintenance d’un bâtiment administratif',
    'Extension simple d’une école primaire',
    'Démolition reconstruction du centre de santé',
    'Construction de logements ordinaires',
])
def test_ordinary_construction_stays_rejected(title):
    assert evaluate_relevance(title)['decision'] == 'reject'


def test_verified_budget_supports_major_architecture_but_not_infrastructure():
    major = evaluate_relevance('Études architecturales et suivi d’un siège administratif',
        estimated_amount=25_000_000, amount_verified=True, threshold_mad=THRESHOLD)
    assert major['business_category'] == 'P1_MAJOR_ARCH'
    below = evaluate_relevance('Études architecturales et suivi d’un siège administratif',
        estimated_amount=10_000_000, amount_verified=True, threshold_mad=THRESHOLD)
    assert (below['decision'], below['business_category']) == ('review', 'P2_REVIEW')
    road = evaluate_relevance('Études et construction d’une route structurante',
        estimated_amount=200_000_000, amount_verified=True, threshold_mad=THRESHOLD)
    assert road['decision'] == 'reject'


def test_secondary_estimate_cannot_alone_promote_major_project():
    result = evaluate_relevance('Études architecturales d’un siège administratif',
        estimated_amount=100_000_000, amount_verified=False, threshold_mad=THRESHOLD)
    assert (result['decision'], result['business_category']) == ('review', 'P2_REVIEW')


def test_architectural_competition_and_documents_are_first_class(app):
    title = 'Concours architectural pour la conception d’un nouveau musée'
    item = candidate(title=title, procedure_type='competition',
                     business_category='P1_CONCOURS')
    execute(app, [item])
    card = review_page(app, 'pending', 0)[0][0]
    text = format_result_card(card, 1, 'pending')
    assert '🏆 Concours architectural' in text
    assert 'Règlement / DCE' in text
    facts = procurement_metadata(Page(
        '<p>Prime du concours : 500 000 MAD</p>'
        '<p>Conditions d’éligibilité : architectes inscrits à l’ordre</p>'
        '<a href="/reglement.pdf">Règlement du concours</a>'), URL)
    assert facts['competition_prize_amount'] == 500_000
    assert facts['competition_regulation_available']
    assert 'REGLEMENT' in facts['document_types']
    assert facts['eligibility_conditions'] == 'architectes inscrits à l’ordre'


def test_non_architectural_contest_is_rejected():
    assert evaluate_relevance('Concours national de photographie',
                              procedure_type='competition')['decision'] == 'reject'


def test_discovery_has_controlled_competition_and_major_families(app):
    plan = build_discovery_plan(app.config)
    assert FAMILY_TERMS['competition'] == (
        'concours architectural', 'concours de conception architecturale')
    assert any(row.family == 'competition' for row in plan)
    assert any(row.family == 'major_architecture' for row in plan)
    assert app.config['RADAR1_NORMAL_SEARCH_BUDGET'] == 2


def test_saved_generic_snapshot_replay_is_selective():
    rows = json.loads(Path('tests/fixtures/manual_market_relevance.json').read_text(encoding='utf-8'))
    decisions = [evaluate_relevance(row['title']) for row in rows]
    assert sum(row['business_category'] == 'P1_HERITAGE' for row in decisions) == 0
    assert sum(row['business_category'] == 'P1_CONCOURS' for row in decisions) == 2
    # Only plausible major/heritage-adjacent cases stay P2 — not ordinary écoles/logements.
    assert sum(row['business_category'] == 'P2_REVIEW' for row in decisions) == 4
    assert sum(row['business_category'] == 'REJECT' for row in decisions) == 6
