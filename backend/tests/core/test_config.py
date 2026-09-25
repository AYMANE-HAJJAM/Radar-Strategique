import pytest

from backend.app import create_app
from backend.app.config import load_config


@pytest.mark.parametrize('value', ['abc', '123,bad', '-1', '0'])
def test_invalid_allowlist_fails_closed(monkeypatch, value):
    monkeypatch.setenv('ALLOWED_TELEGRAM_USER_IDS', value)
    with pytest.raises(ValueError, match='positive integers'):
        load_config()


def test_empty_allowlist_and_postgres_url(monkeypatch):
    monkeypatch.setenv('ALLOWED_TELEGRAM_USER_IDS', '')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:password@localhost/db')
    config = load_config()
    assert config['ALLOWED_TELEGRAM_USER_IDS'] == frozenset()
    assert config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://')


def test_app_import_and_production_configuration(monkeypatch):
    monkeypatch.setenv('ALLOWED_TELEGRAM_USER_IDS', '')
    with pytest.raises(ValueError, match='SECRET_KEY'):
        create_app({'FLASK_ENV': 'production', 'SECRET_KEY': '',
                    'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://user:password@localhost/db'})
