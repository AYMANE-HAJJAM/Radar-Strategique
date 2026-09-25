"""Regression: PMMP official detail with parenthetical estimate label (RGON)."""
from pathlib import Path
from unittest.mock import Mock

from backend.app.bot.presenters.result_presenter import format_result_card
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import (
    _amount, build_pmmp_detail, enrich_detail, field_name, labelled_fields,
    procurement_metadata,
)
from test_agent import candidate

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'pmmp_detail_rgo_04_2026.html'
URL = ('https://www.marchespublics.gov.ma/index.php?'
       'page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042001&orgAcronyme=rgo')


def test_french_decimal_amount_not_inflated_by_fold():
    assert _amount('28 400 000,00') == (28_400_000.0, None)
    assert _amount('28 400 000,00 MAD TTC') == (28_400_000.0, 'MAD')
    assert _amount('3 552 000 MAD') == (3_552_000.0, 'MAD')
    assert _amount('0') == (0.0, None)


def test_parenthetical_estimation_label_maps():
    assert field_name('Estimation (en Dhs TTC)') == 'estimated_amount'
    assert field_name('Estimation du coût des prestations') == 'estimated_amount'


def test_rgo_fixture_full_official_detail():
    html = FIXTURE.read_text(encoding='utf-8')
    page = Page(html)
    fields = labelled_fields(page)
    meta = procurement_metadata(page, URL)
    assert fields['reference'] == '04/2026/CA/BR/RGON'
    assert fields['location'] == 'SIDI IFNI'
    assert meta['estimated_amount'] == 28_400_000
    assert meta['estimated_currency'] == 'MAD'
    assert meta['estimated_amount_tax_mode'] == 'TTC'
    assert meta['estimated_amount_verified'] is True
    assert meta['provisional_bond_amount'] == 0
    assert meta['estimated_amount'] != meta['provisional_bond_amount']
    assert fields.get('admin_contact')
    assert fields.get('meeting') is not None or meta.get('meeting') is not None
    pmmp = build_pmmp_detail({**fields, **meta, 'location_evidence': fields['location']}, URL, page.text)
    assert pmmp['reference'] == '04/2026/CA/BR/RGON'
    assert pmmp['execution_location'] == 'SIDI IFNI'
    assert pmmp['estimate']['amount'] == 28_400_000
    assert pmmp['estimate']['currency'] == 'MAD'
    assert pmmp['estimate']['tax_basis'] == 'TTC'
    assert pmmp['estimate']['verified'] is True
    assert pmmp['provisional_guarantee']['amount'] == 0


def test_rgo_enrich_detail_and_telegram_card():
    html = FIXTURE.read_text(encoding='utf-8')
    pages = Mock()
    pages.get.return_value = (URL, Page(html))
    item = enrich_detail(
        candidate(url=URL, official_url=URL, title='Réhabilitation SIDI IFNI',
                  reference='04/2026/CA/BR/RGON', institution='Conseil régional'),
        pages)
    assert item.estimated_amount == 28_400_000
    assert item.estimated_currency == 'MAD'
    assert item.estimated_amount_tax_mode == 'TTC'
    assert item.estimated_amount_verified is True
    assert item.provisional_bond_amount == 0
    assert item.metadata['pmmp']['estimate']['amount'] == 28_400_000
    assert item.metadata['pmmp']['provisional_guarantee']['amount'] == 0
    pages.get.assert_called_once()

    payload = {
        'id': 1,
        'version': 'abcdef123456',
        'title': item.title,
        'institution': item.institution,
        'city': item.location_evidence or 'SIDI IFNI',
        'reference': item.reference,
        'estimated_amount': item.estimated_amount,
        'estimated_currency': item.estimated_currency,
        'estimated_amount_tax_mode': item.estimated_amount_tax_mode,
        'estimated_amount_verified': item.estimated_amount_verified,
        'estimated_amount_source': item.estimated_amount_source,
        'publication': str(item.publication_date or ''),
        'deadline': str(item.deadline or ''),
        'status': item.source_status,
        'url': URL,
        'source': 'marchespublics.gov.ma',
    }
    text = format_result_card(payload, 1, 'pending')
    assert '💰 Estimation : 28 400 000 MAD TTC' in text
    assert 'non vérifiée' not in text


def test_collapsed_hidden_div_still_readable_from_get_html():
    """PMMP « + » expansion keeps fields in the GET HTML (display:none), no AJAX."""
    html = FIXTURE.read_text(encoding='utf-8')
    assert 'display:none' in html or 'display: none' in html
    assert '28 400 000,00' in html
    assert procurement_metadata(Page(html), URL)['estimated_amount'] == 28_400_000


def test_one_detail_fetch_via_page_cache():
    html = FIXTURE.read_text(encoding='utf-8')
    reader = Mock()
    reader.get.return_value = (URL, Page(html))
    from backend.app.integrations.http.html import AccessLimitedPages
    limited = AccessLimitedPages(reader, metrics={'http_403': 0, 'http_429': 0})
    first = enrich_detail(
        candidate(url=URL, official_url=URL, title='Réhabilitation SIDI IFNI',
                  reference='04/2026/CA/BR/RGON', institution='Conseil régional'),
        limited)
    second = enrich_detail(
        candidate(url=URL, official_url=URL, title='Réhabilitation SIDI IFNI',
                  reference='04/2026/CA/BR/RGON', institution='Conseil régional'),
        limited)
    assert first.estimated_amount == second.estimated_amount == 28_400_000
    assert reader.get.call_count == 1
