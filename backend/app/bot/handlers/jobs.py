import asyncio
import logging

from telegram.error import TelegramError
from sqlalchemy.exc import SQLAlchemyError

from app.core.agent_errors import ActiveRunError, AgentError
from app.core.agent_schemas import RunStatus
from app.bot.keyboards.main import radar_completion_keyboard, radar_failure_keyboard
from app.bot.state import UIState, set_state
from app.core.agent_job_service import launch_radar
from app.core.logging import log_failure

logger = logging.getLogger(__name__)

ACTIVE_RUN_MESSAGE = '⏳ Une recherche est déjà en cours.'
FAILED_MESSAGE = '❌ La recherche n’a pas pu être terminée.'


async def launch_search(update, context, code, number):
    data = context.application.bot_data
    message = update.callback_query.message
    try:
        ticket = await asyncio.to_thread(launch_radar, data['flask_app'], data['job_runner'], code, update.effective_user.id)
    except ActiveRunError:
        await message.reply_text(ACTIVE_RUN_MESSAGE)
        return
    except AgentError as error:
        await message.reply_text(str(error))
        return
    except SQLAlchemyError as error:
        log_failure(logger, 'Search reservation database', error)
        await message.reply_text('❌ Impossible de créer la recherche. Base de données temporairement indisponible.')
        return
    set_state(context, UIState.RADAR_RUNNING, code=code)
    try:
        await message.reply_text(f'🔄 Radar {number} lancé...')
    except TelegramError as error:
        log_failure(logger, f'run_id={ticket.run_id} Telegram launch notification', error)
    context.application.create_task(notify_when_finished(
        ticket, message, code, number, data['flask_app'], context))


def _completion_text(summary, ticket, code, number):
    health = (summary.run_metadata or {}).get('collector_health')
    partial = health in {'PARTIAL', 'DEGRADED'}
    if code == 'RADAR_1_MARKETS':
        body = (f'Nouveaux : {summary.new_results_count}\n'
                f'Mis à jour : {summary.updated_results_count}\nDéjà connus : {summary.duplicate_count}\n'
                f'Rejetés automatiquement : {summary.rejected_count}\n\n'
                f'📥 À traiter : {summary.manual_review_count}')
        if partial or health == 'FAILED':
            return f'⚠️ Radar {number} terminé partiellement\n{body}'
        if health == 'HEALTHY' and not summary.new_results_count and not summary.updated_results_count and not summary.duplicate_count:
            return f'✅ Recherche terminée — aucun résultat pertinent\n{body}'
        return f'✅ Radar {number} terminé\n{body}'
    body = (f'Nouveaux résultats : {summary.new_results_count}\n'
            f'Mis à jour : {summary.updated_results_count}\nDoublons ignorés : {summary.duplicate_count}\n'
            f'À vérifier manuellement : {summary.manual_review_count}\nRejetés : {summary.rejected_count}\n'
            'Les résultats sont enregistrés dans la base.')
    if summary.candidate_errors_count:
        body += f'\nCandidats invalides ignorés : {summary.candidate_errors_count}'
    if partial:
        return f'⚠️ Radar {number} terminé partiellement\n{body}'
    return f'✅ Radar {number} terminé\n{body}'


async def notify_when_finished(ticket, message, code, number, app=None, context=None):
    completed = False
    failed = False
    try:
        summary = await asyncio.wrap_future(ticket.future)
        completed = summary.status == RunStatus.COMPLETED
        if not completed:
            failed = True
            text = FAILED_MESSAGE
        else:
            text = _completion_text(summary, ticket, code, number)
            if text is None:
                completed, failed = False, True
                text = FAILED_MESSAGE
    except Exception as error:
        log_failure(logger, f'run_id={ticket.run_id} job completion', error)
        failed = True
        text = FAILED_MESSAGE
    try:
        if completed:
            from app.core.review import run_actionable_count
            actionable = (await asyncio.to_thread(run_actionable_count, app, ticket.run_id, code)
                          if app is not None else summary.manual_review_count)
            keyboard = radar_completion_keyboard(code, ticket.run_id, actionable > 0)
            if context is not None:
                set_state(context, UIState.RADAR_COMPLETION, code=code, run_id=ticket.run_id,
                          has_pending=actionable > 0)
        else:
            keyboard = radar_failure_keyboard(code)
            if context is not None:
                set_state(context, UIState.RADAR_MENU, code=code)
        await message.reply_text(text, reply_markup=keyboard)
    except TelegramError as error:
        log_failure(logger, f'run_id={ticket.run_id} Telegram completion notification', error)
