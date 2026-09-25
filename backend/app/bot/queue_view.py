"""Persistent per-user Telegram queue view: reuse/edit message slots in place.

Telegram-only rendering. No Radar/review business logic lives here.
"""
from __future__ import annotations

from telegram.error import BadRequest, TelegramError

QUEUE_VIEW_KEY = 'queue_view'


def get_queue_view(context):
    if context is None or not hasattr(context, 'user_data') or context.user_data is None:
        return None
    return context.user_data.get(QUEUE_VIEW_KEY)


def _chat_id(message):
    chat = getattr(message, 'chat', None)
    if chat is not None:
        return getattr(chat, 'id', chat)
    return getattr(message, 'chat_id', None)


def _bot(context):
    return getattr(getattr(context, 'application', None), 'bot', None)


def _is_not_modified(error):
    return 'message is not modified' in str(error).lower()


async def _safe_edit_text(bot, chat_id, message_id, text, reply_markup=None, **kwargs):
    """Edit a message; treat 'not modified' as success. Return True on success."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            **kwargs,
        )
        return True
    except BadRequest as error:
        if _is_not_modified(error):
            return True
        return False
    except TelegramError:
        return False


async def _safe_clear_markup(bot, chat_id, message_id):
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None)
    except (BadRequest, TelegramError, AttributeError):
        pass


async def _safe_delete(bot, chat_id, message_id):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        return True
    except (BadRequest, TelegramError, AttributeError):
        return False


async def _send_text(message, bot, chat_id, text, reply_markup=None, **kwargs):
    """Create a new queue slot message; prefer reply_text for test/compat anchors."""
    if message is not None and hasattr(message, 'reply_text'):
        return await message.reply_text(text, reply_markup=reply_markup, **kwargs)
    return await bot.send_message(
        chat_id=chat_id, text=text, reply_markup=reply_markup, **kwargs)


async def cleanup_queue_view(context, message=None, *, keep_navigation=False):
    """Remove or neutralize a stored queue view. Optionally leave the nav message for reuse."""
    view = get_queue_view(context)
    if not view:
        return
    bot = _bot(context)
    chat_id = view.get('chat_id') or _chat_id(message)
    if bot and chat_id is not None:
        for message_id in list(view.get('result_message_ids') or []):
            if not await _safe_delete(bot, chat_id, message_id):
                await _safe_clear_markup(bot, chat_id, message_id)
        nav_id = view.get('navigation_message_id')
        if nav_id is not None and not keep_navigation:
            if not await _safe_delete(bot, chat_id, nav_id):
                await _safe_clear_markup(bot, chat_id, nav_id)
    if hasattr(context, 'user_data') and context.user_data is not None:
        context.user_data.pop(QUEUE_VIEW_KEY, None)


async def render_queue_slots(
    message,
    context,
    *,
    view_key,
    code,
    mode,
    page,
    slots,
    nav_text,
    nav_markup,
    parse_mode=None,
    disable_web_page_preview=True,
):
    """Sync result slots + one navigation message to ``slots`` / nav content.

    ``slots`` is a list of ``{'text': str, 'reply_markup': Markup|None}``.
    Reuses stored Telegram message IDs; creates only missing slots; deletes extras.
    """
    if context is None or not hasattr(context, 'user_data') or context.user_data is None:
        # No per-user state — fall back to one-shot send (should not happen in bot).
        for slot in slots:
            await message.reply_text(
                slot['text'], reply_markup=slot.get('reply_markup'),
                parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        await message.reply_text(nav_text, reply_markup=nav_markup, parse_mode=parse_mode)
        return None

    bot = _bot(context)
    chat_id = _chat_id(message)
    previous = get_queue_view(context) or {}
    if previous.get('view_key') and previous.get('view_key') != view_key:
        await cleanup_queue_view(context, message)
        previous = {}

    result_ids = list(previous.get('result_message_ids') or [])
    nav_id = previous.get('navigation_message_id')
    edit_kwargs = {'parse_mode': parse_mode, 'disable_web_page_preview': disable_web_page_preview}

    # Grow or update slots.
    for index, slot in enumerate(slots):
        text = slot['text']
        markup = slot.get('reply_markup')
        if index < len(result_ids) and bot and chat_id is not None:
            ok = await _safe_edit_text(
                bot, chat_id, result_ids[index], text, markup, **edit_kwargs)
            if ok:
                continue
            # Missing / uneditable — recreate and replace the stored id.
            sent = await _send_text(
                message, bot, chat_id, text, markup,
                parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
            new_id = getattr(sent, 'message_id', None)
            if new_id is not None:
                result_ids[index] = new_id
            continue
        sent = await _send_text(
            message, bot, chat_id, text, markup,
            parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        new_id = getattr(sent, 'message_id', None)
        if new_id is not None:
            if index < len(result_ids):
                result_ids[index] = new_id
            else:
                result_ids.append(new_id)

    # Shrink: remove unused actionable slots.
    while len(result_ids) > len(slots):
        stale_id = result_ids.pop()
        if bot and chat_id is not None:
            if not await _safe_delete(bot, chat_id, stale_id):
                await _safe_clear_markup(bot, chat_id, stale_id)

    # Navigation footer — single reusable message.
    if nav_id is not None and bot and chat_id is not None:
        ok = await _safe_edit_text(bot, chat_id, nav_id, nav_text, nav_markup, parse_mode=parse_mode)
        if not ok:
            sent = await _send_text(message, bot, chat_id, nav_text, nav_markup, parse_mode=parse_mode)
            nav_id = getattr(sent, 'message_id', nav_id)
    else:
        sent = await _send_text(message, bot, chat_id, nav_text, nav_markup, parse_mode=parse_mode)
        nav_id = getattr(sent, 'message_id', None)

    view = {
        'view_key': view_key,
        'code': code,
        'mode': mode,
        'page': page,
        'result_message_ids': result_ids,
        'navigation_message_id': nav_id,
        'chat_id': chat_id,
        'detail_message_id': None,
    }
    context.user_data[QUEUE_VIEW_KEY] = view
    return view


async def show_inline_details(query, context, *, text, reply_markup, parse_mode=None,
                              disable_web_page_preview=True):
    """Edit the clicked result card into its detail view (same message)."""
    from telegram.error import BadRequest as TelegramBadRequest
    try:
        await query.answer()
    except TelegramBadRequest:
        pass

    message = query.message
    message_id = getattr(message, 'message_id', None)
    bot = _bot(context)
    chat_id = _chat_id(message)
    edited = False
    if bot and chat_id is not None and message_id is not None:
        edited = await _safe_edit_text(
            bot, chat_id, message_id, text, reply_markup,
            parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        if not edited and hasattr(query, 'edit_message_text'):
            try:
                await query.edit_message_text(
                    text, reply_markup=reply_markup, parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview)
                edited = True
            except BadRequest as error:
                if _is_not_modified(error):
                    edited = True
            except TelegramError:
                edited = False

    if not edited:
        sent = await message.reply_text(
            text, reply_markup=reply_markup, parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview)
        message_id = getattr(sent, 'message_id', message_id)

    view = get_queue_view(context)
    if view is not None:
        view['detail_message_id'] = message_id
        context.user_data[QUEUE_VIEW_KEY] = view
    return message_id
