from datetime import timedelta
from unittest.mock import Mock

from backend.app.core.validation import today_in_morocco
from backend.app.bot.presenters.result_presenter import format_result_card, format_result_details
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import enrich_detail, procurement_metadata
from backend.app.db.extensions import db
from backend.app.db.models import Result
from backend.app.core.review import page as review_page, decide
from backend.app.modules.radar1_markets.official_link_resolver import OfficialLinkResolver
from test_agent import candidate
from test_phase3 import execute, URL


def notice(extra=''):
    deadline = (today_in_morocco() + timedelta(days=20)).strftime('%d/%m/%Y')
    published = today_in_morocco().strftime('%d/%m/%Y')
    return Page(
        f'<h1>Etude architecturale patrimoniale</h1>'
        f'<p>Référence : REF-1</p><p>Acheteur public : Institution</p>'
        f'<p>Date de publication : {published}</p>'
        f'<p>Date et heure limite de remise des plis : {deadline} à 10:30</p>{extra}'
    )


def test_official_estimate_dates_and_time_are_extracted():
    pages = Mock()
    pages.get.return_value = (URL, notice(
        '<p>Estimation du coût des prestations : 2 450 000 MAD TTC</p>'
        '<p>Caution provisoire : 50 000 MAD</p>'))
    item = enrich_detail(candidate(url=URL, official_url=URL), pages)
    assert item.estimated_amount == 2_450_000
    assert item.estimated_currency == 'MAD' and item.estimated_amount_tax_mode == 'TTC'
    assert item.estimated_amount_source == 'PMMP' and item.estimated_amount_verified
    assert item.provisional_bond_amount == 50_000
    assert item.publication_date_verified and item.deadline_verified
    assert item.deadline_time == '10:30'


def test_caution_alone_never_becomes_budget():
    facts = procurement_metadata(notice('<p>Caution provisoire : 50 000 MAD</p>'), URL)
    assert facts['provisional_bond_amount'] == 50_000
    assert 'estimated_amount' not in facts


def test_lot_estimates_stay_separate_without_invented_total():
    facts = procurement_metadata(notice(
        '<p>Lot 1 : 1 000 000 MAD TTC;</p><p>Lot 2 : 2 000 000 MAD TTC;</p>'), URL)
    assert 'estimated_amount' not in facts
    assert [lot['amount'] for lot in facts['estimated_lots']] == [1_000_000, 2_000_000]


def test_latest_deadline_and_time_win_when_notice_is_extended():
    old = (today_in_morocco() + timedelta(days=10)).strftime('%d/%m/%Y')
    new = (today_in_morocco() + timedelta(days=30)).strftime('%d/%m/%Y')
    page = notice(
        f'<p>Date limite de remise des plis : {old} à 09:00</p>'
        f'<p>Date limite de remise des plis : {new} à 12:00</p>')
    pages = Mock()
    pages.get.return_value = (URL, page)
    item = enrich_detail(candidate(url=URL, official_url=URL), pages)
    assert item.deadline == today_in_morocco() + timedelta(days=30)
    assert item.deadline_time == '12:00'


def test_secondary_estimate_requires_strong_identity_and_stays_unverified():
    secondary = candidate(estimated_amount=900_000, estimated_currency='MAD',
        estimated_amount_source='MARCHE_FACILE', estimated_amount_verified=False)
    official = candidate(estimated_amount=None)
    merged = OfficialLinkResolver.merge_secondary_procurement(secondary, official)
    assert merged.estimated_amount == 900_000 and not merged.estimated_amount_verified
    wrong_buyer = secondary.model_copy(update={'institution': 'Autre acheteur'})
    assert OfficialLinkResolver.merge_secondary_procurement(wrong_buyer, official).estimated_amount is None


def test_persisted_metadata_drives_card_and_details_without_fetch(app):
    item = candidate(estimated_amount=2_450_000, estimated_currency='MAD',
        estimated_amount_tax_mode='TTC', estimated_amount_source='PMMP',
        estimated_amount_verified=True, deadline_time='10:00',
        provisional_bond_amount=50_000, provisional_bond_currency='MAD')
    execute(app, [item])
    card = review_page(app, 'pending', 0)[0][0]
    text = format_result_card(card, 1, 'pending')
    assert '💰 Estimation : 2 450 000 MAD TTC' in text
    assert '📅 Publication :' in text and '⏳ Échéance :' in text and ' à 10:00' in text
    details = format_result_details(card)
    assert 'Caution provisoire : 50 000 MAD' in details
    assert 'Estimation : 2 450 000 MAD TTC — vérifiée (PMMP)' in details


def test_missing_and_secondary_estimate_card_labels():
    base = {'title': 'Avis', 'deadline': '2026-10-01', 'publication': '2026-09-01',
            'source': 'marchespublics.gov.ma', 'url': URL, 'estimated_amount': None}
    assert '💰 Estimation : non vérifiée' in format_result_card(base, 1, 'pending')
    secondary = {**base, 'estimated_amount': 1000, 'estimated_currency': 'MAD',
                 'estimated_amount_source': 'MARCHE_FACILE', 'estimated_amount_verified': False}
    assert '⚠️ Source secondaire — à confirmer' in format_result_card(secondary, 1, 'pending')


def test_estimate_correction_is_a_meaningful_update(app):
    first = candidate(estimated_amount=1_000_000, estimated_currency='MAD',
                      estimated_amount_source='PMMP', estimated_amount_verified=True)
    execute(app, [first])
    card = review_page(app, 'pending', 0)[0][0]
    decide(app, card['id'], card['version'], 'approved', 123)
    execute(app, [first.model_copy(update={'estimated_amount': 1_200_000})])
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert row.review_status == 'PENDING'
        assert 'estimated_amount' in row.update_reason['changed_fields']
