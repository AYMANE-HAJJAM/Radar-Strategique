import pytest

from backend.app.core.business_relevance import evaluate_business_relevance


@pytest.mark.parametrize('text', [
    'Programme de réhabilitation de la médina',
    'Étude de valorisation du patrimoine culturel',
    'Projet de régénération du centre historique',
    'Programme de restauration et conservation des monuments',
    'Conservation du site archéologique',
    'Convention de développement territorial',
    'Programme régional de développement',
    'Étude de stratégie territoriale',
    'Programme de régénération urbaine',
    'Réforme de la gouvernance territoriale',
    'Donor-funded regional development program',
    'برنامج تنمية ترابية وتأهيل المدينة العتيقة',
])
def test_archeritage_and_innova_scope(text):
    assert evaluate_business_relevance(text)['decision'] != 'reject'


@pytest.mark.parametrize('text', [
    'Tournoi national de football', 'Discours politique sans projet concret',
    'Déploiement d’un logiciel de paie', 'Revêtement ordinaire de la route provinciale',
    'Nouveau produit bancaire pour consommateurs', 'Programme scolaire de mathématiques',
])
def test_unrelated_content_rejected(text):
    assert evaluate_business_relevance(text)['decision'] == 'reject'
