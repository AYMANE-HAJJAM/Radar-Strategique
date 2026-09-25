from unittest.mock import Mock

import pytest

from backend.app.bot.handlers.jobs import launch_search
from backend.app.db.extensions import db
from backend.app.db.models import SearchRun
from backend.app.db.repositories.search_runs import SearchRunService
from test_bot import fixture_update


@pytest.mark.parametrize('setting,counter', [
    ('MAX_DAILY_SEARCH_CALLS', 'search_calls'),
    ('MAX_DAILY_AI_CALLS', 'ai_calls'),
])
async def test_exhausted_daily_cap_returns_message_without_submitting(app, setting, counter):
    code = 'RADAR_1_MARKETS'
    with app.app_context():
        previous = db.session.get(SearchRun, SearchRunService().reserve(code, 123))
        previous.status = 'completed'
        setattr(previous, counter, 1)
        db.session.commit()
    app.config[setting] = 1
    update, context = fixture_update(app, data='search:' + code)
    runner = Mock()
    context.application.bot_data['job_runner'] = runner
    await launch_search(update, context, code, 1)
    runner.submit.assert_not_called()
    assert 'quotidienne' in update.effective_message.reply_text.call_args.args[0]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(SearchRun)) == 1
