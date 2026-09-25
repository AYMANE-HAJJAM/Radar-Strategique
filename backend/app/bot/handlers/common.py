import asyncio
import logging
from time import monotonic

from telegram.error import BadRequest, TelegramError

from app.bot.routing import parse_callback
from app.bot.keyboards.main import main_keyboard, radar_keyboard, COMPLETION_LABELS
from app.bot.handlers.jobs import launch_search
from app.bot.queue_view import cleanup_queue_view
from app.bot.state import UIState, set_state, expects_text, redisplay_current, begin_transition, end_transition
from app.core.constants import (
    CALLBACK_DEBOUNCE_CACHE_LIMIT, CALLBACK_DEBOUNCE_PRUNE_SECONDS, CALLBACK_DEBOUNCE_SECONDS)
from app.core.radar_registry import RADARS
from app.db.repositories.radars import RadarServiceError, radar_action
from app.core.logging import log_failure

logger = logging.getLogger(__name__)

PREFIX_HANDLERS = {
    't:': ('app.bot.handlers.targeted', 'parse_callback', 'handle'),
    'm:': ('app.bot.handlers.markets', 'parse_market_callback', 'handle'),
    'p:': ('app.bot.handlers.projects', 'parse_project_callback', 'handle'),
    'i:': ('app.bot.handlers.institutions', 'parse_institution_callback', 'handle'),
    'l:': ('app.bot.handlers.policies', 'parse_policy_callback', 'handle'),
    'f:': ('app.bot.handlers.funding', 'parse_funding_callback', 'handle'),
}

QUEUE_SHOW = {
    'RADAR_1_MARKETS': ('app.bot.handlers.markets', 'show_page'),
    'RADAR_2_PROJECTS': ('app.bot.handlers.projects', 'show_page'),
    'RADAR_3_INSTITUTIONS': ('app.bot.handlers.institutions', 'show_page'),
    'RADAR_4_POLICIES': ('app.bot.handlers.policies', 'show_page'),
    'RADAR_5_FUNDING': ('app.bot.handlers.funding', 'show_page'),
}


def _import_attr(module_path, name):
    module = __import__(module_path, fromlist=[name])
    return getattr(module, name)


def _duplicate_callback(update, context, ttl=CALLBACK_DEBOUNCE_SECONDS):
    """Debounce rapid repeated buttons per user/action while retaining stale-state checks."""
    query, user = update.callback_query, update.effective_user
    if query is None or user is None:
        return False
    now = monotonic()
    cache = context.application.bot_data.setdefault('callback_debounce', {})
    key = (user.id, query.data)
    previous = cache.get(key, 0)
    cache[key] = now
    if len(cache) > CALLBACK_DEBOUNCE_CACHE_LIMIT:
        context.application.bot_data['callback_debounce'] = {
            item: stamp for item, stamp in cache.items()
            if now - stamp < CALLBACK_DEBOUNCE_PRUNE_SECONDS}
    return now - previous < ttl


async def authorized(update, context):
    user = update.effective_user
    allowed = context.application.bot_data['flask_app'].config['ALLOWED_TELEGRAM_USER_IDS']
    if user is None or user.id not in allowed:
        logger.info('Access denied user_id=%s', getattr(user, 'id', None))
        if update.callback_query:
            await update.callback_query.answer('Accès non autorisé.', show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text('Accès non autorisé.')
        return False
    if update.effective_chat is None or update.effective_chat.type != 'private':
        if update.callback_query:
            await update.callback_query.answer('Utilisez ce bot en conversation privée.', show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text('Utilisez ce bot en conversation privée.')
        return False
    return True


async def start(update, context):
    if await authorized(update, context):
        logger.info('User action user_id=%s action=start', update.effective_user.id)
        set_state(context, UIState.MAIN_MENU)
        await update.effective_message.reply_text('Choisissez un radar :', reply_markup=main_keyboard())


async def on_callback(update, context):
    from app.bot.state import active_context
    user = update.effective_user
    query = update.callback_query
    key = (getattr(user, 'id', None), getattr(query, 'data', None))
    running = context.application.bot_data.setdefault('callback_inflight', set())
    if key in running:
        if await authorized(update, context):
            await query.answer('Action déjà prise en compte.')
        return
    running.add(key)
    begin_transition(context)
    token = active_context.set(context)
    try:
        await _handle_callback(update, context)
    finally:
        active_context.reset(token)
        running.discard(key)
        end_transition(context)


async def _handle_callback(update, context):
    if not await authorized(update, context):
        return
    query = update.callback_query
    if _duplicate_callback(update, context):
        await query.answer('Action déjà prise en compte.')
        return
    data = query.data if isinstance(query.data, str) else ''
    for prefix, (module_path, parse_name, handle_name) in PREFIX_HANDLERS.items():
        if data.startswith(prefix):
            parse = _import_attr(module_path, parse_name)
            handle = _import_attr(module_path, handle_name)
            try:
                parsed = parse(data)
            except ValueError:
                await query.answer('Cette action n’est plus disponible.', show_alert=True)
                return
            await handle(update, context, parsed)
            return
    try:
        action, code = parse_callback(query.data)
    except ValueError:
        await query.answer('Action invalide. Utilisez /start.', show_alert=True)
        return
    await query.answer()
    if code in COMPLETION_LABELS and action in {'pending', 'approved', 'rejected', 'runs'}:
        module_path, show_name = QUEUE_SHOW[code]
        show_page = _import_attr(module_path, show_name)
        set_state(context, UIState.RADAR_QUEUE, code=code, mode=action)
        await show_page(query.message, context.application.bot_data['flask_app'], action, 0, context)
        return
    logger.info('User action user_id=%s action=%s radar=%s', update.effective_user.id, action, code)
    if action == 'menu':
        await cleanup_queue_view(context, query.message)
        set_state(context, UIState.MAIN_MENU)
        text, keyboard = 'Choisissez un radar :', main_keyboard()
    else:
        definition = RADARS[code]
        keyboard = radar_keyboard(code)
        if action == 'radar':
            # Leaving a queue: drop result slots; reuse this nav/menu message for the radar menu.
            await cleanup_queue_view(context, query.message, keep_navigation=True)
            logger.info('Radar selected radar=%s agent=%s', code, type(definition).__name__)
            set_state(context, UIState.RADAR_MENU, code=code)
            text = f'Radar {definition.number} — {definition.name}'
        elif action == 'search':
            await launch_search(update, context, code, definition.number)
            return
        else:
            try:
                text = await asyncio.to_thread(radar_action, context.application.bot_data['flask_app'], code, action)
            except RadarServiceError as error:
                text = str(error)
            await query.message.reply_text(text, reply_markup=keyboard)
            return
    try:
        await query.edit_message_text(text, reply_markup=keyboard)
    except BadRequest as error:
        if 'message is not modified' not in str(error).lower():
            raise


async def fallback(update, context):
    if not await authorized(update, context):
        return
    message = update.effective_message
    if expects_text(context):
        from app.bot.handlers.targeted import handle_text
        text = (message.text or '').strip() if message else ''
        if not text:
            await message.reply_text('Merci d’envoyer une description textuelle de la recherche.')
            await message.reply_text('Décris ce que tu veux rechercher.')
            return
        if await handle_text(update, context):
            return
    await redisplay_current(update, context)


async def on_error(update, context):
    log_failure(logger, 'Telegram update handling', context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text('Service temporairement indisponible. Réessayez plus tard.')
        except TelegramError as error:
            log_failure(logger, 'Telegram error notification', error)
