"""Explicit per-user UI session state for stray-message fallback and navigation."""
from enum import StrEnum

from app.bot.keyboards.main import main_keyboard, radar_keyboard, radar_completion_keyboard, COMPLETION_LABELS


class UIState(StrEnum):
    MAIN_MENU = 'MAIN_MENU'
    RADAR_MENU = 'RADAR_MENU'
    RADAR_RUNNING = 'RADAR_RUNNING'
    RADAR_COMPLETION = 'RADAR_COMPLETION'
    RADAR_QUEUE = 'RADAR_QUEUE'
    RADAR_DETAILS = 'RADAR_DETAILS'
    TARGETED_MENU = 'TARGETED_MENU'
    TARGETED_INPUT = 'TARGETED_INPUT'
    TARGETED_CONFIRMATION = 'TARGETED_CONFIRMATION'
    TARGETED_RESULTS = 'TARGETED_RESULTS'
    TARGETED_REFINEMENT_INPUT = 'TARGETED_REFINEMENT_INPUT'


STATE_KEY = 'ui_state'


def get_state(context):
    return context.user_data.get(STATE_KEY) or {'name': UIState.MAIN_MENU}


def set_state(context, name, **payload):
    if context is None or not hasattr(context, 'user_data') or context.user_data is None:
        return
    previous = context.user_data.get(STATE_KEY) or {}
    version = int(previous.get('version', 0)) + 1
    context.user_data[STATE_KEY] = {'name': str(name), 'version': version, **payload}


def begin_transition(context):
    """Mark an interaction in progress; used with inflight callback guarding."""
    if context is None or not hasattr(context, 'user_data'):
        return 0
    state = get_state(context)
    version = int(state.get('version', 0)) + 1
    state = {**state, 'version': version, 'transition': True}
    context.user_data[STATE_KEY] = state
    return version


def end_transition(context):
    if context is None or not hasattr(context, 'user_data'):
        return
    state = get_state(context)
    state = {**state, 'transition': False}
    context.user_data[STATE_KEY] = state


def expects_text(context):
    name = get_state(context).get('name')
    return name in {UIState.TARGETED_INPUT, UIState.TARGETED_REFINEMENT_INPUT} or bool(
        context.user_data.get('targeted_input'))


async def redisplay_current(update, context):
    """Re-render the user's current options without changing state (stray input)."""
    message = update.effective_message
    state = get_state(context)
    name = state.get('name', UIState.MAIN_MENU)
    if name == UIState.RADAR_MENU and state.get('code') in COMPLETION_LABELS:
        code = state['code']
        from app.core.radar_registry import RADARS
        radar = RADARS[code]
        await message.reply_text(f'Radar {radar.number} — {radar.name}', reply_markup=radar_keyboard(code))
        return
    if name == UIState.RADAR_COMPLETION and state.get('code') in COMPLETION_LABELS:
        code = state['code']
        await message.reply_text(
            'Options de la recherche terminée :',
            reply_markup=radar_completion_keyboard(code, state.get('run_id'), bool(state.get('has_pending'))))
        return
    if name in {UIState.TARGETED_MENU, UIState.TARGETED_CONFIRMATION, UIState.TARGETED_RESULTS,
                UIState.TARGETED_INPUT, UIState.TARGETED_REFINEMENT_INPUT}:
        from app.bot.handlers.targeted import menu
        if name == UIState.TARGETED_RESULTS:
            from app.bot.queue_view import get_queue_view
            from app.bot.handlers.targeted import show_results
            view = get_queue_view(context)
            session_id = state.get('session_id') or (view or {}).get('session_id')
            if session_id is not None and view and str(view.get('view_key', '')).startswith('targeted:'):
                mode = (view.get('mode') or 'PENDING')
                await show_results(
                    message, context.application.bot_data['flask_app'],
                    session_id, int(view.get('page') or 0), mode)
                return
        if name == UIState.TARGETED_CONFIRMATION and state.get('session_id') is not None:
            from app.bot.handlers.targeted import interpretation
            from app.modules.targeted_search.service import TargetedSearchService
            current = TargetedSearchService().get(context.application.bot_data['flask_app'], state['session_id'])
            if current:
                text, keys = interpretation(state['session_id'], current['version'], current['brief'])
                await message.reply_text(text, reply_markup=keys)
                return
        await message.reply_text('🎯 Recherche ciblée', reply_markup=menu())
        return
    if name in {UIState.RADAR_QUEUE, UIState.RADAR_DETAILS}:
        from app.bot.queue_view import get_queue_view
        view = get_queue_view(context)
        code = state.get('code') or (view or {}).get('code')
        if code in COMPLETION_LABELS and view:
            queue_modules = {
                'RADAR_1_MARKETS': 'app.bot.handlers.markets',
                'RADAR_2_PROJECTS': 'app.bot.handlers.projects',
                'RADAR_3_INSTITUTIONS': 'app.bot.handlers.institutions',
                'RADAR_4_POLICIES': 'app.bot.handlers.policies',
                'RADAR_5_FUNDING': 'app.bot.handlers.funding',
            }
            module = __import__(queue_modules[code], fromlist=['show_page'])
            mode = view.get('mode') or state.get('mode') or 'pending'
            page = int(view.get('page') or 0)
            await module.show_page(
                message, context.application.bot_data['flask_app'], mode, page, context)
            return
        if code in COMPLETION_LABELS:
            from app.core.radar_registry import RADARS
            radar = RADARS[code]
            await message.reply_text(f'Radar {radar.number} — {radar.name}', reply_markup=radar_keyboard(code))
            return
    if name == UIState.RADAR_RUNNING:
        code = state.get('code')
        if code in COMPLETION_LABELS:
            from app.core.radar_registry import RADARS
            radar = RADARS[code]
            await message.reply_text(f'Radar {radar.number} — {radar.name}', reply_markup=radar_keyboard(code))
            return
    await message.reply_text('Choisissez un radar :', reply_markup=main_keyboard())


"""Reuse each user's queue view without altering card content or business callbacks."""
import asyncio
from contextvars import ContextVar
from functools import wraps
from telegram.error import TelegramError
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup

active_context = ContextVar('radar_callback_context', default=None)


class TrackedMessage:
    def __init__(self, message, context, key):
        self.message, self.context, self.key = message, context, key

    def __getattr__(self, name):
        return getattr(self.message, name)

    async def reply_text(self, *args, **kwargs):
        sent = await self.message.reply_text(*args, **kwargs)
        if getattr(sent, 'message_id', None) is not None:
            self.context.user_data.setdefault(self.key, []).append(sent.message_id)
        return sent


async def replace_view(message, context, key):
    previous = context.user_data.pop(key, [])
    chat_id = getattr(message, 'chat_id', None) or getattr(getattr(message, 'chat', None), 'id', None)
    for message_id in previous:
        try:
            await context.application.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError:
            pass
    return TrackedMessage(message, context, key)


def replace_queue(function):
    @wraps(function)
    async def wrapped(message, *args, **kwargs):
        context = active_context.get()
        if context is not None:
            message = await replace_view(message, context, function.__module__ + ':queue')
            await replace_view(message, context, function.__module__ + ':details')
        return await function(message, *args, **kwargs)
    return wrapped


async def show_details(query, context, module, prefix, mode, index, text, url):
    """Edit the clicked result card into details (same message slot)."""
    from app.bot.queue_view import show_inline_details
    buttons = [[Button('🔗 Ouvrir', url=url)]] if url else []
    buttons.append([Button('⬅️ Retour', callback_data=f'{prefix}:{mode}:{index}')])
    # module retained for call-site compatibility; details no longer use a separate tracked list.
    _ = module
    await show_inline_details(
        query, context, text=text, reply_markup=Markup(buttons), parse_mode=None,
        disable_web_page_preview=True)


async def clamped_page(loader, index):
    """Load a zero-based page and retry at the last valid page if the queue shrank."""
    items, more, total = await asyncio.to_thread(loader, index)
    effective = min(index, max(0, total - 1))
    if effective != index:
        items, more, total = await asyncio.to_thread(loader, effective)
    return items, more, total, effective


def pagination_rows(prefix, mode, index, more, radar_code):
    navigation = []
    if index > 0:
        navigation.append(Button('⬅️ Précédent', callback_data=f'{prefix}:{mode}:{index-1}'))
    if more:
        navigation.append(Button('➡️ Suivant', callback_data=f'{prefix}:{mode}:{index+1}'))
    rows = [navigation] if navigation else []
    rows.append([Button('⬅️ Retour', callback_data=f'radar:{radar_code}')])
    return rows


def pagination_label(items, index, total, empty_message='Aucun résultat.'):
    return f'Page {index+1}/{total}' if items else empty_message
