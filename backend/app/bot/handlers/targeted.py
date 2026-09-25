"""Compact Telegram workflow for persistent, versioned targeted searches."""
import asyncio,re
from telegram import InlineKeyboardButton as Button,InlineKeyboardMarkup as Markup
import logging
from app.bot.queue_view import render_queue_slots
from app.bot.state import pagination_rows, show_details
from app.core.constants import MAX_PAGE_INDEX, PAGE_SIZE
from app.modules.targeted_search.service import (ActiveTargetedRunError, StaleBriefError,
                                                   TargetedSearchService)
from app.bot.presenters.result_presenter import amount_label, date_label
from app.core.logging import log_failure

logger = logging.getLogger(__name__)
service = TargetedSearchService()


def parse_callback(data):
    patterns = (
        (r't:(menu|new|history|pendingall)', lambda m: (m[1], None, None, None)),
        (r't:(confirm|modify|cancel|results|refine|continue|open):(\d{1,12}):(\d{1,6})',
         lambda m: (m[1], int(m[2]), int(m[3]), None)),
        (r't:(pending|pertinent|rejected):(\d{1,12}):(\d{1,5})',
         lambda m: (m[1], int(m[2]), int(m[3]), None)),
        (r't:details:(\d{1,12}):(\d{1,12}):(\d{1,5})',
         lambda m: ('details', int(m[1]), int(m[3]), int(m[2]))),
        (r't:(accept|reject):(\d{1,12}):(\d{1,12}):(\d{1,5})',
         lambda m: (m[1], int(m[2]), int(m[4]), int(m[3]))),
    )
    for pattern, convert in patterns:
        match = re.fullmatch(pattern, data)
        if match:
            parsed = convert(match)
            if parsed[2] is not None and parsed[2] > MAX_PAGE_INDEX:
                break
            return parsed
    raise ValueError('Action ciblée invalide.')


def menu():
    return Markup([[Button('➕ Nouvelle recherche',callback_data='t:new')],
        [Button('📥 À traiter',callback_data='t:pendingall')],[Button('🕘 Recherches précédentes',callback_data='t:history')],
        [Button('⬅️ Retour',callback_data='menu')]])


def interpretation(session_id,version,brief):
    text=('🔎 Recherche comprise\n\n'+f'Sujet : {", ".join(brief["topics"])}\n'
          f'Zone : {", ".join(brief["geography"]) or "Non précisée"}\nType : {brief["search_mode"]}\n'
          f'Documents : {", ".join(brief["document_requirements"]) or "Aucun imposé"}\n'
          f'Période : {brief.get("date_from") or "défaut du type"} → {brief.get("date_to") or "maintenant"}')
    if brief.get('ambiguities'):
        text+='\n\n❓ '+brief['ambiguities'][0]
    rows=[] if brief.get('ambiguities') else [[Button('✅ Lancer la recherche',callback_data=f't:confirm:{session_id}:{version}')]]
    keys=Markup(rows+[[Button('✏️ Modifier',callback_data=f't:modify:{session_id}:{version}')],
        [Button('❌ Annuler',callback_data=f't:cancel:{session_id}:{version}')]])
    return text,keys


async def show_results(message, app, session_id, index, mode='PENDING', context=None):
    cards, more, total, index = await asyncio.to_thread(service.result_page, app, session_id, index, mode)
    slots = []
    for number, item in enumerate(cards, index * PAGE_SIZE + 1):
        badge = {'NEW': '🆕 Nouveau', 'KNOWN': f'♻️ Déjà connu — {item["origin"]}',
                 'UPDATED': '🟡 Mis à jour'}[item['match_status']]
        lines = [f'[{number}] {item["title"]}', badge]
        if item.get('reference'):
            lines.append(f'📄 Réf : {item["reference"]}')
        if item.get('institution'):
            lines.append(f'🏛️ {item["institution"]}')
        estimate = amount_label(item.get('estimated_amount'), item.get('estimated_currency'),
                                item.get('estimated_amount_tax_mode'))
        if estimate:
            lines.append(f'💰 Estimation : {estimate}' + (
                '' if item.get('estimated_amount_verified') else ' — à confirmer'))
        publication = date_label(item.get('publication'))
        if publication:
            lines.append(f'📅 Publication : {publication}')
        deadline = date_label(item.get('deadline'))
        if deadline:
            lines.append(f'⏳ Échéance : {deadline}' + (
                f' à {item["deadline_time"]}' if item.get('deadline_time') else ''))
        if item.get('dce_available'):
            access = ' — formulaire requis' if item.get('dce_access_mode') == 'FORM_REQUIRED' else ''
            documents = ', '.join(item.get('document_types') or ['DCE'])
            lines.append(f'📎 {documents} : disponible{access}')
        lines.append(f'🎯 Pertinence : {item["score"]}/100')
        buttons = [[Button('🔗 Ouvrir', url=item['url'])] if item['url'] else []]
        buttons[0].append(Button('ℹ️ Détails', callback_data=f't:details:{session_id}:{item["id"]}:{index}'))
        if mode == 'PENDING':
            buttons.append([
                Button('✅ Pertinent', callback_data=f't:accept:{session_id}:{item["id"]}:{index}'),
                Button('❌ Rejeter', callback_data=f't:reject:{session_id}:{item["id"]}:{index}'),
            ])
        slots.append({'text': '\n'.join(lines), 'reply_markup': Markup(buttons)})
    rows = pagination_rows('t', mode.lower() + f':{session_id}', index, more, 'TARGETED')
    rows[-1] = [Button('⬅️ Retour', callback_data=f't:open:{session_id}:0')]
    view = await render_queue_slots(
        message, context, view_key=f'targeted:{session_id}', code='TARGETED',
        mode=mode, page=index, slots=slots,
        nav_text=f'Page {index + 1}/{total}' if cards else 'Aucun résultat.',
        nav_markup=Markup(rows), parse_mode=None, disable_web_page_preview=True)
    if view is not None and context is not None:
        view['session_id'] = session_id
        context.user_data['queue_view'] = view


async def handle(update, context, parsed):
    from app.bot.state import UIState, set_state
    action, session_id, value, result_id = parsed
    query, app = update.callback_query, context.application.bot_data['flask_app']
    if action == 'menu':
        set_state(context, UIState.TARGETED_MENU)
        await query.answer()
        await query.edit_message_text('🎯 Recherche ciblée', reply_markup=menu())
        return
    if action == 'new':
        context.user_data['targeted_input'] = {'action': 'new'}
        set_state(context, UIState.TARGETED_INPUT)
        await query.answer()
        await query.message.reply_text('Décris ce que tu veux rechercher.')
        return
    if action == 'history':
        rows = await asyncio.to_thread(service.history, app)
        buttons = [[Button(f'{x["title"]} · v{x["version"]}', callback_data=f't:open:{x["id"]}:0')] for x in rows]
        buttons.append([Button('⬅️ Retour', callback_data='t:menu')])
        await query.answer()
        await query.message.reply_text('Recherches précédentes' if rows else 'Aucune recherche ciblée.', reply_markup=Markup(buttons))
        return
    if action == 'pendingall':
        rows = await asyncio.to_thread(service.pending_sessions, app)
        buttons = [[Button(f'{x["title"]} · {x["count"]}', callback_data=f't:pending:{x["id"]}:0')] for x in rows]
        buttons.append([Button('⬅️ Retour', callback_data='t:menu')])
        await query.answer()
        await query.message.reply_text('Résultats à traiter' if rows else 'Aucun résultat à traiter.', reply_markup=Markup(buttons))
        return
    current = await asyncio.to_thread(service.get, app, session_id)
    if not current:
        await query.answer('Recherche introuvable.', show_alert=True)
        return
    if action in {'modify', 'refine'}:
        context.user_data['targeted_input'] = {'action': 'refine', 'session_id': session_id}
        set_state(context, UIState.TARGETED_REFINEMENT_INPUT, session_id=session_id)
        await query.answer()
        await query.message.reply_text('Décris la modification à appliquer.')
        return
    if action == 'cancel':
        await query.answer()
        await asyncio.to_thread(service.cancel, app, session_id, value)
        set_state(context, UIState.TARGETED_MENU)
        await query.message.reply_text('Recherche annulée.', reply_markup=menu())
        return
    if action in {'confirm', 'continue'}:
        try:
            await asyncio.to_thread(service.reserve, app, session_id, value)
        except (StaleBriefError, ActiveTargetedRunError) as error:
            await query.answer(str(error), show_alert=True)
            return
        await query.answer()
        await query.message.reply_text('🔄 Recherche ciblée lancée…')
        context.application.create_task(_execute(app, query.message, session_id, value, context))
        return
    if action == 'open':
        text, keys = interpretation(session_id, current['version'], current['brief'])
        set_state(context, UIState.TARGETED_CONFIRMATION, session_id=session_id)
        await query.answer()
        await query.message.reply_text(text, reply_markup=keys)
        return
    if action in {'pending', 'pertinent', 'rejected'}:
        set_state(context, UIState.TARGETED_RESULTS, session_id=session_id)
        await query.answer()
        await show_results(query.message, app, session_id, value, action.upper(), context)
        return
    if action == 'details':
        item = await asyncio.to_thread(service.result_detail, app, session_id, result_id)
        if not item:
            await query.answer('Résultat indisponible.')
            return
        fields = (('title', 'Objet'), ('reference', 'Référence'), ('institution', 'Acheteur'),
                  ('estimated_amount', 'Estimation'), ('publication', 'Publication'), ('deadline', 'Échéance'),
                  ('procedure_type', 'Procédure'), ('document_types', 'Documents'),
                  ('dce_access_mode', 'Accès DCE'), ('status', 'Statut'), ('score', 'Pertinence'), ('reason', 'Motif'))
        text = '\n'.join(f'{label} : {item[key]}' for key, label in fields if item.get(key))
        await show_details(query, context, __name__, 't', f'pending:{session_id}', value, text, item.get('url'))
        return
    if action in {'accept', 'reject'}:
        await asyncio.to_thread(service.feedback, app, session_id, result_id,
                                'PERTINENT' if action == 'accept' else 'REJECTED', update.effective_user.id)
        await query.answer()
        await show_results(query.message, app, session_id, value, context=context)
        return


async def _execute(app, message, session_id, version, context=None):
    from app.bot.state import UIState, set_state
    try:
        summary = await asyncio.to_thread(service.execute, app, session_id, version)
        text = ('✅ Recherche ciblée terminée\n\n' + f'Nouveaux : {summary["new"]}\nDéjà connus : {summary["known"]}\n'
                f'Mis à jour : {summary["updated"]}\nRejetés : {summary["rejected"]}\nÀ vérifier : {summary["pending"]}')
        if summary['pending']:
            rows = [
                [Button('📥 Voir les résultats', callback_data=f't:pending:{session_id}:0')],
                [Button('💬 Affiner la recherche', callback_data=f't:refine:{session_id}:{version}')],
                [Button('🔄 Continuer la recherche', callback_data=f't:continue:{session_id}:{version}')],
                [Button('🕘 Historique', callback_data='t:history')],
                [Button('⬅️ Retour', callback_data='t:menu')],
            ]
            await message.reply_text(text, reply_markup=Markup(rows))
            if context is not None:
                set_state(context, UIState.TARGETED_RESULTS, session_id=session_id)
        else:
            rows = [
                [Button('💬 Affiner', callback_data=f't:refine:{session_id}:{version}')],
                [Button('⬅️ Retour', callback_data='t:menu')],
            ]
            await message.reply_text(
                text + '\n\nAucun résultat correspondant au périmètre actuel.',
                reply_markup=Markup(rows))
            if context is not None:
                set_state(context, UIState.TARGETED_MENU, session_id=session_id)
    except Exception as error:
        log_failure(logger, f'targeted_search session_id={session_id}', error)
        await message.reply_text(
            '❌ La recherche ciblée a échoué. Tu peux modifier le brief ou réessayer.',
            reply_markup=menu())


async def handle_text(update, context):
    from app.bot.state import UIState, set_state
    state = context.user_data.pop('targeted_input', None)
    if not state:
        return False
    app = context.application.bot_data['flask_app']
    text = update.effective_message.text or ''
    try:
        if state['action'] == 'new':
            session_id, brief = await asyncio.to_thread(service.create, app, text, update.effective_user.id)
            version = 1
        else:
            session_id = state['session_id']
            version, brief = await asyncio.to_thread(service.refine, app, session_id, text, update.effective_user.id)
        rendered, keys = interpretation(session_id, version, brief)
        set_state(context, UIState.TARGETED_CONFIRMATION, session_id=session_id)
        await update.effective_message.reply_text(rendered, reply_markup=keys)
        return True
    except ValueError as error:
        context.user_data['targeted_input'] = state
        await update.effective_message.reply_text(str(error))
        return True
