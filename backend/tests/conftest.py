import sys
from pathlib import Path

import pytest

from app import create_app
from app.db.extensions import db
from app.db.repositories.radars import seed_radars

# Allow cross-module test helpers (from test_bot import ...) after folder reorganization.
_TESTS_ROOT = Path(__file__).resolve().parent
for _path in [_TESTS_ROOT, *_TESTS_ROOT.rglob('*')]:
    if _path.is_dir():
        _as_str = str(_path)
        if _as_str not in sys.path:
            sys.path.insert(0, _as_str)


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    """Fail the test immediately if any SDK attempts real network I/O."""
    import httpx
    def denied(*args, **kwargs):
        raise AssertionError('Real HTTP requests are forbidden in tests.')
    import urllib.request
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', denied)
    monkeypatch.setattr(httpx.Client, 'send', denied)
    monkeypatch.setattr(httpx.AsyncClient, 'send', denied)


@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SQLALCHEMY_ENGINE_OPTIONS': {},
        'OPENAI_API_KEY': '',
        'FRONTEND_URL': 'http://localhost:3000',
        'INTERNAL_USER_EMAIL': '',
        'INTERNAL_USER_PASSWORD_HASH': '',
        'SEARCH_PROVIDER': 'disabled',
    })
    with application.app_context():
        db.create_all()
        seed_radars()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
