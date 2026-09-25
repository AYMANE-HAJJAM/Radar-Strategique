"""ARCHERITAGE scope restore: heritage / concours / major only; reject generic architecture."""
from types import SimpleNamespace
from datetime import timedelta

import pytest

from backend.app.integrations.pmmp.parser import enrich_detail
from backend.app.modules.radar1_markets.policy import (
    evaluate_relevance, preliminary_plausible,
    REASON_ACCEPT_CONCOURS, REASON_ACCEPT_HERITAGE, REASON_ACCEPT_MAJOR,
    REASON_REJECT_EXECUTION, REASON_REJECT_GENERIC, REASON_REJECT_INFRA,
    REASON_REJECT_NO_DOMAIN,
)
from backend.app.modules.radar1_markets.schemas import MarketCandidate
from backend.app.core.validation import today_in_morocco


def test_ancienne_medina_etudes_suivi_is_p1_heritage():
    result = evaluate_relevance(
        "Études et suivi des travaux de réhabilitation de l’ancienne médina")
    assert result['decision'] == 'keep'
    assert result['business_category'] == 'P1_HERITAGE'
    assert result['reason_code'] == REASON_ACCEPT_HERITAGE


def test_patrimoine_culturel_study_is_p1_heritage():
    result = evaluate_relevance('Étude de valorisation du patrimoine culturel')
    assert result['decision'] == 'keep'
    assert result['business_category'] == 'P1_HERITAGE'
    assert result['reason_code'] == REASON_ACCEPT_HERITAGE


def test_sidi_ifni_architectural_competition_is_p1_concours():
    result = evaluate_relevance(
        "Concours architectural pour l’aménagement de la corniche de Sidi Ifni")
    assert result['business_category'] == 'P1_CONCOURS'
    assert result['reason_code'] == REASON_ACCEPT_CONCOURS


def test_major_architectural_project_above_verified_threshold():
    result = evaluate_relevance(
        'Études architecturales pour un grand musée régional',
        estimated_amount=25_000_000, amount_verified=True)
    assert result['business_category'] == 'P1_MAJOR_ARCH'
    assert result['reason_code'] == REASON_ACCEPT_MAJOR


@pytest.mark.parametrize('title', [
    "Études architecturales et suivi des travaux de construction d’un lycée ordinaire",
    'Études architecturales et suivi des travaux de construction du lycée',
    "Étude architecturale d’un logement de fonction",
    "Étude architecturale pour reconstruction d’un logement de fonction",
    "Études architecturales pour une école ordinaire",
    "Étude architecturale d’un petit bâtiment administratif",
    'Études architecturales et suivi des travaux',
    "Conception architecturale et suivi des travaux de construction des logements",
])
def test_ordinary_architectural_studies_rejected_as_generic(title):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_GENERIC
    assert result['role_fit'] is True
    assert result['domain_fit'] is False


@pytest.mark.parametrize('title', [
    'Études et suivi des travaux de voirie',
    "Études et suivi des travaux d’assainissement",
    'Études techniques de réhabilitation des rues',
    'Études assainissement et réseaux',
])
def test_ordinary_infrastructure_rejected(title):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_INFRA


def test_pure_restoration_works_rejected():
    result = evaluate_relevance("Travaux de restauration d’un monument")
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_EXECUTION


def test_heritage_urban_streets_not_rejected_for_voirie_alone():
    result = evaluate_relevance(
        "Études et suivi de réhabilitation des espaces et voies de l’ancienne médina")
    assert result['decision'] in {'keep', 'review'}
    assert result['reason_code'] in {REASON_ACCEPT_HERITAGE, 'REVIEW_AMBIGUOUS_RELEVANCE'}
    assert result['reason_code'] != REASON_REJECT_INFRA


def test_moe_monument_is_heritage():
    result = evaluate_relevance(
        "Maîtrise d’œuvre pour restauration d’un monument historique")
    assert result['decision'] == 'keep'
    assert result['business_category'] == 'P1_HERITAGE'


def test_corniche_without_competition_uses_major_track_not_generic_accept():
    """Corniche is a major asset → P2 major review; not a dump of all études architecturales."""
    result = evaluate_relevance(
        "Études architecturales et suivi des travaux d’aménagement de la corniche")
    assert result['decision'] == 'review'
    assert result['business_category'] == 'P2_REVIEW'
    assert result['business_tracks'] == ['MAJOR_ARCH']
    assert result['reason_code'] != REASON_REJECT_GENERIC


def test_corniche_with_competition_is_concours():
    result = evaluate_relevance(
        "Études architecturales et suivi des travaux d’aménagement de la corniche",
        procedure_type='competition')
    assert result['business_category'] == 'P1_CONCOURS'
    assert result['reason_code'] == REASON_ACCEPT_CONCOURS


class _FakePages:
    def __init__(self, url, text, links=None):
        self.url = url
        self.text = text
        self.links = links or []
        self.texts = [line.strip() for line in text.splitlines() if line.strip()]
        self.has_form = False

    def get(self, url):
        page = SimpleNamespace(
            text=self.text, links=self.links, texts=self.texts, has_form=self.has_form)
        return self.url, page


def test_detail_enrichment_can_upgrade_listing_to_competition():
    """Architectural wording may reach detail; final accept needs competition/heritage/major."""
    today = today_in_morocco()
    url = (
        'https://www.marchespublics.gov.ma/index.php?'
        'page=entreprise.EntrepriseDetailsConsultation&refConsultation=999&orgAcronyme=x1'
    )
    listing_title = 'Élaboration des études et suivi des travaux de construction'
    assert preliminary_plausible(listing_title)['decision'] == 'continue'
    listing = evaluate_relevance(listing_title)
    assert listing['decision'] == 'reject'
    assert listing['reason_code'] in {REASON_REJECT_NO_DOMAIN, REASON_REJECT_GENERIC,
                                      'REJECT_NO_ARCHITECTURAL_ROLE'}

    page_text = """
    Référence: 99/2026/TEST
    Objet: Élaboration des études et suivi des travaux de construction
    Procédure: Concours Architectural
    Domaines d'activité: Services d'architecture
    Lieu d'exécution: Rabat, Maroc
    Date limite: 15/12/2026 10:00
    Estimation: 2 000 000 MAD TTC
    """
    candidate = MarketCandidate(
        title=listing_title,
        url=url,
        source='www.marchespublics.gov.ma',
        reference='99/2026/TEST',
        institution='Commune Test',
        publication_date=today - timedelta(days=2),
        deadline=today + timedelta(days=40),
        source_status='open',
        morocco_related=True,
        source_type='OFFICIAL_PROCUREMENT',
        official_url=url,
        metadata={'discovery_url': url},
    )
    enriched = enrich_detail(candidate, _FakePages(url, page_text))
    assert enriched.metadata.get('detail_enrichment_status') == 'enriched'
    assert enriched.procedure_type == 'competition'
    pmmp = enriched.metadata.get('pmmp') or {}
    domains = ' '.join(pmmp.get('activity_domains') or [])
    scope = ' '.join(filter(None, (
        enriched.raw_text, enriched.institution, enriched.location_evidence,
        domains, pmmp.get('procedure'), enriched.procedure_type)))
    final = evaluate_relevance(
        enriched.title, scope=scope, procedure_type=enriched.procedure_type,
        estimated_amount=enriched.estimated_amount,
        amount_verified=enriched.estimated_amount_verified)
    assert final['business_category'] == 'P1_CONCOURS'
    assert final['reason_code'] == REASON_ACCEPT_CONCOURS
