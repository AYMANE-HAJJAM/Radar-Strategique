"""Shared exact-SearchRun Telegram queue for Radars 2–5."""
import asyncio
import re
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from app.bot.queue_view import render_queue_slots
from app.bot.state import clamped_page, pagination_label, pagination_rows, show_details
from app.core.constants import MAX_PAGE_INDEX, PAGE_SIZE
from app.core.review import run_result_page, detail, decide


def parse(data, prefix):
    match = re.fullmatch(fr'{prefix}:run:(\d{{1,12}}):(\d{{1,5}})', data)
    if match and int(match[2]) <= MAX_PAGE_INDEX:
        return 'run_' + match[1], int(match[2]), None, None
    match = re.fullmatch(fr'{prefix}:run_details:(\d{{1,12}}):(\d{{1,12}}):(\d{{1,5}})', data)
    if match and int(match[3]) <= MAX_PAGE_INDEX:
        return 'run_details_' + match[1], int(match[3]), int(match[2]), None
    match = re.fullmatch(fr'{prefix}:run_(approve|reject):(\d{{1,12}}):(\d{{1,12}}):([a-f0-9]{{12}}):(\d{{1,5}})', data)
    if match and int(match[5]) <= MAX_PAGE_INDEX:
        return 'run_' + match[1] + '_' + match[2], int(match[5]), int(match[3]), match[4]
    return None


def keyboard(prefix, run_id, item, index):
    first = ([Button('🔗 Ouvrir', url=item['url'])] if item.get('url') else [])
    first.append(Button('ℹ️ Détails', callback_data=f'{prefix}:run_details:{run_id}:{item["id"]}:{index}'))
    rows = [first]
    if item.get('version'):
        rows.append([
            Button('✅ Valider', callback_data=f'{prefix}:run_approve:{run_id}:{item["id"]}:{item["version"]}:{index}'),
            Button('❌ Rejeter', callback_data=f'{prefix}:run_reject:{run_id}:{item["id"]}:{item["version"]}:{index}'),
        ])
    return Markup(rows)


async def show_page(message, app, code, prefix, mode, index, card_formatter, context=None, module=None):
    run_id = int(mode.removeprefix('run_'))
    cards, more, total, index = await clamped_page(
        lambda i: run_result_page(app, run_id, i, include_total=True, code=code), index)
    slots = [
        {
            'text': card_formatter(item, number),
            'reply_markup': keyboard(prefix, run_id, item, index),
        }
        for number, item in enumerate(cards, index * PAGE_SIZE + 1)
    ]
    await render_queue_slots(
        message, context,
        view_key=(module or prefix),
        code=code,
        mode=mode,
        page=index,
        slots=slots,
        nav_text=pagination_label(cards, index, total, 'Aucun résultat.'),
        nav_markup=Markup(pagination_rows(prefix, f'run:{run_id}', index, more, code)),
        parse_mode=None,
        disable_web_page_preview=True,
    )


async def handle(update, context, parsed, code, prefix, module, card_formatter, details_formatter):
    action, index, result_id, version = parsed
    app, query = context.application.bot_data['flask_app'], update.callback_query
    decision = re.fullmatch(r'run_(approve|reject)_(\d+)', action)
    if decision:
        await query.answer()
        try:
            await asyncio.to_thread(
                decide, app, result_id, version,
                'approved' if decision[1] == 'approve' else 'rejected',
                update.effective_user.id, code, int(decision[2]))
        except ValueError:
            await query.message.reply_text('Cette action n’est plus disponible.')
            return
        await show_page(query.message, app, code, prefix, f'run_{decision[2]}', index,
                        card_formatter, context, module)
        return
    if action.startswith('run_details_'):
        await query.answer()
        run_id = int(action.removeprefix('run_details_'))
        item = await asyncio.to_thread(detail, app, result_id, code, run_id)
        if not item:
            await query.message.reply_text('Cette action n’est plus disponible.')
            return
        await show_details(query, context, module, prefix, f'run:{run_id}', index,
                           details_formatter(item), item.get('url'))
        return
    await query.answer()
    await show_page(query.message, app, code, prefix, action, index, card_formatter, context, module)
