from concurrent.futures import Future

from werkzeug.security import check_password_hash

from app.api.auth import failed_attempts
from app.core.agent_errors import ActiveRunError
from app.db.extensions import db
from app.db.models import AuthAuditEvent, Radar, SearchRun, User
from app.modules.auth import AccessService


def make_user(app, name='Admin', role='ADMIN'):
    with app.app_context():
        user, code = AccessService().create(name, role)
        return user.id, code


def login(client, code):
    response = client.post('/api/auth/access', json={'access_code': code})
    assert response.status_code == 200
    return response.get_json()['csrf_token']


def test_health_is_lightweight(app):
    assert app.test_client().get('/api/health').get_json() == {'status': 'ok'}


def test_valid_code_login_me_and_logout(app):
    user_id, code = make_user(app)
    client = app.test_client(); csrf = login(client, code)
    assert client.get('/api/auth/me').get_json()['user']['id'] == user_id
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 204
    assert client.get('/api/auth/me').status_code == 401


def test_access_preflight_and_post_include_credentialed_cors(app):
    _, code = make_user(app)
    client = app.test_client()
    preflight = client.options('/api/auth/access', headers={
        'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type',
    })
    assert preflight.status_code == 204
    assert preflight.headers['Access-Control-Allow-Origin'] == 'http://localhost:3000'
    response = client.post('/api/auth/access', json={'access_code': code},
                           headers={'Origin': 'http://localhost:3000'})
    assert response.status_code == 200
    assert response.headers['Access-Control-Allow-Origin'] == 'http://localhost:3000'
    assert response.headers['Access-Control-Allow-Credentials'] == 'true'


def test_invalid_and_inactive_code_use_generic_error(app):
    failed_attempts.clear(); user_id, code = make_user(app)
    client = app.test_client()
    invalid = client.post('/api/auth/access', json={'access_code': 'AAAA-BBBB-CC'})
    with app.app_context():
        user = db.session.get(User, user_id); user.active = False; db.session.commit()
    inactive = client.post('/api/auth/access', json={'access_code': code})
    assert invalid.status_code == inactive.status_code == 401
    assert invalid.get_json()['error']['message'] == inactive.get_json()['error']['message'] == "Code d’accès invalide."


def test_normal_user_cannot_manage_users(app):
    _, code = make_user(app, 'Collaborateur', 'USER')
    client = app.test_client(); login(client, code)
    assert client.get('/api/admin/users').status_code == 403


def test_admin_create_code_is_hashed_and_generated_code_works(app):
    _, admin_code = make_user(app)
    client = app.test_client(); csrf = login(client, admin_code)
    response = client.post('/api/admin/users', json={'name': 'Emmanuel', 'role': 'USER'},
                           headers={'X-CSRF-Token': csrf})
    assert response.status_code == 201
    payload = response.get_json(); raw = payload['access_code']
    assert len(raw) == 12 and raw[4] == raw[9] == '-'
    with app.app_context():
        user = db.session.get(User, payload['id'])
        assert raw not in user.access_code_hash
        assert check_password_hash(user.access_code_hash, raw)
    assert app.test_client().post('/api/auth/access', json={'access_code': raw}).status_code == 200


def test_regenerate_invalidates_old_code_and_sessions(app):
    _, admin_code = make_user(app); user_id, old_code = make_user(app, 'User', 'USER')
    user_client = app.test_client(); login(user_client, old_code)
    admin = app.test_client(); csrf = login(admin, admin_code)
    response = admin.post(f'/api/admin/users/{user_id}/regenerate-code', json={},
                          headers={'X-CSRF-Token': csrf})
    new_code = response.get_json()['access_code']
    assert user_client.get('/api/auth/me').status_code == 401
    assert app.test_client().post('/api/auth/access', json={'access_code': old_code}).status_code == 401
    assert app.test_client().post('/api/auth/access', json={'access_code': new_code}).status_code == 200


def test_deactivate_blocks_session_and_reactivate_returns_fresh_code(app):
    _, admin_code = make_user(app); user_id, code = make_user(app, 'User', 'USER')
    user_client = app.test_client(); login(user_client, code)
    admin = app.test_client(); csrf = login(admin, admin_code)
    assert admin.post(f'/api/admin/users/{user_id}/deactivate', json={}, headers={'X-CSRF-Token': csrf}).status_code == 200
    assert user_client.get('/api/auth/me').status_code == 401
    response = admin.post(f'/api/admin/users/{user_id}/reactivate', json={}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200
    assert app.test_client().post('/api/auth/access', json={'access_code': response.get_json()['access_code']}).status_code == 200


def _session_version(app, user_id):
    with app.app_context():
        return db.session.get(User, user_id).session_version


def test_admin_cannot_regenerate_own_code(app):
    admin_id, code = make_user(app)
    client = app.test_client(); csrf = login(client, code)
    before = _session_version(app, admin_id)
    response = client.post(f'/api/admin/users/{admin_id}/regenerate-code', json={},
                           headers={'X-CSRF-Token': csrf})
    payload = response.get_json()
    assert response.status_code == 409
    assert payload['error']['code'] == 'SELF_ACTION_NOT_ALLOWED'
    assert payload['error']['message'] == "Cette action n’est pas autorisée sur votre compte actuel."
    assert 'access_code' not in payload
    assert _session_version(app, admin_id) == before
    assert client.get('/api/auth/me').status_code == 200
    assert app.test_client().post('/api/auth/access', json={'access_code': code}).status_code == 200


def test_admin_cannot_deactivate_own_account(app):
    admin_id, code = make_user(app)
    make_user(app, 'Second admin', 'ADMIN')
    client = app.test_client(); csrf = login(client, code)
    before = _session_version(app, admin_id)
    response = client.post(f'/api/admin/users/{admin_id}/deactivate', json={}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'SELF_ACTION_NOT_ALLOWED'
    with app.app_context():
        user = db.session.get(User, admin_id)
        assert user.active and user.revoked_at is None and user.session_version == before
    assert client.get('/api/auth/me').status_code == 200


def test_last_admin_cannot_be_deactivated(app, monkeypatch):
    admin_id, code = make_user(app)
    client = app.test_client(); csrf = login(client, code)
    before = _session_version(app, admin_id)
    monkeypatch.setattr('app.api.admin_users.current_user_id', lambda: admin_id + 1)
    response = client.post(f'/api/admin/users/{admin_id}/deactivate', json={}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 409
    assert response.get_json()['error']['code'] == 'LAST_ADMIN'
    with app.app_context():
        user = db.session.get(User, admin_id)
        assert user.active and user.session_version == before


def test_login_and_management_are_audited_without_raw_code(app):
    _, code = make_user(app); client = app.test_client(); csrf = login(client, code)
    response = client.post('/api/admin/users', json={'name': 'Audited', 'role': 'USER'},
                           headers={'X-CSRF-Token': csrf})
    raw = response.get_json()['access_code']
    with app.app_context():
        events = db.session.scalars(db.select(AuthAuditEvent)).all()
        assert {'USER_LOGIN', 'USER_CREATED'} <= {event.action for event in events}
        assert raw not in repr([event.metadata_json for event in events])


def test_duplicate_run_is_a_conflict(app, monkeypatch):
    _, code = make_user(app); client = app.test_client(); csrf = login(client, code)
    monkeypatch.setattr('app.api.radars.launch_radar', lambda *args: (_ for _ in ()).throw(ActiveRunError()))
    response = client.post('/api/radars/1/runs', json={}, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 409


def _quiet_runner(app, monkeypatch):
    def submit(*args, **kwargs):
        future = Future()
        future.set_result(None)
        return future
    monkeypatch.setattr(app.extensions['radar_job_runner'], 'submit', submit)


def _radar_id(app, code):
    with app.app_context():
        return db.session.scalar(db.select(Radar.id).where(Radar.code == code))


def test_launch_records_session_user_and_ignores_spoofed_identity(app, monkeypatch):
    _quiet_runner(app, monkeypatch)
    aymane_id, aymane_code = make_user(app, 'Aymane', 'ADMIN')
    emmanuel_id, emmanuel_code = make_user(app, 'Emmanuel', 'USER')
    markets_id, projects_id = _radar_id(app, 'RADAR_1_MARKETS'), _radar_id(app, 'RADAR_2_PROJECTS')
    aymane = app.test_client(); aymane_csrf = login(aymane, aymane_code)
    response = aymane.post(f'/api/radars/{markets_id}/runs', json={'launched_by_user_id': emmanuel_id, 'user_id': emmanuel_id},
                           headers={'X-CSRF-Token': aymane_csrf})
    assert response.status_code == 201
    created = response.get_json()
    assert created['launched_by'] == {'id': aymane_id, 'name': 'Aymane'}
    assert 'access_code' not in created
    detail = aymane.get(f"/api/runs/{created['run_id']}").get_json()
    assert detail['launched_by'] == {'id': aymane_id, 'name': 'Aymane'}
    history = aymane.get(f'/api/radars/{markets_id}/runs').get_json()['items']
    assert history[0]['id'] == created['run_id'] and history[0]['launched_by']['name'] == 'Aymane'
    with app.app_context():
        run = db.session.get(SearchRun, created['run_id'])
        assert run.launched_by_user_id == aymane_id and run.radar_id == markets_id
        event = db.session.scalar(db.select(AuthAuditEvent).where(AuthAuditEvent.action == 'RADAR_LAUNCHED'))
        assert event.actor_user_id == aymane_id and event.created_at is not None
        assert event.metadata_json['run_id'] == created['run_id']
        assert event.metadata_json['radar_id'] == markets_id
        assert event.metadata_json['launched_by_user_id'] == aymane_id
        assert event.metadata_json['launched_by_name'] == 'Aymane'
    emmanuel = app.test_client(); emmanuel_csrf = login(emmanuel, emmanuel_code)
    second = emmanuel.post(f'/api/radars/{projects_id}/runs', json={'launched_by_user_id': aymane_id},
                           headers={'X-CSRF-Token': emmanuel_csrf})
    assert second.status_code == 201
    assert second.get_json()['launched_by'] == {'id': emmanuel_id, 'name': 'Emmanuel'}
    with app.app_context():
        assert db.session.get(SearchRun, second.get_json()['run_id']).launched_by_user_id == emmanuel_id


def test_run_without_launcher_stays_anonymous(app):
    _, code = make_user(app)
    with app.app_context():
        radar_id = _radar_id(app, 'RADAR_1_MARKETS')
        run = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED')
        db.session.add(run); db.session.commit(); run_id = run.id
    client = app.test_client(); login(client, code)
    payload = client.get(f'/api/runs/{run_id}').get_json()
    assert payload['launched_by'] is None
    assert payload['id'] == run_id


def test_launcher_is_exposed_for_every_radar(app, monkeypatch):
    _quiet_runner(app, monkeypatch)
    aymane_id, aymane_code = make_user(app, 'Aymane', 'ADMIN')
    emmanuel_id, emmanuel_code = make_user(app, 'Emmanuel', 'USER')
    codes = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
    ids = {code: _radar_id(app, code) for code in codes}
    aymane = app.test_client(); aymane_csrf = login(aymane, aymane_code)
    emmanuel = app.test_client(); emmanuel_csrf = login(emmanuel, emmanuel_code)
    expected = {}
    for code, actor, actor_id, token in (
        ('RADAR_1_MARKETS', aymane, aymane_id, aymane_csrf),
        ('RADAR_3_INSTITUTIONS', emmanuel, emmanuel_id, emmanuel_csrf),
        ('RADAR_2_PROJECTS', aymane, aymane_id, aymane_csrf),
        ('RADAR_4_POLICIES', emmanuel, emmanuel_id, emmanuel_csrf),
        ('RADAR_5_FUNDING', aymane, aymane_id, aymane_csrf),
    ):
        response = actor.post(f'/api/radars/{ids[code]}/runs', json={'launched_by_user_id': 99999}, headers={'X-CSRF-Token': token})
        assert response.status_code == 201
        body = response.get_json()
        assert body['launched_by'] == {'id': actor_id, 'name': 'Aymane' if actor is aymane else 'Emmanuel'}
        assert 'access_code' not in body and 'access_code_hash' not in body and 'session_version' not in body
        expected[code] = body['launched_by']['name']
    with app.app_context():
        anonymous = SearchRun(radar_id=ids['RADAR_1_MARKETS'], status='failed', current_stage='FAILED')
        db.session.add(anonymous); db.session.commit()
    for code, name in expected.items():
        history = aymane.get(f'/api/radars/{ids[code]}/runs').get_json()['items']
        owned = next(item for item in history if item['launched_by'])
        assert owned['launched_by']['name'] == name
        assert 'access_code_hash' not in owned and 'session_version' not in owned['launched_by']
        detail = aymane.get(f"/api/runs/{owned['id']}").get_json()
        assert detail['launched_by']['name'] == name
    markets = aymane.get(f"/api/radars/{ids['RADAR_1_MARKETS']}/runs").get_json()['items']
    assert any(item['launched_by'] is None for item in markets)


def test_results_pagination(app):
    _, code = make_user(app); client = app.test_client(); login(client, code)
    response = client.get('/api/radars/1/results?status=pending&page=1&page_size=20')
    assert response.status_code == 200
