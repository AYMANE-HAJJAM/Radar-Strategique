from concurrent.futures import Future

from werkzeug.security import check_password_hash

from app.api.auth import failed_attempts
from app.core.agent_errors import ActiveRunError
from app.db.extensions import db
from app.db.models import AuthAuditEvent, Radar, Result, ResultObservation, SearchRun, User
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
    me = client.get('/api/auth/me')
    assert me.status_code == 200 and me.get_json()['user']['id'] == user_id
    assert client.get('/api/radars').status_code == 200
    assert client.post('/api/auth/logout', headers={'X-CSRF-Token': csrf}).status_code == 204
    assert client.get('/api/auth/me').status_code == 401
    assert client.get('/api/radars').status_code == 401


def test_render_session_cookie_is_secure_cross_site(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('FLASK_ENV', 'development')
    from app.config import load_config
    config = load_config()
    assert config['SESSION_COOKIE_HTTPONLY'] is True
    assert config['SESSION_COOKIE_SECURE'] is True
    assert config['SESSION_COOKIE_SAMESITE'] == 'None'


def test_local_session_cookie_is_lax_and_not_secure(app):
    _, code = make_user(app)
    response = app.test_client().post('/api/auth/access', json={'access_code': code})
    cookie = response.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie
    assert 'Secure' not in cookie


def test_foreign_origin_is_not_credentialed(app):
    response = app.test_client().get('/api/health', headers={'Origin': 'https://evil.example'})
    assert 'Access-Control-Allow-Origin' not in response.headers


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


def _pending_result(radar_id, title, fingerprint, *, review='PENDING', discovery='NEW', content_hash=None):
    row = Result(radar_id=radar_id, title=title, fingerprint=fingerprint, status='new',
                 discovery_status=discovery, review_status=review, priority='2', source_status='open',
                 content_hash=content_hash or f'{fingerprint}-hash',
                 radar_metadata={'detail_verified': True, 'official_confirmation': True,
                                 'morocco_related': True, 'current_evidence': True})
    db.session.add(row)
    db.session.flush()
    return row


def test_result_rows_use_the_observation_launcher(app):
    aymane_id, aymane_code = make_user(app, 'Aymane', 'ADMIN')
    emmanuel_id, _emmanuel_code = make_user(app, 'Emmanuel', 'USER')
    with app.app_context():
        codes = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
        ids = {code: _radar_id(app, code) for code in codes}
        aymane_markets = SearchRun(radar_id=ids['RADAR_1_MARKETS'], status='completed', current_stage='COMPLETED', launched_by_user_id=aymane_id)
        old_markets = SearchRun(radar_id=ids['RADAR_1_MARKETS'], status='completed', current_stage='COMPLETED')
        aymane_projects = SearchRun(radar_id=ids['RADAR_2_PROJECTS'], status='completed', current_stage='COMPLETED', launched_by_user_id=aymane_id)
        emmanuel_projects = SearchRun(radar_id=ids['RADAR_2_PROJECTS'], status='completed', current_stage='COMPLETED', launched_by_user_id=emmanuel_id)
        anonymous_projects = SearchRun(radar_id=ids['RADAR_2_PROJECTS'], status='completed', current_stage='COMPLETED')
        owned = {
            'RADAR_3_INSTITUTIONS': SearchRun(radar_id=ids['RADAR_3_INSTITUTIONS'], status='completed', current_stage='COMPLETED', launched_by_user_id=emmanuel_id),
            'RADAR_4_POLICIES': SearchRun(radar_id=ids['RADAR_4_POLICIES'], status='completed', current_stage='COMPLETED', launched_by_user_id=emmanuel_id),
            'RADAR_5_FUNDING': SearchRun(radar_id=ids['RADAR_5_FUNDING'], status='completed', current_stage='COMPLETED', launched_by_user_id=aymane_id),
        }
        db.session.add_all([aymane_markets, old_markets, aymane_projects, emmanuel_projects, anonymous_projects, *owned.values()])
        db.session.flush()
        market = _pending_result(ids['RADAR_1_MARKETS'], 'Étude de restauration du monument historique Aymane', 'fp-markets-aymane')
        old = _pending_result(ids['RADAR_1_MARKETS'], 'Étude de restauration du monument historique ancien', 'fp-markets-old')
        shared = _pending_result(ids['RADAR_2_PROJECTS'], 'Projet observé par deux recherches', 'fp-projects-shared')
        others = {
            code: _pending_result(ids[code], f'Signal {code}', f'fp-{code}')
            for code in ('RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
        }
        db.session.add_all([
            ResultObservation(run_id=aymane_markets.id, result_id=market.id, state='new', snapshot={}),
            ResultObservation(run_id=old_markets.id, result_id=old.id, state='new', snapshot={}),
            ResultObservation(run_id=aymane_projects.id, result_id=shared.id, state='new', snapshot={}),
            ResultObservation(run_id=emmanuel_projects.id, result_id=shared.id, state='updated', snapshot={}),
            ResultObservation(run_id=anonymous_projects.id, result_id=shared.id, state='unchanged', snapshot={}),
            *[ResultObservation(run_id=owned[code].id, result_id=others[code].id, state='new', snapshot={})
              for code in others],
        ])
        db.session.commit()
        run_ids = {
            'aymane_markets': aymane_markets.id, 'old_markets': old_markets.id,
            'aymane_projects': aymane_projects.id, 'emmanuel_projects': emmanuel_projects.id,
            'anonymous_projects': anonymous_projects.id,
        }
    client = app.test_client()
    login(client, aymane_code)

    def rows(code, run_id=None):
        suffix = f'&run_id={run_id}' if run_id else ''
        response = client.get(f'/api/radars/{ids[code]}/results?status=pending&page_size=50{suffix}')
        assert response.status_code == 200
        return response.get_json()['items']

    markets = {item['title']: item for item in rows('RADAR_1_MARKETS')}
    assert markets['Étude de restauration du monument historique Aymane']['launched_by'] == {'id': aymane_id, 'name': 'Aymane'}
    assert markets['Étude de restauration du monument historique ancien']['launched_by'] is None
    assert 'access_code_hash' not in markets['Étude de restauration du monument historique Aymane']['launched_by']
    assert {item['launched_by']['name'] for item in rows('RADAR_1_MARKETS', run_ids['aymane_markets'])} == {'Aymane'}
    assert all(item['launched_by'] is None for item in rows('RADAR_1_MARKETS', run_ids['old_markets']))

    emmanuel = {'id': emmanuel_id, 'name': 'Emmanuel'}
    aymane = {'id': aymane_id, 'name': 'Aymane'}
    assert rows('RADAR_3_INSTITUTIONS')[0]['launched_by'] == emmanuel
    assert rows('RADAR_4_POLICIES')[0]['launched_by'] == emmanuel
    assert rows('RADAR_5_FUNDING')[0]['launched_by'] == aymane
    assert rows('RADAR_2_PROJECTS')[0]['launched_by'] == emmanuel
    assert rows('RADAR_2_PROJECTS', run_ids['aymane_projects'])[0]['launched_by'] == aymane
    assert rows('RADAR_2_PROJECTS', run_ids['emmanuel_projects'])[0]['launched_by'] == emmanuel
    assert rows('RADAR_2_PROJECTS', run_ids['anonymous_projects']) == []


def test_run_view_is_actionable_pending_for_every_radar(app):
    user_id, code = make_user(app, 'Aymane', 'ADMIN')
    codes = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
    with app.app_context():
        ids = {radar_code: _radar_id(app, radar_code) for radar_code in codes}
        seeded = {}
        for radar_code in codes:
            radar_id = ids[radar_code]
            run = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED', launched_by_user_id=user_id)
            empty = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED', launched_by_user_id=user_id)
            db.session.add_all([run, empty])
            db.session.flush()
            older = [_pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} {n}', f'{radar_code}-old-{n}') for n in range(5)]
            updated = _pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} maj', f'{radar_code}-updated', discovery='UPDATED')
            created = [_pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} nouveau {n}', f'{radar_code}-new-{n}', content_hash=f'{radar_code}-new-{n}-hash') for n in range(2)]
            approved = _pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} validé', f'{radar_code}-approved', review='APPROVED')
            rejected = _pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} rejeté', f'{radar_code}-rejected', review='REJECTED')
            db.session.add_all([
                ResultObservation(run_id=run.id, result_id=created[0].id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=created[0].id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=created[1].id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=updated.id, state='updated', snapshot={}),
                ResultObservation(run_id=run.id, result_id=older[0].id, state='unchanged', snapshot={}),
                ResultObservation(run_id=run.id, result_id=approved.id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=rejected.id, state='new', snapshot={}),
                ResultObservation(run_id=empty.id, result_id=older[1].id, state='unchanged', snapshot={}),
            ])
            seeded[radar_code] = {'run': run.id, 'empty': empty.id, 'approve': created[0].id, 'version': created[0].content_hash[:12]}
        db.session.commit()
    client = app.test_client()
    csrf = login(client, code)
    for radar_code, radar_id in ids.items():
        run_id = seeded[radar_code]['run']
        scoped = client.get(f'/api/radars/{radar_id}/results?status=pending&run_id={run_id}&page_size=50')
        assert scoped.status_code == 200
        body = scoped.get_json()
        assert body['run_total'] == 3 and body['total'] == 3 and body['pending_total'] == 8
        assert len(body['items']) == 3
        assert len({item['id'] for item in body['items']}) == 3
        assert sorted(item['run_observation'] for item in body['items']) == ['new', 'new', 'updated']
        assert all('NEW' != item['run_observation'] for item in body['items'])
        backlog = client.get(f'/api/radars/{radar_id}/results?status=pending&page_size=50').get_json()
        assert backlog['total'] == 8 and backlog['pending_total'] == 8 and 'run_id' not in backlog
        assert backlog['total'] == body['pending_total']
        assert len(backlog['items']) == backlog['total']
        assert all('run_observation' not in item for item in backlog['items'])
        assert (body['total'] == 0) == (body['items'] == [])
        empty = client.get(f"/api/radars/{radar_id}/results?status=pending&run_id={seeded[radar_code]['empty']}&page_size=50").get_json()
        assert empty['items'] == [] and empty['run_total'] == 0 and empty['pending_total'] == 8
        approved = client.post(f"/api/results/{seeded[radar_code]['approve']}/approve",
                               json={'version': seeded[radar_code]['version']}, headers={'X-CSRF-Token': csrf})
        assert approved.status_code == 200, approved.get_json()
        after = client.get(f'/api/radars/{radar_id}/results?status=pending&run_id={run_id}&page_size=50').get_json()
        assert after['run_total'] == 2 and after['total'] == 2 and after['pending_total'] == 7
        assert len(after['items']) == after['total']
        assert seeded[radar_code]['approve'] not in {item['id'] for item in after['items']}


def _assert_view_agrees(body):
    assert body['total'] >= len(body['items'])
    if body['page'] == 1 and body['total'] <= body['page_size']:
        assert len(body['items']) == body['total']
    if body['total'] == 0:
        assert body['items'] == []


def test_empty_run_does_not_return_older_pending_rows(app):
    """Run with no NEW/UPDATED observations must not render the existing backlog."""
    user_id, code = make_user(app, 'Aymane', 'ADMIN')
    codes = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
    with app.app_context():
        ids = {radar_code: _radar_id(app, radar_code) for radar_code in codes}
        runs = {}
        old_ids = {}
        for radar_code in codes:
            radar_id = ids[radar_code]
            earlier = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED')
            current = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED', launched_by_user_id=user_id)
            db.session.add_all([earlier, current])
            db.session.flush()
            older = [_pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} stock {n}', f'{radar_code}-stock-{n}') for n in range(2)]
            db.session.add_all([
                ResultObservation(run_id=earlier.id, result_id=older[0].id, state='new', snapshot={}),
                ResultObservation(run_id=earlier.id, result_id=older[1].id, state='new', snapshot={}),
                ResultObservation(run_id=current.id, result_id=older[0].id, state='unchanged', snapshot={}),
                ResultObservation(run_id=current.id, result_id=older[1].id, state='unchanged', snapshot={}),
            ])
            runs[radar_code] = current.id
            old_ids[radar_code] = {row.id for row in older}
        db.session.commit()
    client = app.test_client()
    login(client, code)
    for radar_code, radar_id in ids.items():
        scoped = client.get(f"/api/radars/{radar_id}/results?status=pending&run_id={runs[radar_code]}&page_size=50").get_json()
        backlog = client.get(f'/api/radars/{radar_id}/results?status=pending&page_size=50').get_json()
        _assert_view_agrees(scoped)
        _assert_view_agrees(backlog)
        assert scoped['total'] == 0 and scoped['run_total'] == 0 and scoped['items'] == []
        assert scoped['pending_total'] == 2
        assert backlog['total'] == 2 and backlog['pending_total'] == 2
        assert {item['id'] for item in backlog['items']} == old_ids[radar_code]
        assert backlog['total'] == scoped['pending_total']


def test_run_membership_and_backlog_are_separate_filters(app):
    user_id, code = make_user(app, 'Aymane', 'ADMIN')
    codes = ('RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES', 'RADAR_5_FUNDING')
    with app.app_context():
        ids = {radar_code: _radar_id(app, radar_code) for radar_code in codes}
        seeded = {}
        for radar_code in codes:
            radar_id = ids[radar_code]
            run = SearchRun(radar_id=radar_id, status='completed', current_stage='COMPLETED', launched_by_user_id=user_id)
            db.session.add(run)
            db.session.flush()
            old = [_pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} ancien {n}', f'{radar_code}-avant-{n}') for n in range(2)]
            updated = _pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} mis à jour', f'{radar_code}-maj', discovery='UPDATED', content_hash=f'{radar_code}-maj-hashxx')
            created = [_pending_result(radar_id, f'Étude de restauration du monument historique {radar_code} neuf {n}', f'{radar_code}-neuf-{n}') for n in range(2)]
            db.session.add_all([
                ResultObservation(run_id=run.id, result_id=old[0].id, state='unchanged', snapshot={}),
                ResultObservation(run_id=run.id, result_id=created[0].id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=created[1].id, state='new', snapshot={}),
                ResultObservation(run_id=run.id, result_id=updated.id, state='updated', snapshot={}),
            ])
            seeded[radar_code] = {'run': run.id, 'old': {row.id for row in old}, 'found': {created[0].id, created[1].id, updated.id}, 'drop': created[0].id, 'version': created[0].content_hash[:12]}
        db.session.commit()
    client = app.test_client()
    csrf = login(client, code)
    for radar_code, radar_id in ids.items():
        run_id = seeded[radar_code]['run']
        scoped = client.get(f'/api/radars/{radar_id}/results?status=pending&run_id={run_id}&page_size=50').get_json()
        backlog = client.get(f'/api/radars/{radar_id}/results?status=pending&page_size=50').get_json()
        _assert_view_agrees(scoped)
        _assert_view_agrees(backlog)
        assert scoped['total'] == 3 and scoped['run_total'] == 3 and len(scoped['items']) == 3
        assert {item['id'] for item in scoped['items']} == seeded[radar_code]['found']
        assert not seeded[radar_code]['old'] & {item['id'] for item in scoped['items']}
        assert backlog['total'] == 5 and len(backlog['items']) == 5
        assert seeded[radar_code]['old'] <= {item['id'] for item in backlog['items']}
        assert backlog['total'] == scoped['pending_total']
        approved = client.post(f"/api/results/{seeded[radar_code]['drop']}/approve", json={'version': seeded[radar_code]['version']}, headers={'X-CSRF-Token': csrf})
        assert approved.status_code == 200, approved.get_json()
        after_run = client.get(f'/api/radars/{radar_id}/results?status=pending&run_id={run_id}&page_size=50').get_json()
        after_backlog = client.get(f'/api/radars/{radar_id}/results?status=pending&page_size=50').get_json()
        _assert_view_agrees(after_run)
        _assert_view_agrees(after_backlog)
        assert after_run['total'] == 2 and after_run['run_total'] == 2
        assert after_backlog['total'] == 4 and after_run['pending_total'] == 4
        assert seeded[radar_code]['drop'] not in {item['id'] for item in after_run['items']}
        assert seeded[radar_code]['drop'] not in {item['id'] for item in after_backlog['items']}
