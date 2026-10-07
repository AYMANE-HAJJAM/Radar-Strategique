from app.db.extensions import db
from app.db.models import User
from test_api import login, make_user


def test_session_shared_by_tabs_and_revoked_on_logout(app):
    user_id, code = make_user(app)
    first_tab = app.test_client()
    csrf = login(first_tab, code)
    cookie_name = app.config['SESSION_COOKIE_NAME']
    cookie = first_tab.get_cookie(cookie_name)
    assert cookie is not None
    assert cookie.expires is not None

    second_tab = app.test_client()
    second_tab.set_cookie(cookie_name, cookie.value)
    assert second_tab.get('/api/auth/me').status_code == 200
    assert second_tab.get('/api/radars').status_code == 200
    with app.app_context():
        version = db.session.get(User, user_id).session_version

    response = first_tab.post('/api/auth/logout', headers={'X-CSRF-Token': csrf})
    assert response.status_code == 204
    assert first_tab.get_cookie(cookie_name) is None
    assert 'Max-Age=0' in response.headers['Set-Cookie']
    with app.app_context():
        assert db.session.get(User, user_id).session_version == version + 1

    # Even a copied pre-logout signed cookie is invalid on the backend.
    assert second_tab.get('/api/auth/me').status_code == 401
    second_tab.set_cookie(cookie_name, cookie.value)
    assert second_tab.get('/api/radars').status_code == 401
    assert app.test_client().get('/api/auth/me').status_code == 401
    assert first_tab.get('/api/radars').status_code == 401

    # Logout does not revoke or change the access code.
    login(first_tab, code)
    assert first_tab.get('/api/auth/me').status_code == 200


def test_logout_requires_csrf_and_keeps_session_on_failure(app):
    user_id, code = make_user(app)
    client = app.test_client()
    login(client, code)
    with app.app_context():
        version = db.session.get(User, user_id).session_version
    assert client.post('/api/auth/logout').status_code == 403
    assert client.get('/api/auth/me').status_code == 200
    with app.app_context():
        assert db.session.get(User, user_id).session_version == version


def test_auth_responses_cannot_be_cached(app):
    _, code = make_user(app)
    client = app.test_client()
    assert client.get('/api/auth/me').headers['Cache-Control'] == 'no-store'
    response = client.post('/api/auth/access', json={'access_code': code})
    assert response.headers['Cache-Control'] == 'no-store'
    assert client.get('/api/auth/me').headers['Cache-Control'] == 'no-store'
    assert client.post('/api/auth/logout', headers={
        'X-CSRF-Token': response.get_json()['csrf_token']
    }).headers['Cache-Control'] == 'no-store'
