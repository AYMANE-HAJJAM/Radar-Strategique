"""Shared compact review queue for Radars 2–5 (global backlog + exact-run via run_queue)."""
import asyncio
import re
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from app.bot.handlers import run_queue
from app.bot.queue_view import render_queue_slots
from app.bot.state import UIState, set_state
from app.bot.state import clamped_page, pagination_label, pagination_rows, show_details
from app.core.constants import MAX_PAGE_INDEX, PAGE_SIZE
from app.core.review import page, detail, decide, run_page

UNAVAILABLE = 'Cette action n’est plus disponible.'


def make_parser(prefix):
    def parse(data):
        parsed = run_queue.parse(data, prefix)
        if parsed:
            return parsed
        match = re.fullmatch(fr'{prefix}:(pending|approved|rejected|runs):(\d{{1,5}})', data)
        if match and int(match[2]) <= MAX_PAGE_INDEX:
            return match[1], int(match[2]), None, None
        match = re.fullmatch(fr'{prefix}:details:(pending|approved|rejected):(\d{{1,12}}):(\d{{1,5}})', data)
        if match and int(match[3]) <= MAX_PAGE_INDEX:
            return 'details_' + match[1], int(match[3]), int(match[2]), None
        match = re.fullmatch(fr'{prefix}:(approve|reject):(\d{{1,12}}):([a-f0-9]{{12}}):(\d{{1,5}})', data)
        if match and int(match[4]) <= MAX_PAGE_INDEX:
            return match[1], int(match[4]), int(match[2]), match[3]
        raise ValueError('Action invalide.')
    return parse


def item_keyboard(prefix, item, mode, index):
    first = ([Button('🔗 Ouvrir', url=item['url'])] if item.get('url') else [])
    first.append(Button('ℹ️ Détails', callback_data=f'{prefix}:details:{mode}:{item["id"]}:{index}'))
    rows = [first]
    if mode == 'pending' and item.get('version'):
        rows.append([
            Button('✅ Valider', callback_data=f'{prefix}:approve:{item["id"]}:{item["version"]}:{index}'),
            Button('❌ Rejeter', callback_data=f'{prefix}:reject:{item["id"]}:{item["version"]}:{index}'),
        ])
    return Markup(rows)


def default_run_line(number, run):
    return (f'{run["started_at"]:%d/%m/%Y — %H:%M}\nRadar {number}\nTrouvés : {run["found"]}\n'
            f'Nouveaux : {run["new"]}\nMis à jour : {run["updated"]}')


def build_handlers(code, prefix, number, card_fn, details_fn, module_name, format_run=None):
    parse = make_parser(prefix)
    format_run = format_run or (lambda run: default_run_line(number, run))
    view_key = module_name

    async def show_page(message, app, mode, index, context=None):
        if mode == 'runs':
            runs, more, total, index = await clamped_page(lambda i: run_page(app, i, code), index)
            slots = []
            if runs:
                slots.append({'text': '\n\n'.join(format_run(run) for run in runs), 'reply_markup': None})
            nav_text = pagination_label(runs, index, total, 'Aucune recherche.')
            if context is not None:
                set_state(context, UIState.RADAR_QUEUE, code=code, mode='runs')
            await render_queue_slots(
                message, context, view_key=view_key, code=code, mode='runs', page=index,
                slots=slots, nav_text=nav_text,
                nav_markup=Markup(pagination_rows(prefix, mode, index, more, code)),
                parse_mode=None, disable_web_page_preview=False)
            return

        cards, more, total, index = await clamped_page(
            lambda i: page(app, mode, i, include_total=True, code=code), index)
        slots = [
            {'text': card_fn(item, n), 'reply_markup': item_keyboard(prefix, item, mode, index)}
            for n, item in enumerate(cards, index * PAGE_SIZE + 1)
        ]
        if context is not None:
            set_state(context, UIState.RADAR_QUEUE, code=code, mode=mode)
        await render_queue_slots(
            message, context, view_key=view_key, code=code, mode=mode, page=index,
            slots=slots, nav_text=pagination_label(cards, index, total),
            nav_markup=Markup(pagination_rows(prefix, mode, index, more, code)),
            parse_mode=None, disable_web_page_preview=True)

    async def handle(update, context, parsed):
        action, index, result_id, version = parsed
        query, app = update.callback_query, context.application.bot_data['flask_app']
        if action.startswith('run_'):
            await run_queue.handle(update, context, parsed, code, prefix, module_name, card_fn, details_fn)
            set_state(context, UIState.RADAR_QUEUE, code=code, mode='run')
            return
        if action in {'approve', 'reject'}:
            await query.answer()
            try:
                await asyncio.to_thread(
                    decide, app, result_id, version,
                    'approved' if action == 'approve' else 'rejected',
                    update.effective_user.id, code)
            except ValueError:
                await query.message.reply_text(UNAVAILABLE)
                return
            await show_page(query.message, app, 'pending', index, context)
            return
        if action.startswith('details_'):
            await query.answer()
            item = await asyncio.to_thread(detail, app, result_id, code)
            if not item:
                await query.message.reply_text(UNAVAILABLE)
                return
            set_state(context, UIState.RADAR_DETAILS, code=code, mode=action.removeprefix('details_'))
            await show_details(query, context, module_name, prefix, action.removeprefix('details_'),
                               index, details_fn(item), item.get('url'))
            return
        await query.answer()
        await show_page(query.message, app, action, index, context)

    return parse, show_page, handle
