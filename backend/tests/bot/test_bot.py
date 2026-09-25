from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import NetworkError

from backend.app.bot import build_application
from backend.app.bot.routing import parse_callback
from backend.app.bot.handlers.common import fallback, on_callback, on_error, start
from backend.app.bot.keyboards.main import main_keyboard, radar_keyboard


def fixture_update(app, user_id=123, data=None, chat_type='private'):
    counter = {'n': 0}

    async def reply_text(*args, **kwargs):
        counter['n'] += 1
        return SimpleNamespace(message_id=counter['n'])

    async def edit_message_text(*, chat_id=None, message_id=None, text=None, reply_markup=None, **kwargs):
        return SimpleNamespace(message_id=message_id, text=text, reply_markup=reply_markup)

    message = SimpleNamespace(
        reply_text=AsyncMock(side_effect=reply_text),
        chat=SimpleNamespace(id=1),
        chat_id=1,
        message_id=100,
    )
    query = None if data is None else SimpleNamespace(
        data=data, answer=AsyncMock(), edit_message_text=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        delete_message=AsyncMock(), message=message)
    update = SimpleNamespace(effective_user=SimpleNamespace(id=user_id),
                             effective_chat=SimpleNamespace(type=chat_type),
                             effective_message=message, callback_query=query)
    bot = SimpleNamespace(
        delete_message=AsyncMock(),
        edit_message_text=AsyncMock(side_effect=edit_message_text),
        edit_message_reply_markup=AsyncMock(),
        send_message=AsyncMock(side_effect=lambda **kw: reply_text(kw.get('text'), **{
            k: v for k, v in kw.items() if k != 'chat_id' and k != 'text'})),
    )
    context = SimpleNamespace(
        application=SimpleNamespace(bot_data={'flask_app': app}, bot=bot),
        user_data={})
    return update, context


@pytest.mark.parametrize('handler', [start, fallback])
async def test_unauthorized_messages(app, handler):
    update, context = fixture_update(app, user_id=999)
    await handler(update, context)
    update.effective_message.reply_text.assert_awaited_once_with('Accès non autorisé.')


async def test_unauthorized_callback_cannot_reach_service(app):
    update, context = fixture_update(app, user_id=999, data='search:RADAR_1_MARKETS')
    with patch('app.bot.handlers.common.radar_action') as action:
        await on_callback(update, context)
        action.assert_not_called()
    update.callback_query.answer.assert_awaited_once_with('Accès non autorisé.', show_alert=True)


async def test_private_chat_only(app):
    update, context = fixture_update(app, chat_type='supergroup')
    await start(update, context)
    update.effective_message.reply_text.assert_awaited_once_with('Utilisez ce bot en conversation privée.')


async def test_navigation_and_invalid_callback(app):
    update, context = fixture_update(app, data='radar:RADAR_1_MARKETS')
    await on_callback(update, context)
    assert 'Marchés' in update.callback_query.edit_message_text.call_args.args[0]
    update, context = fixture_update(app, data='invalid:payload')
    await on_callback(update, context)
    update.callback_query.answer.assert_awaited_once_with('Action invalide. Utilisez /start.', show_alert=True)


async def test_search_handler_dispatches_business_service(app):
    update, context = fixture_update(app, data='search:RADAR_1_MARKETS')
    with patch('app.bot.handlers.common.launch_search', new_callable=AsyncMock) as launch:
        await on_callback(update, context)
        launch.assert_awaited_once_with(update, context, 'RADAR_1_MARKETS', 1)


async def test_rapid_repeated_callback_is_debounced(app):
    update, context = fixture_update(app, data='radar:RADAR_1_MARKETS')
    await on_callback(update, context)
    await on_callback(update, context)
    update.callback_query.edit_message_text.assert_awaited_once()
    assert update.callback_query.answer.await_count == 2


@pytest.mark.parametrize('code,module', [
    ('RADAR_2_PROJECTS', 'app.bot.handlers.projects'),
    ('RADAR_3_INSTITUTIONS', 'app.bot.handlers.institutions'),
    ('RADAR_4_POLICIES', 'app.bot.handlers.policies'),
    ('RADAR_5_FUNDING', 'app.bot.handlers.funding'),
])
async def test_all_radar_queue_callbacks_render(app, code, module):
    update, context = fixture_update(app, data=f'pending:{code}')
    with patch(module + '.show_page', new_callable=AsyncMock) as show:
        await on_callback(update, context)
        show.assert_awaited_once_with(update.callback_query.message, app, 'pending', 0, context)


async def test_error_handler_survives_telegram_outage(app, caplog):
    update, context = fixture_update(app)
    context.error = NetworkError('token-secret')
    update.effective_message.reply_text.side_effect = NetworkError('token-secret')
    await on_error(update, context)
    assert 'token-secret' not in caplog.text
    assert 'NetworkError' in caplog.text


def test_keyboards_and_application_build(app):
    from backend.app.bot import handlers
    assert not hasattr(handlers, 'myid')
    keyboard = main_keyboard()
    assert len(keyboard.inline_keyboard) == 6
    assert keyboard.inline_keyboard[-1][0].callback_data == 't:menu'
    for row in keyboard.inline_keyboard:
        if row[0].callback_data == 't:menu':
            continue
        _, code = parse_callback(row[0].callback_data)
        for submenu_row in radar_keyboard(code).inline_keyboard:
            data = submenu_row[0].callback_data
            assert len(data.encode('utf-8')) <= 64
            parse_callback(data)
    application = build_application(app)
    assert len(application.handlers[0]) == 3
    assert all('myid' not in getattr(handler, 'commands', ()) for handler in application.handlers[0])


async def test_authorized_start_still_displays_five_radars(app):
    update, context = fixture_update(app)
    await start(update, context)
    assert len(update.effective_message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard) == 6
