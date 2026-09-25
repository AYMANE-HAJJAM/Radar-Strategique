"""Radar 1 role+domain relevance regressions (études+suivi alone is not enough)."""
import pytest
from backend.app.modules.radar1_markets.policy import (
    evaluate_relevance, REASON_ACCEPT_HERITAGE, REASON_REJECT_EXECUTION,
    REASON_REJECT_INFRA, REASON_ACCEPT_CONCOURS, REASON_ACCEPT_MAJOR,
)


@pytest.mark.parametrize('title', [
    'REALISATION DES ETUDES ET SUIVI DES TRAVAUX DE REHABILITATION DE L’ANCIENNE MEDINA DE LA VILLE DE GUELMIM',
    'Études et suivi des travaux de réhabilitation de l’ancienne médina',
    'Études et suivi des travaux de restauration des remparts',
    'Étude restauration monument historique',
    'Maîtrise d’œuvre restauration patrimoine bâti',
])
def test_heritage_professional_services_remain_eligible(title):
    result = evaluate_relevance(title)
    assert result['decision'] in {'keep', 'review'}
    assert result['domain_fit'] is True
    assert result['reason_code'] in {REASON_ACCEPT_HERITAGE, 'REVIEW_AMBIGUOUS_RELEVANCE'}


@pytest.mark.parametrize('title,code', [
    ('Études et suivi des travaux de réhabilitation de voirie et assainissement dans plusieurs rues',
     REASON_REJECT_INFRA),
    ('Études et suivi des travaux de voirie', REASON_REJECT_INFRA),
    ('Études et suivi des travaux d’assainissement', REASON_REJECT_INFRA),
    ('Études techniques de réseaux d’eau potable', REASON_REJECT_INFRA),
    ('Études et suivi des travaux de réhabilitation de la chaussée', REASON_REJECT_INFRA),
])
def test_ordinary_infrastructure_studies_are_rejected(title, code):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == code
    assert result['role_fit'] is True
    assert result['domain_fit'] is False


@pytest.mark.parametrize('title', [
    'Travaux de restauration d’un monument historique',
    'Travaux de réhabilitation des remparts',
    'Restauration et sauvegarde du ksar historique',
])
def test_pure_heritage_works_remain_rejected(title):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_EXECUTION


def test_architectural_competition_and_major_services():
    concours = evaluate_relevance('Concours de conception architecturale pour un grand musée')
    assert concours['business_category'] == 'P1_CONCOURS'
    assert concours['reason_code'] == REASON_ACCEPT_CONCOURS
    major = evaluate_relevance('Études architecturales d’un grand centre culturel structurant')
    assert major['decision'] in {'keep', 'review'}
    assert major['reason_code'] in {REASON_ACCEPT_MAJOR, 'REVIEW_AMBIGUOUS_RELEVANCE', REASON_ACCEPT_HERITAGE}


def test_professional_role_without_domain_rejects():
    result = evaluate_relevance('Études et suivi des travaux')
    assert result['decision'] == 'reject'
    assert result['reason_code'] in {REASON_REJECT_INFRA, 'REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT'}
