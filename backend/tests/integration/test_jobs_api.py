import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from backend.app.core.agent_errors import ActiveRunError
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.agent_schemas import RunSummary, RunStatus, Stage
from backend.app.bot.handlers.jobs import launch_search, notify_when_finished
from backend.app.core.agent_job_service import JobTicket, launch_radar
from backend.app.core.job_runner import LocalJobRunner

CODE = 'RADAR_1_MARKETS'
COMPLETION_LABELS = {
    'RADAR_1_MARKETS': '📥 Voir les offres',
    'RADAR_2_PROJECTS': '📥 Voir les projets',
    'RADAR_3_INSTITUTIONS': '📥 Voir les institutions',
    'RADAR_4_POLICIES': '📥 Voir les politiques',
    'RADAR_5_FUNDING': '📥 Voir les financements',
}


async def test_telegram_launch_returns_before_background_job_finishes(app):
    future = Future()
    pending = []
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(callback_query=SimpleNamespace(message=message), effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(application=SimpleNamespace(
        bot_data={'flask_app': app, 'job_runner': Mock()}, create_task=lambda coroutine: pending.append(coroutine)))
    with patch('app.bot.handlers.jobs.launch_radar', return_value=JobTicket(42, future)):
        await asyncio.wait_for(launch_search(update, context, CODE, 1), timeout=2)
    assert not future.done()
    message.reply_text.assert_awaited_once_with('🔄 Radar 1 lancé...')
    future.set_result(RunSummary(id=42, radar_code=CODE, status=RunStatus.COMPLETED, current_stage=Stage.COMPLETED))
    await pending[0]
    assert 'Nouveaux : 0' in message.reply_text.call_args.args[0]
    text = message.reply_text.call_args.args[0]
    assert 'Déjà connus :' in text and 'Rejetés automatiquement :' in text and '📥 À traiter :' in text
    labels = [button.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard for button in row]
    assert labels == ['⬅️ Retour']


@pytest.mark.parametrize('code,label', COMPLETION_LABELS.items())
async def test_all_radars_complete_with_direct_pending_cta(code, label):
    future = Future()
    future.set_result(RunSummary(id=42, radar_code=code, status=RunStatus.COMPLETED,
        current_stage=Stage.COMPLETED, new_results_count=1, updated_results_count=1,
        manual_review_count=2))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(42, future), message, code,
                               list(COMPLETION_LABELS).index(code) + 1)
    call = message.reply_text.call_args
    labels = [button.text for row in call.kwargs['reply_markup'].inline_keyboard for button in row]
    callbacks = [button.callback_data for row in call.kwargs['reply_markup'].inline_keyboard for button in row]
    assert labels == [label, '⬅️ Retour']
    prefix = {'RADAR_1_MARKETS': 'm', 'RADAR_2_PROJECTS': 'p', 'RADAR_3_INSTITUTIONS': 'i', 'RADAR_4_POLICIES': 'l', 'RADAR_5_FUNDING': 'f'}[code]
    assert callbacks == [f'{prefix}:run:42:0', f'radar:{code}']
    assert '🔎 Lancer une recherche' not in labels
    assert '🕘 Recherches précédentes' not in labels


@pytest.mark.parametrize('code', COMPLETION_LABELS)
async def test_zero_pending_completion_has_back_only(code):
    future = Future()
    future.set_result(RunSummary(id=42, radar_code=code, status=RunStatus.COMPLETED,
        current_stage=Stage.COMPLETED, manual_review_count=0))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(42, future), message, code,
                               list(COMPLETION_LABELS).index(code) + 1)
    rows = message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard
    assert [button.text for row in rows for button in row] == ['⬅️ Retour']
    assert [button.callback_data for row in rows for button in row] == [f'radar:{code}']


async def test_failed_search_offers_retry(code='RADAR_1_MARKETS'):
    future = Future()
    future.set_result(RunSummary(id=7, radar_code=code, status=RunStatus.FAILED, current_stage=Stage.FAILED))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(7, future), message, code, 1)
    assert message.reply_text.call_args.args[0] == '❌ La recherche n’a pas pu être terminée.'
    labels = [button.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard for button in row]
    assert labels == ['🔄 Réessayer', '⬅️ Retour']


async def test_telegram_active_run_and_failure_messages(app):
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(callback_query=SimpleNamespace(message=message), effective_user=SimpleNamespace(id=123))
    context = SimpleNamespace(application=SimpleNamespace(bot_data={'flask_app': app, 'job_runner': Mock()}))
    with patch('app.bot.handlers.jobs.launch_radar', side_effect=ActiveRunError()):
        await launch_search(update, context, CODE, 1)
    message.reply_text.assert_awaited_once_with('⏳ Une recherche est déjà en cours.')
    future = Future()
    future.set_result(RunSummary(id=7, radar_code=CODE, status=RunStatus.FAILED, current_stage=Stage.FAILED))
    await notify_when_finished(JobTicket(7, future), message, CODE, 1)
    assert message.reply_text.call_args.args[0] == '❌ La recherche n’a pas pu être terminée.'


def test_local_runner_executes_empty_agent(app):
    runner = LocalJobRunner()
    try:
        ticket = launch_radar(app, runner, CODE, 123)
        summary = ticket.future.result(timeout=5)
        assert summary.status == 'completed' and summary.new_results_count == 0 and summary.ai_calls == 0
    finally:
        runner.shutdown()


def test_submission_failure_releases_active_run(app):
    runner = Mock()
    runner.submit.side_effect = RuntimeError('queue unavailable')
    summary = launch_radar(app, runner, CODE, 123).future.result()
    assert summary.status == 'failed'
    assert AgentOrchestrator(app).run_radar(CODE).status == 'completed'


def test_internal_api_requires_separate_token_and_limits_output(app):
    client = app.test_client()
    assert client.get('/api/runs').status_code == 401
    app.config['INTERNAL_API_TOKEN'] = 'internal-test-token'
    headers = {'Authorization': 'Bearer internal-test-token'}
    assert client.get('/api/radars', headers=headers).status_code == 200
    summary = AgentOrchestrator(app).run_radar(CODE)
    response = client.get(f'/api/runs/{summary.id}', headers=headers)
    assert response.json['current_stage'] == 'COMPLETED'
    assert 'internal-test-token' not in response.get_data(as_text=True)
    assert client.get('/api/runs?limit=10000', headers=headers).json['limit'] == 100
    assert client.get('/api/runs?limit=bad', headers=headers).status_code == 400
    assert client.get('/api/runs/99999', headers=headers).status_code == 404
