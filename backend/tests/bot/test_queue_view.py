"""Persistent Telegram queue view — in-place slot reuse (UX only)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import BadRequest

from backend.app.bot.handlers.common import on_callback
from backend.app.bot.handlers.markets import handle, parse_market_callback, show_page
from backend.app.bot.queue_view import QUEUE_VIEW_KEY, cleanup_queue_view, render_queue_slots
from backend.app.core.review import CODE
from backend.tests.bot.test_bot import fixture_update
from test_market_usability import review_rows


def _view(context):
    return context.user_data[QUEUE_VIEW_KEY]


async def test_a_opening_queue_creates_one_queue_view(app):
    review_rows(app, 5)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    view = _view(context)
    assert len(view['result_message_ids']) == 5
    assert view['navigation_message_id'] is not None
    assert update.callback_query.message.reply_text.await_count == 6
    assert view['mode'] == 'pending' and view['page'] == 0


async def test_b_page1_to_page2_reuses_result_message_ids(app):
    review_rows(app, 10)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    first_ids = list(_view(context)['result_message_ids'])
    nav_id = _view(context)['navigation_message_id']
    update2, context2 = fixture_update(app, data='m:pending:1')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await handle(update2, context2, parse_market_callback('m:pending:1'))
    assert _view(context2)['result_message_ids'] == first_ids
    assert _view(context2)['navigation_message_id'] == nav_id
    assert update2.callback_query.message.reply_text.await_count == 0
    assert context.application.bot.edit_message_text.await_count >= 5


async def test_c_page2_to_page1_reuses_same_block(app):
    review_rows(app, 10)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    ids = list(_view(context)['result_message_ids'])
    for data in ('m:pending:1', 'm:pending:0'):
        nxt, ctx = fixture_update(app, data=data)
        ctx.user_data = context.user_data
        ctx.application.bot = context.application.bot
        await handle(nxt, ctx, parse_market_callback(data))
    assert _view(context)['result_message_ids'] == ids
    assert _view(context)['page'] == 0


async def test_d_five_to_two_clears_unused_slot_buttons(app):
    review_rows(app, 7)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    assert len(_view(context)['result_message_ids']) == 5
    update2, context2 = fixture_update(app, data='m:pending:1')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await handle(update2, context2, parse_market_callback('m:pending:1'))
    assert len(_view(context2)['result_message_ids']) == 2
    assert context.application.bot.delete_message.await_count == 3


async def test_e_two_to_five_reuses_and_creates_only_missing(app):
    review_rows(app, 7)
    update, context = fixture_update(app, data='m:pending:1')
    await handle(update, context, parse_market_callback('m:pending:1'))
    two = list(_view(context)['result_message_ids'])
    assert len(two) == 2
    update2, context2 = fixture_update(app, data='m:pending:0')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await handle(update2, context2, parse_market_callback('m:pending:0'))
    five = _view(context2)['result_message_ids']
    assert five[:2] == two
    assert len(five) == 5
    # Only three new result messages (+ nav already existed so not resent).
    assert update2.callback_query.message.reply_text.await_count == 3


async def test_f_details_edits_same_card_and_back_restores(app):
    record = review_rows(app)[0]
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    slots = list(_view(context)['result_message_ids'])
    details, dctx = fixture_update(app, data=f'm:details:pending:{record["id"]}:0')
    dctx.user_data = context.user_data
    dctx.application.bot = context.application.bot
    await on_callback(details, dctx)
    assert context.application.bot.edit_message_text.await_count >= 1
    back = context.application.bot.edit_message_text.call_args.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data
    back_u, bctx = fixture_update(app, data=back)
    bctx.user_data = dctx.user_data
    bctx.application.bot = context.application.bot
    await on_callback(back_u, bctx)
    assert _view(bctx)['result_message_ids'] == slots
    assert _view(bctx)['page'] == 0
    assert back_u.callback_query.message.reply_text.await_count == 0


async def test_g_validate_reject_refreshes_in_place(app):
    rows = review_rows(app, 3)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    nav = _view(context)['navigation_message_id']
    record = rows[0]
    rej, rctx = fixture_update(app, data=f'm:reject:{record["id"]}:{record["version"]}:0')
    rctx.user_data = context.user_data
    rctx.application.bot = context.application.bot
    await on_callback(rej, rctx)
    assert _view(rctx)['navigation_message_id'] == nav
    assert len(_view(rctx)['result_message_ids']) == 2
    assert rej.callback_query.message.reply_text.await_count == 0


async def test_h_queue_shrink_clamps_page(app):
    rows = review_rows(app, 6)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    page2, ctx2 = fixture_update(app, data='m:pending:1')
    ctx2.user_data = context.user_data
    ctx2.application.bot = context.application.bot
    await handle(page2, ctx2, parse_market_callback('m:pending:1'))
    assert _view(ctx2)['page'] == 1
    assert len(_view(ctx2)['result_message_ids']) == 1
    record = rows[-1]
    rej, rctx = fixture_update(app, data=f'm:reject:{record["id"]}:{record["version"]}:1')
    rctx.user_data = ctx2.user_data
    rctx.application.bot = context.application.bot
    await on_callback(rej, rctx)
    # Page 2 gone → clamp to page 0 with the remaining five.
    assert _view(rctx)['page'] == 0
    assert len(_view(rctx)['result_message_ids']) == 5


async def test_i_rapid_suivant_one_effective_transition(app):
    review_rows(app, 10)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    ids = list(_view(context)['result_message_ids'])
    updates = []
    for _ in range(3):
        u, c = fixture_update(app, data='m:pending:1')
        c.user_data = context.user_data
        c.application = context.application
        updates.append((u, c))
    import asyncio
    await asyncio.gather(*(on_callback(u, c) for u, c in updates))
    assert _view(context)['result_message_ids'] == ids
    assert _view(context)['page'] == 1
    assert context.application.bot.edit_message_text.await_count <= 12


async def test_j_deleted_slot_is_recreated(app):
    review_rows(app, 3)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    missing = _view(context)['result_message_ids'][0]
    created = {'n': 5000}

    async def fail_missing(**kwargs):
        if kwargs.get('message_id') == missing:
            raise BadRequest('message to edit not found')
        return SimpleNamespace(message_id=kwargs.get('message_id'))

    async def reply_text(*args, **kwargs):
        created['n'] += 1
        return SimpleNamespace(message_id=created['n'])

    context.application.bot.edit_message_text = AsyncMock(side_effect=fail_missing)
    update2, context2 = fixture_update(app, data='m:pending:0')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    update2.callback_query.message.reply_text = AsyncMock(side_effect=reply_text)
    await handle(update2, context2, parse_market_callback('m:pending:0'))
    assert update2.callback_query.message.reply_text.await_count >= 1
    assert _view(context2)['result_message_ids'][0] == 5001
    assert _view(context2)['result_message_ids'][0] != missing
    assert len(_view(context2)['result_message_ids']) == 3


async def test_k_user_a_and_user_b_state_isolated(app):
    app.config['ALLOWED_TELEGRAM_USER_IDS'] = frozenset({123, 456})
    review_rows(app, 5)
    a_update, a_ctx = fixture_update(app, user_id=123, data=f'pending:{CODE}')
    await on_callback(a_update, a_ctx)
    b_update, b_ctx = fixture_update(app, user_id=456, data=f'pending:{CODE}')
    await on_callback(b_update, b_ctx)
    assert a_ctx.user_data is not b_ctx.user_data
    a_ids = list(_view(a_ctx)['result_message_ids'])
    b_ids = list(_view(b_ctx)['result_message_ids'])
    await show_page(a_update.callback_query.message, app, 'pending', 0, a_ctx)
    assert _view(b_ctx)['result_message_ids'] == b_ids
    assert _view(a_ctx)['result_message_ids'] == a_ids


async def test_message_not_modified_is_harmless(app):
    message = SimpleNamespace(reply_text=AsyncMock(side_effect=lambda *a, **k: SimpleNamespace(message_id=1)),
                              chat=SimpleNamespace(id=9), chat_id=9)
    bot = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest('Message is not modified')),
        delete_message=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
    )
    context = SimpleNamespace(application=SimpleNamespace(bot=bot), user_data={
        QUEUE_VIEW_KEY: {
            'view_key': 't', 'code': CODE, 'mode': 'pending', 'page': 0,
            'result_message_ids': [1], 'navigation_message_id': 2, 'chat_id': 9,
        }
    })
    await render_queue_slots(
        message, context, view_key='t', code=CODE, mode='pending', page=0,
        slots=[{'text': 'same', 'reply_markup': None}],
        nav_text='Page 1/1', nav_markup=None, parse_mode=None)
    assert _view(context)['result_message_ids'] == [1]
    assert message.reply_text.await_count == 0


async def test_cleanup_on_retour_clears_actionable_slots(app):
    review_rows(app, 3)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    assert QUEUE_VIEW_KEY in context.user_data
    await cleanup_queue_view(context, update.callback_query.message, keep_navigation=True)
    assert QUEUE_VIEW_KEY not in context.user_data
    assert context.application.bot.delete_message.await_count == 3
