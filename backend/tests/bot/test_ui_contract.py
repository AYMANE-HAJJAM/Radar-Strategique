"""Contract regression: stray messages and completion keyboard UX."""
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.core.agent_schemas import RunSummary, RunStatus, Stage
from backend.app.bot.handlers.common import fallback, start, on_callback
from backend.app.bot.handlers.jobs import notify_when_finished
from backend.app.bot.keyboards.main import COMPLETION_LABELS, radar_keyboard
from backend.app.bot.state import UIState, set_state
from backend.app.core.agent_job_service import JobTicket
from backend.tests.bot.test_bot import fixture_update


async def test_start_sets_main_menu_and_stray_text_redisplays(app):
    update, context = fixture_update(app)
    await start(update, context)
    update.effective_message.reply_text.reset_mock()
    update.effective_message.text = 'bonjour'
    await fallback(update, context)
    assert 'Choisissez un radar' in update.effective_message.reply_text.call_args.args[0]


async def test_radar_menu_stray_text_and_photo_redisplay(app):
    update, context = fixture_update(app, data='radar:RADAR_2_PROJECTS')
    await on_callback(update, context)
    update.effective_message.reply_text.reset_mock()
    update.effective_message.text = 'test'
    await fallback(update, context)
    assert 'Radar 2' in update.effective_message.reply_text.call_args.args[0]
    assert update.effective_message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard[0][0].text.startswith('🔎')
    update.effective_message.reply_text.reset_mock()
    update.effective_message.text = None
    update.effective_message.photo = [object()]
    await fallback(update, context)
    assert 'Radar 2' in update.effective_message.reply_text.call_args.args[0]


async def test_completion_stray_text_redisplays_options(app):
    update, context = fixture_update(app)
    set_state(context, UIState.RADAR_COMPLETION, code='RADAR_1_MARKETS', run_id=9, has_pending=True)
    update.effective_message.text = 'hello'
    await fallback(update, context)
    labels = [b.text for row in update.effective_message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
    assert labels == ['📥 Voir les offres', '⬅️ Retour']


async def test_targeted_input_rejects_non_text(app):
    update, context = fixture_update(app)
    context.user_data['targeted_input'] = {'action': 'new'}
    set_state(context, UIState.TARGETED_INPUT)
    update.effective_message.text = None
    update.effective_message.sticker = object()
    await fallback(update, context)
    texts = [call.args[0] for call in update.effective_message.reply_text.await_args_list]
    assert any('description textuelle' in text for text in texts)
    assert context.user_data.get('targeted_input') == {'action': 'new'}


@pytest.mark.parametrize('code', COMPLETION_LABELS)
async def test_completion_keyboard_never_includes_history(code):
    future = Future()
    future.set_result(RunSummary(id=3, radar_code=code, status=RunStatus.COMPLETED,
                                 current_stage=Stage.COMPLETED, manual_review_count=2))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(3, future), message, code, 1)
    labels = [b.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
    assert '🕘 Recherches précédentes' not in labels
    assert labels == [COMPLETION_LABELS[code], '⬅️ Retour']
    menu_labels = [row[0].text for row in radar_keyboard(code).inline_keyboard]
    assert '🕘 Recherches précédentes' in menu_labels
