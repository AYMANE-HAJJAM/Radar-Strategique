"""Radar 1 Telegram navigation; formatting lives in presenters."""
import asyncio
import re
from telegram import InlineKeyboardButton as Button, InlineKeyboardMarkup as Markup
from app.bot.handlers import run_queue
from app.bot.queue_view import render_queue_slots, show_inline_details
from app.core.constants import MAX_PAGE_INDEX, PAGE_SIZE
from app.core.review import page, detail, decide, run_page, run_result_page, CODE
from app.bot.presenters.result_presenter import format_result_card, format_result_details
from app.bot.state import UIState, clamped_page, pagination_label, pagination_rows, set_state

UNAVAILABLE = 'Cette action n’est plus disponible.'
VIEW_KEY = 'radar1'


def parse_market_callback(data):
    parsed = run_queue.parse(data, 'm')
    if parsed:
        return parsed
    match = re.fullmatch(r'm:(pending|approved|rejected|runs):(\d{1,5})', data)
    if match and int(match[2]) <= MAX_PAGE_INDEX:
        return match[1], int(match[2]), None, None
    match = re.fullmatch(r'm:details:(pending|approved|rejected):(\d{1,12}):(\d{1,5})', data)
    if match and int(match[3]) <= MAX_PAGE_INDEX:
        return 'details_' + match[1], int(match[3]), int(match[2]), None
    match = re.fullmatch(r'm:back:(pending|approved|rejected):(\d{1,5})', data)
    if match and int(match[2]) <= MAX_PAGE_INDEX:
        return 'back_' + match[1], int(match[2]), None, None
    match = re.fullmatch(r'm:(approve|reject):(\d{1,12}):([a-f0-9]{12}):(\d{1,5})', data)
    if match and int(match[4]) <= MAX_PAGE_INDEX:
        return match[1], int(match[4]), int(match[2]), match[3]
    raise ValueError('Action invalide.')


def result_keyboard(item, mode, index):
    first = [Button('🔗 Ouvrir la source' if item.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE'
                    else '🔗 Ouvrir l’offre', url=item['url'])] if item['url'] else []
    run_id = mode.removeprefix('run_') if mode.startswith('run_') else None
    details = (f'm:run_details:{run_id}:{item["id"]}:{index}' if run_id else
               f'm:details:{mode}:{item["id"]}:{index}')
    first.append(Button('ℹ️ Détails', callback_data=details))
    rows = [first]
    if (mode == 'pending' or run_id) and item['version']:
        prefix = f'm:run_{{}}:{run_id}:{item["id"]}:{item["version"]}:{index}' if run_id else None
        rows.append([Button('✅ Valider', callback_data=prefix.format('approve') if prefix else f'm:approve:{item["id"]}:{item["version"]}:{index}'),
                     Button('❌ Rejeter', callback_data=prefix.format('reject') if prefix else f'm:reject:{item["id"]}:{item["version"]}:{index}')])
    return Markup(rows)


async def show_page(message, app, mode, index, context=None):
    if context is not None:
        set_state(context, UIState.RADAR_QUEUE, code=CODE, mode=mode)

    if mode == 'runs':
        runs, more, total_pages, index = await clamped_page(lambda page_index: run_page(app, page_index), index)
        slots = []
        if runs:
            parts = []
            for run in runs:
                duration = ('en cours' if run['duration'] is None else
                            f'{run["duration"] // 60}m {run["duration"] % 60:02d}s')
                parts.append(f'{run["started_at"]:%d/%m/%Y — %H:%M}\nRadar 1\n'
                    f'Trouvés : {run["found"]}\nNouveaux : {run["new"]}\nMis à jour : {run["updated"]}\n'
                    f'Déjà connus : {run["known"]}\nRejetés automatiquement : {run["auto_rejected"]}\nDurée : {duration}')
            slots.append({'text': '\n\n'.join(parts), 'reply_markup': None})
        rows = pagination_rows('m', 'runs', index, more, CODE)
        await render_queue_slots(
            message, context, view_key=VIEW_KEY, code=CODE, mode=mode, page=index,
            slots=slots,
            nav_text=pagination_label(runs, index, total_pages, 'Aucune recherche pour le moment.'),
            nav_markup=Markup(rows), parse_mode=None, disable_web_page_preview=False)
        return

    run_id = int(mode.removeprefix('run_')) if mode.startswith('run_') else None
    cards, more, total_pages, index = await clamped_page(
        lambda page_index: run_result_page(app, run_id, page_index, include_total=True) if run_id else
        page(app, mode, page_index, include_total=True), index)
    seen_ids = set()
    slots = []
    for number, item in enumerate(cards, index * PAGE_SIZE + 1):
        if item['id'] in seen_ids:
            continue
        seen_ids.add(item['id'])
        slots.append({
            'text': format_result_card(item, number, 'pending' if run_id else mode),
            'reply_markup': result_keyboard(item, mode, index),
        })
    rows = pagination_rows('m', f'run:{run_id}' if run_id else mode, index, more, CODE)
    await render_queue_slots(
        message, context, view_key=VIEW_KEY, code=CODE, mode=mode, page=index,
        slots=slots,
        nav_text=pagination_label(cards, index, total_pages, 'Aucun résultat.'),
        nav_markup=Markup(rows), parse_mode=None, disable_web_page_preview=True)


async def handle(update, context, parsed):
    action, index, result_id, version = parsed
    app = context.application.bot_data['flask_app']
    query = update.callback_query
    run_match = re.fullmatch(r'run_(approve|reject)_(\d+)', action)
    if action in {'approve', 'reject'} or run_match:
        decision_action = run_match.group(1) if run_match else action
        await query.answer()
        try:
            await asyncio.to_thread(decide, app, result_id, version,
                'approved' if decision_action == 'approve' else 'rejected', update.effective_user.id,
                CODE, int(run_match.group(2)) if run_match else None)
        except ValueError:
            await query.message.reply_text(UNAVAILABLE)
            return
        await show_page(query.message, app, f'run_{run_match.group(2)}' if run_match else 'pending', index, context)
        return
    if action.startswith('details_') or action.startswith('run_details_'):
        await query.answer()
        run_id = int(action.removeprefix('run_details_')) if action.startswith('run_details_') else None
        item = await asyncio.to_thread(detail, app, result_id, CODE, run_id)
        if item is None:
            await query.message.reply_text(UNAVAILABLE)
            return
        mode = (f'run_{action.removeprefix("run_details_")}' if action.startswith('run_details_')
                else action.removeprefix('details_'))
        rows = [[Button('🔗 Ouvrir la source' if item.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE'
                        else '🔗 Ouvrir l’offre', url=item['url'])]] if item['url'] else []
        # Back restores the same card via in-place page refresh (preserves page index).
        rows.append([Button('⬅️ Retour', callback_data=(
            f'm:run:{mode.removeprefix("run_")}:{index}' if mode.startswith('run_')
            else f'm:back:{mode}:{index}'))])
        set_state(context, UIState.RADAR_DETAILS, code=CODE, mode=mode)
        await show_inline_details(
            query, context, text=format_result_details(item), reply_markup=Markup(rows),
            parse_mode=None, disable_web_page_preview=True)
        return
    if action.startswith('back_'):
        await query.answer()
        mode = action.removeprefix('back_')
        await show_page(query.message, app, mode, index, context)
        return
    await query.answer()
    await show_page(query.message, app, action, index, context)
