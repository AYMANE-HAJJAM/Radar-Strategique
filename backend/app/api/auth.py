import secrets
from collections import defaultdict, deque
from datetime import timedelta
from functools import wraps

from flask import jsonify, request, session

from app.db.extensions import db
from app.db.models import User, utcnow
from app.modules.auth import AccessService

service = AccessService()
failed_attempts = defaultdict(deque)
MAX_ATTEMPTS = 5
COOLDOWN = timedelta(minutes=15)


def _client_key():
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()


def _current_user():
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user or not user.active or session.get('session_version') != user.session_version:
        session.clear()
        return None
    return user


def require_auth(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        user = _current_user()
        if not user:
            return jsonify(error={'code': 'UNAUTHENTICATED', 'message': 'Authentification requise.'}), 401
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf_token', '')):
                return jsonify(error={'code': 'INVALID_CSRF', 'message': 'Session expirée. Rechargez la page.'}), 403
        return handler(*args, **kwargs)
    return wrapped


def require_admin(handler):
    @wraps(handler)
    @require_auth
    def wrapped(*args, **kwargs):
        if current_user().role != 'ADMIN':
            return jsonify(error={'code': 'FORBIDDEN', 'message': 'Accès administrateur requis.'}), 403
        return handler(*args, **kwargs)
    return wrapped


def current_user():
    return db.session.get(User, session['user_id'])


def current_user_id():
    return int(session['user_id'])


def register(bp):
    @bp.route('/auth/access', methods=['POST'], provide_automatic_options=False)
    def access():
        key, now = _client_key(), utcnow()
        attempts = failed_attempts[key]
        while attempts and now - attempts[0] >= COOLDOWN:
            attempts.popleft()
        if len(attempts) >= MAX_ATTEMPTS:
            return jsonify(error={'code': 'LOGIN_RATE_LIMITED',
                'message': 'Trop de tentatives. Réessayez dans quelques minutes.'}), 429
        user = service.authenticate((request.get_json(silent=True) or {}).get('access_code', ''))
        if not user:
            attempts.append(now)
            return jsonify(error={'code': 'INVALID_ACCESS_CODE', 'message': "Code d’accès invalide."}), 401
        attempts.clear()
        session.clear()
        session.permanent = True
        session['user_id'] = user.id
        session['session_version'] = user.session_version
        session['csrf_token'] = secrets.token_urlsafe(32)
        return jsonify(user=service.public(user), csrf_token=session['csrf_token'])

    @bp.get('/auth/me')
    @require_auth
    def me():
        return jsonify(user=service.public(current_user()), csrf_token=session['csrf_token'])

    @bp.post('/auth/logout')
    @require_auth
    def logout():
        session.clear()
        return '', 204
