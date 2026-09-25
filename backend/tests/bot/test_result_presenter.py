from unittest.mock import AsyncMock

from backend.app.bot.handlers.common import on_callback
from backend.app.bot.handlers.markets import parse_market_callback
from backend.app.bot.presenters.result_presenter import (
    format_result_card,
    format_result_details,
    format_review_reason,
    format_source_label,
    truncate,
)
from backend.tests.bot.test_bot import fixture_update
from test_market_usability import CODE, review_rows


def item(**changes):
    payload = {
        'id': 42,
        'version': '123456abcdef',
        'title': 'Étude de valorisation du patrimoine — Settat',
        'institution': 'Agence Urbaine de Settat',
        'city': 'Settat',
        'procedure': 'study',
        'publication': '2026-09-09',
        'deadline': '2026-10-02',
        'status': 'open',
        'reference': '04/2026',
        'source': 'marchespublics.gov.ma',
        'url': 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=123',
        'link_label': 'officiel PMMP',
        'reason': 'OFFICIAL_URL_NOT_CONFIRMED;DEADLINE_UNCLEAR;MEDIUM_AI_CONFIDENCE',
    }
    payload.update(changes)
    return payload


def test_compact_card_has_essentials_and_one_reason_without_url_or_internal_codes():
    card = format_result_card(item(), 1, 'pending')
    assert '[1] Étude de valorisation du patrimoine — Settat' in card
    assert '📅 Publication : 09/09/2026' in card
    assert '⏳ Échéance : 02/10/2026' in card
    assert '🔗 Source : PMMP' in card
    assert 'https://' not in card
    assert 'OFFICIAL_' not in card and 'MEDIUM_AI_CONFIDENCE' not in card
    assert 'Type' not in card


def test_long_title_truncates_on_word_boundary():
    title = ('Maîtrise d’Œuvre Ingénierie (MOEI) du projet de restauration et de réhabilitation '
             'des anciens abattoirs de Casablanca — consultation 04/2026')
    shortened = truncate(title)
    assert len(shortened) <= 115 and shortened.endswith('…')
    assert 'consultation 04/2026' not in shortened
    assert not shortened.endswith(' …')


def test_empty_fields_are_omitted_except_uncertain_deadline():
    card = format_result_card(item(institution=None, city=None, reference=None, deadline=None,
                                   reason='DEADLINE_UNCLEAR'), 2, 'pending')
    assert '🏛️' not in card and '📍' not in card and '📄' not in card
    assert '⏳ Échéance : à confirmer' in card
    news = format_result_card(item(deadline=None, status='unknown'), 2, 'approved')
    assert 'Échéance' not in news and 'Statut' not in news


def test_details_show_full_title_and_readable_values_without_raw_url_or_enums():
    full_title = 'A < B & C > D _test_ *important* (04/2026)'
    details = format_result_details(item(title=full_title))
    assert full_title in details  # Plain text parse mode makes these characters safe.
    assert 'Type : Étude' in details
    assert 'Publication : 09/09/2026' in details
    assert 'Lien : Annonce officielle PMMP' in details
    assert 'Lien officiel à confirmer' in details and 'Échéance à confirmer' in details
    assert 'https://' not in details and 'OFFICIAL_URL_NOT_CONFIRMED' not in details


def test_reason_and_source_labels_are_human_readable():
    assert format_review_reason('SECONDARY_SOURCE_ONLY') == 'Source secondaire'
    assert format_review_reason('STATUS_UNCLEAR;DEADLINE_UNCLEAR') == 'Statut à confirmer'
    assert format_source_label(item()) == 'PMMP'
    assert format_source_label(item(source='casa-amenagement.ma', url='https://casa-amenagement.ma/avis')) == 'Casablanca Aménagement'
    assert format_source_label(item(source='https://example.org/path', url=None)) == 'example.org'


async def test_details_callback_has_open_and_return_buttons(app):
    record = review_rows(app)[0]
    data = f'm:details:pending:{record["id"]}:0'
    assert parse_market_callback(data) == ('details_pending', 0, record['id'], None)
    update, context = fixture_update(app, data=data)
    await on_callback(update, context)
    update.callback_query.answer.assert_awaited()
    call = context.application.bot.edit_message_text.call_args
    assert call is not None
    assert 'https://' not in call.kwargs['text']
    rows = call.kwargs['reply_markup'].inline_keyboard
    assert rows[0][0].url == record['url']
    assert rows[-1][0].callback_data == 'm:back:pending:0'
    assert call.kwargs['parse_mode'] is None


async def test_reject_refreshes_same_logical_page(app):
    record = review_rows(app)[0]
    data = f'm:reject:{record["id"]}:{record["version"]}:0'
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    nav_id = context.user_data['queue_view']['navigation_message_id']
    update2, context2 = fixture_update(app, data=data)
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await on_callback(update2, context2)
    assert context2.user_data['queue_view']['navigation_message_id'] == nav_id
    assert context2.user_data['queue_view']['result_message_ids'] == []
    assert any(c.kwargs.get('text') == 'Aucun résultat.'
               for c in context.application.bot.edit_message_text.call_args_list)


async def test_approve_refreshes_same_logical_page(app):
    record = review_rows(app)[0]
    data = f'm:approve:{record["id"]}:{record["version"]}:0'
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    nav_id = context.user_data['queue_view']['navigation_message_id']
    update2, context2 = fixture_update(app, data=data)
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await on_callback(update2, context2)
    assert context2.user_data['queue_view']['navigation_message_id'] == nav_id
    assert context2.user_data['queue_view']['result_message_ids'] == []
    assert any(c.kwargs.get('text') == 'Aucun résultat.'
               for c in context.application.bot.edit_message_text.call_args_list)


async def test_stale_action_uses_concise_callback_answer(app):
    record = review_rows(app)[0]
    data = f'm:approve:{record["id"]}:{"0" * 12}:0'
    update, context = fixture_update(app, data=data)
    await on_callback(update, context)
    update.callback_query.answer.assert_awaited_once_with()
    update.callback_query.message.reply_text.assert_awaited_once_with('Cette action n’est plus disponible.')