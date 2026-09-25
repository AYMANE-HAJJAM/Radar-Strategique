"""Radar 1 patrimoine-first regressions, including AI and stale queue bypasses."""
from unittest.mock import Mock

import pytest

from backend.app.modules.radar1_markets.policy import evaluate_relevance, folded
from backend.app.modules.radar1_markets.service import MarketsRadarAgent
from backend.app.core.review import _unique_eligible
from backend.scripts.test_agent import MockAnalyzer
from test_agent import candidate
from test_phase3 import execute
from types import SimpleNamespace


REJECTED = [
    'Construction de nouvelles écoles et unités préscolaires',
    'Construction de cimetière', 'Aménagement du centre communal',
    'Démolition et reconstruction du centre de santé',
    'Construction de terrains sportifs', 'Aménagement de voirie et assainissement',
    'Étude topographique par LiDAR', 'Aménagement paysager du jardin public',
    'Construction du nouveau souk', 'Réhabilitation de logements',
    'Traitement du bâti menaçant ruine', 'Valorisation du centre commercial',
    'Restauration collective au monument historique',
    'Construction de route à Ksar Sghir', 'Conservation des eaux et sols',
    'Réhabilitation de la route à Ksar Sghir',
    'Réhabilitation de l’école dans la médina',
    'Restauration du bâtiment ordinaire',
    'Aménagement du bâtiment destiné à abriter un espace de la mémoire historique',
    'Gestion du patrimoine automobile', 'ERP de gestion du patrimoine informatique',
    'Gestion administrative du patrimoine foncier et immobilier',
    'Inventaire physique des biens mobiliers de la société',
    'Valorisation du patrimoine végétal', 'Étude du patrimoine naturel',
    'Assistance topographique et foncière',
]
# Explicit architectural wording on ordinary buildings is NOT an ARCHERITAGE track.
GENERIC_ARCHITECTURE_REJECTED = [
    'Étude architecturale pour construction de gendarmerie',
    'Réhabilitation architecturale du bâtiment administratif',
]
# Médina + architectural study remains heritage-eligible.
HERITAGE_WITH_ARCHITECTURE = [
    'Étude architecturale pour école dans la médina',
]
P1 = [
    'Restauration des remparts', 'Réhabilitation de la médina',
    'Étude pour un monument historique',
    'Conservation et restauration du bâtiment historique',
    'Diagnostic architectural patrimonial', 'Études architecturales patrimoniales',
    'Suivi de travaux de restauration des murailles', 'Restauration des ksour',
    'Conservation du bastion', 'Restauration de la porte historique',
    'Sauvegarde de l’ancienne médina', 'Revitalisation du centre historique',
    'Conservation d’un site archéologique', 'Restauration d’un ancien fondouk',
    'Consolidation d’un bâtiment historique', 'Reconversion d’un édifice ancien',
    'Plan de sauvegarde d’une médina', 'Réhabilitation du tissu ancien',
    'Programme de mise à niveau de l’ancienne ville',
    'Restauration d’une zaouia patrimoniale', 'Conservation d’une synagogue historique',
    'Restauration des façades historiques avec des matériaux traditionnels',
    'Réhabilitation du bâti ancien',
    'Traitement du bâti menaçant ruine dans la médina historique',
    'Réhabilitation d’un bâtiment public historique',
    'Diagnostic structurel d’une structure ancienne',
    # Clear patrimonial professional studies (étude/diagnostic/plan) are P1.
    'Étude de valorisation du patrimoine culturel, naturel et historique de Settat',
    'Étude patrimoniale du territoire',
    'Inventaire du patrimoine culturel et historique',
    'Diagnostic du patrimoine historique',
    'Documentation et interprétation du patrimoine culturel',
    'Plan de conservation du patrimoine historique',
    'Étude du paysage culturel et historique',
    'Étude de gestion du patrimoine culturel',
    'Stratégie de valorisation patrimoniale',
    'Études techniques pour intervention dans le tissu ancien',
]
P2 = [
    'Intervention dans le tissu ancien',
    'Aménagement des espaces publics de la médina',
    'Valorisation du patrimoine culturel', 'Valorisation du patrimoine historique',
    'Développement de circuits patrimoniaux',
    'Valorisation de sites patrimoniaux', 'Cultural heritage development',
    'Mise en valeur d’un circuit historique',
    'Requalification des espaces publics de la médina',
    'Développement touristique des sites historiques',
    'Aménagement d’un centre d’interprétation sur un site patrimonial',
]


# The professional-services policy requires an explicit study/design/supervision role.
P1 = [title if any(term in folded(title) for term in (
    'etude', 'diagnostic', 'suivi', 'plan', 'programme', 'expertise')) else 'Etude de ' + title
    for title in P1]
P2 = ['Etude professionnelle de ' + title if folded(title).startswith('amenagement ') else title
      for title in P2]

@pytest.mark.parametrize('title', REJECTED)
def test_generic_rejected_before_ai(app, title):
    analyzer = Mock()
    assert evaluate_relevance(title)['decision'] == 'reject'
    summary = execute(app, [candidate(title=title)], analyzer)
    assert summary.rejected_count == 1 and summary.new_results_count == 0
    analyzer.analyze_candidate.assert_not_called()


@pytest.mark.parametrize('title', GENERIC_ARCHITECTURE_REJECTED)
def test_ordinary_architectural_studies_rejected_before_ai(app, title):
    from backend.app.modules.radar1_markets.policy import REASON_REJECT_GENERIC
    analyzer = Mock()
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_GENERIC
    summary = execute(app, [candidate(title=title)], analyzer)
    assert summary.rejected_count == 1 and summary.new_results_count == 0
    analyzer.analyze_candidate.assert_not_called()


@pytest.mark.parametrize('title', HERITAGE_WITH_ARCHITECTURE)
def test_architecture_in_medina_remains_heritage_eligible(title):
    result = evaluate_relevance(title)
    assert result['decision'] in {'keep', 'review'}
    assert result['business_category'] in {'P1_HERITAGE', 'P2_REVIEW'}
    assert result['domain_fit'] is True


@pytest.mark.parametrize('title', P1)
def test_direct_heritage_is_p1(title):
    result = evaluate_relevance(title)
    assert (result['decision'], result['priority']) == ('keep', 1)
    assert MarketsRadarAgent().validate_candidate(candidate(title=title)).accepted


@pytest.mark.parametrize('title', P2)
def test_adjacent_never_auto_approved(app, title):
    radar = MarketsRadarAgent()
    item = candidate(title=title)
    result = evaluate_relevance(title)
    assert (result['decision'], result['priority']) == ('review', 2)
    decision = radar.validate_candidate(item)
    assert decision.accepted and decision.needs_manual_review
    analysis = MockAnalyzer().analyze_candidate(item, None, analysis_schema=radar.analysis_schema).analysis
    analysis.confidence = 1.0
    analysis.needs_manual_review = False
    assert radar.validated_analysis(item, analysis).needs_manual_review
    analyzer = Mock()
    summary = execute(app, [item], analyzer)
    assert summary.manual_review_count == 1 and summary.accepted_count == 0
    analyzer.analyze_candidate.assert_not_called()


def test_config_cannot_rescue_generic_architecture():
    assert evaluate_relevance('Construction école', {'HERITAGE_STRONG': ('ecole',)})['decision'] == 'reject'


def test_architectural_competition_is_an_independent_track():
    result = evaluate_relevance('Concours architectural pour équipements publics',
                                procedure_type='competition')
    assert (result['decision'], result['business_category']) == ('keep', 'P1_CONCOURS')


def test_complete_procurement_context_can_establish_heritage_relevance():
    result = evaluate_relevance('Programme de sauvegarde et de mise à niveau',
                                scope='Objet concernant l’ancienne ville de Salé')
    assert (result['decision'], result['priority']) == ('keep', 1)


def test_ksar_in_location_does_not_establish_heritage_context():
    result = evaluate_relevance('Construction d’un équipement public', scope='Ksar Sghir')
    assert result['decision'] == 'reject'


@pytest.mark.parametrize('mode', ['pending', 'approved'])
def test_legacy_generic_records_hidden_without_database_mutation(mode):
    # Ordinary études+suivi without architecture/heritage remain out of Radar 1 queue.
    row = SimpleNamespace(id=1, title='Études et suivi des travaux de construction',
        radar_metadata={'detail_verified': True}, source_status='open',
        deadline=None, publication_date=None, analysis=None)
    assert not list(_unique_eligible([row], mode, 'RADAR_1_MARKETS'))
    assert list(_unique_eligible([row], mode, 'RADAR_2_PROJECTS')) == [row]
