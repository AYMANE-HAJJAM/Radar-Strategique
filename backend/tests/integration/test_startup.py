import asyncio
from unittest.mock import MagicMock, patch

from backend.app import create_app


def test_flask_factory_imports_without_network(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@localhost/test')
    monkeypatch.setenv('ALLOWED_TELEGRAM_USER_IDS', '')
    monkeypatch.setenv('FLASK_ENV', 'development')
    app = create_app()
    with patch('app.core.internal_api.database_available', return_value=True):
        response = app.test_client().get('/api/health')
    assert response.json['phase'] == 2 and response.json['status'] == 'ok'


def test_bot_entry_point_supplies_event_loop(app):
    import backend.run_bot as run_bot

    application = MagicMock()

    def check_loop(**kwargs):
        assert not asyncio.get_event_loop().is_closed()
        assert kwargs['allowed_updates'] == ['message', 'callback_query']

    application.run_polling.side_effect = check_loop
    with patch.object(run_bot, 'create_app', return_value=app), patch.object(
        run_bot, 'build_application', return_value=application
    ):
        run_bot.main()
    application.run_polling.assert_called_once()
