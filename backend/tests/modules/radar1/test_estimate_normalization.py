"""Placeholder estimates must not drop an otherwise valid Radar 1 candidate."""
from datetime import timedelta
from unittest.mock import Mock

from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.core.validation import today_in_morocco
from app.integrations.http.html import Page
from app.integrations.pmmp.parser import (
    build_pmmp_detail, enrich_detail, labelled_fields, normalize_estimate, procurement_metadata)
from app.modules.radar1_markets.schemas import MarketCandidate
from test_agent import candidate
from test_phase3 import URL


def test_placeholder_star_ttc_mad_is_not_an_amount():
    parsed = normalize_estimate('* TTC MAD', official=True, source='PMMP')
    assert parsed['amount'] is None
    assert parsed['currency'] == 'MAD'
    assert parsed['tax_mode'] == 'TTC'
    assert parsed['verified'] is False


def test_dash_and_non_communique_are_missing_amounts():
    assert normalize_estimate('—')['amount'] is None
    assert normalize_estimate('-')['amount'] is None
    assert normalize_estimate('N/A')['amount'] is None
    assert normalize_estimate('Non communiqué')['amount'] is None
    assert normalize_estimate('À définir')['amount'] is None
    assert normalize_estimate('')['amount'] is None
    assert normalize_estimate(None)['amount'] is None
    assert normalize_estimate('Non communiqué')['verified'] is False


def test_french_amounts_parse():
    twenty = normalize_estimate('28 400 000,00 MAD TTC', official=True, source='PMMP')
    assert twenty['amount'] == 28_400_000
    assert twenty['currency'] == 'MAD'
    assert twenty['tax_mode'] == 'TTC'
    assert twenty['verified'] is True
    assert normalize_estimate('3 552 000,00')['amount'] == 3_552_000
    assert normalize_estimate(28_400_000)['amount'] == 28_400_000
    assert normalize_estimate(3552000.0)['amount'] == 3_552_000


def test_structured_valid_estimate_is_preserved():
    parsed = normalize_estimate({
        'amount': '28 400 000,00',
        'currency': 'MAD',
        'tax_basis': 'TTC',
        'verified': True,
        'source': 'PMMP',
    })
    assert parsed['amount'] == 28_400_000
    assert parsed['currency'] == 'MAD'
    assert parsed['tax_mode'] == 'TTC'
    assert parsed['verified'] is True
    assert parsed['source'] == 'PMMP'


def test_structured_placeholder_is_not_verified():
    parsed = normalize_estimate({
        'amount': '* TTC MAD', 'currency': 'MAD', 'tax_basis': 'TTC', 'verified': True,
    })
    assert parsed['amount'] is None
    assert parsed['verified'] is False
    assert parsed['currency'] == 'MAD'
    assert parsed['tax_mode'] == 'TTC'


def test_missing_estimate_candidate_survives_validation():
    item = MarketCandidate(title='Études architecturales et suivi des travaux')
    assert item.estimated_amount is None
    assert item.estimated_amount_verified is False
    assert item.budget is None


def test_placeholder_string_is_sanitized_before_strict_validation():
    item = MarketCandidate(
        title='Études architecturales ISTA Tahannaout',
        estimated_amount='* TTC MAD',
        estimated_amount_verified=True,
        budget='Non communiqué',
    )
    assert item.estimated_amount is None
    assert item.estimated_amount_verified is False
    assert item.estimated_currency == 'MAD'
    assert item.estimated_amount_tax_mode == 'TTC'
    assert item.budget is None
    radar = RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS')
    poisoned = item.model_copy(update={'estimated_amount': '* TTC MAD', 'estimated_amount_verified': True})
    normalized = radar.normalize_candidate(poisoned)
    assert normalized.estimated_amount is None
    assert normalized.estimated_amount_verified is False
    assert normalized.title.startswith('Études architecturales')


def test_invalid_estimate_does_not_consume_caution():
    page = Page(
        '<p>Référence : REF-CAUTION</p>'
        '<p>Estimation (en Dhs TTC) : *</p>'
        '<p>Caution provisoire : 10 000 MAD</p>')
    facts = procurement_metadata(page, URL)
    assert facts['estimated_amount'] is None
    assert facts['estimated_amount_verified'] is False
    assert facts['estimated_currency'] == 'MAD'
    assert facts['estimated_amount_tax_mode'] == 'TTC'
    assert facts['provisional_bond_amount'] == 10_000
    labelled = labelled_fields(page)
    snapshot = build_pmmp_detail({**labelled, **facts}, URL, page.text)
    assert snapshot['estimate']['amount'] is None
    assert snapshot['estimate']['verified'] is False
    assert snapshot['provisional_guarantee']['amount'] == 10_000
    assert snapshot['estimate']['amount'] != snapshot['provisional_guarantee']['amount']


def test_enrich_detail_keeps_candidate_when_estimate_is_placeholder():
    deadline = (today_in_morocco() + timedelta(days=20)).strftime('%d/%m/%Y')
    page = Page(
        '<p>Référence : 101/2026/OFPPT</p>'
        '<p>Objet : Études architecturales ISTA Tahannaout</p>'
        '<p>Acheteur public : OFPPT</p>'
        '<p>Lieu d’exécution : Tahannaout</p>'
        f'<p>Date et heure limite de remise des plis : {deadline} à 10:30</p>'
        '<p>Estimation (en Dhs TTC) : *</p>'
        '<p>Caution provisoire : 70 000 MAD</p>')
    pages = Mock()
    pages.get.return_value = (URL, page)
    item = enrich_detail(candidate(
        url=URL, official_url=URL, title='Études architecturales ISTA Tahannaout',
        reference='101/2026/OFPPT', institution='OFPPT'), pages)
    assert isinstance(item, MarketCandidate)
    assert item.estimated_amount is None
    assert item.estimated_amount_verified is False
    assert item.estimated_currency == 'MAD'
    assert item.estimated_amount_tax_mode == 'TTC'
    assert item.provisional_bond_amount == 70_000
    assert item.metadata['pmmp']['estimate']['amount'] is None
    assert item.metadata['pmmp']['estimate']['verified'] is False
    assert item.metadata['pmmp']['provisional_guarantee']['amount'] == 70_000
    radar = RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS')
    assert radar.normalize_candidate(item).reference == '101/2026/OFPPT'
