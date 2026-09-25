import pytest
from types import SimpleNamespace
from backend.app.modules.radar1_markets.policy import evaluate_relevance
from backend.app.core.review import _unique_eligible

@pytest.mark.parametrize('title', [
    'Étude de valorisation du patrimoine culturel et historique de Settat',
    'Diagnostic architectural d’un monument historique',
    'Maîtrise d’œuvre pour la restauration d’une kasbah',
    'Suivi des travaux de restauration d’un monument historique',
    'Étude architecturale et suivi des travaux d’aménagement de la corniche',
    'Études de conservation des remparts de la médina',
])
def test_heritage_professional_services_are_eligible(title):
    result = evaluate_relevance(title)
    assert result['decision'] in {'keep', 'review'}
    assert result['business_category'] in {'P1_HERITAGE', 'P2_REVIEW'}

@pytest.mark.parametrize('title', [
    'Travaux de restauration d’une mosquée historique',
    'Travaux de réhabilitation des remparts',
    'Construction d’un centre culturel',
    'Travaux d’aménagement de la corniche',
    'Restauration et sauvegarde du ksar historique',
    'Appel d’offres pour la restauration d’un monument historique',
])
def test_execution_only_opportunities_are_rejected(title):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['rejection_reason'] == 'pure_execution_works'

def test_high_budget_cannot_rescue_pure_construction():
    result = evaluate_relevance('Travaux de construction d’un complexe hospitalier structurant', estimated_amount=500_000_000, amount_verified=True)
    assert result['decision'] == 'reject'
    assert result['rejection_reason'] == 'pure_execution_works'

@pytest.mark.parametrize('title', [
    'Études architecturales d’un grand centre culturel structurant',
    'Conception et suivi des travaux d’un nouveau siège national',
    'Maîtrise d’œuvre d’un nouveau campus universitaire structurant',
    'Architectural study for a large hospital complex',
])
def test_major_architecture_services_are_eligible(title):
    assert evaluate_relevance(title)['decision'] in {'keep', 'review'}

def test_architectural_competition_kept_and_other_contest_rejected():
    assert evaluate_relevance('Concours de conception architecturale pour un grand musée')['business_category'] == 'P1_CONCOURS'
    assert evaluate_relevance('Concours national de photographie')['decision'] == 'reject'

def test_pmmp_travaux_category_is_warning_but_service_language_rescues():
    rejected = evaluate_relevance('Restauration des remparts historiques', procedure_type='Travaux')
    accepted = evaluate_relevance('Études et suivi des travaux de restauration des remparts', procedure_type='Travaux')
    assert rejected['rejection_reason'] == 'pure_execution_works'
    assert accepted['decision'] in {'keep', 'review'}

@pytest.mark.parametrize('mode', ['pending', 'approved'])
def test_legacy_pure_works_are_hidden_without_deleting_rows(mode):
    row = SimpleNamespace(id=91, title='Travaux de restauration des remparts historiques',
        radar_metadata={'detail_verified': True, 'official_confirmation': True, 'current_evidence': True},
        source_status='open', deadline=None, publication_date=None, analysis=None)
    assert list(_unique_eligible([row], mode, 'RADAR_1_MARKETS')) == []
