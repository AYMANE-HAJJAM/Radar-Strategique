from flask import jsonify, request

from app.api.auth import current_user_id, require_admin
from app.api.common import error
from app.db.extensions import db
from app.db.models import AuthAuditEvent, User
from app.modules.auth import AccessService

service = AccessService()
SELF_MESSAGE = "Cette action n’est pas autorisée sur votre compte actuel."


def _user_or_error(user_id):
    return db.session.get(User, user_id)


def _reject_self_action(user):
    if user.id == current_user_id():
        return error('SELF_ACTION_NOT_ALLOWED', SELF_MESSAGE, 409)
    return None


def register(bp):
    @bp.get('/admin/users')
    @require_admin
    def users():
        rows = db.session.scalars(db.select(User).order_by(User.created_at, User.id)).all()
        audits = db.session.scalars(db.select(AuthAuditEvent).order_by(
            AuthAuditEvent.id.desc()).limit(50)).all()
        return jsonify(items=[service.public(row) for row in rows], audit=[{
            'id': row.id, 'action': row.action, 'actor_user_id': row.actor_user_id,
            'subject_user_id': row.subject_user_id, 'created_at': row.created_at.isoformat()
        } for row in audits])

    @bp.post('/admin/users')
    @require_admin
    def create_user():
        payload = request.get_json(silent=True) or {}
        try:
            user, code = service.create(payload.get('name', ''), payload.get('role', 'USER'), current_user_id())
        except ValueError as exc:
            return error('INVALID_USER', str(exc), 400)
        return jsonify(**service.public(user), access_code=code), 201

    @bp.post('/admin/users/<int:user_id>/regenerate-code')
    @require_admin
    def regenerate(user_id):
        user = _user_or_error(user_id)
        if not user:
            return error('USER_NOT_FOUND', 'Utilisateur introuvable.', 404)
        rejected = _reject_self_action(user)
        if rejected:
            return rejected
        code = service.regenerate(user, current_user_id())
        return jsonify(**service.public(user), access_code=code)

    @bp.post('/admin/users/<int:user_id>/deactivate')
    @require_admin
    def deactivate(user_id):
        user = _user_or_error(user_id)
        if not user:
            return error('USER_NOT_FOUND', 'Utilisateur introuvable.', 404)
        rejected = _reject_self_action(user)
        if rejected:
            return rejected
        try:
            service.deactivate(user, current_user_id())
        except ValueError as exc:
            return error('LAST_ADMIN', str(exc), 409)
        return jsonify(service.public(user))

    @bp.post('/admin/users/<int:user_id>/reactivate')
    @require_admin
    def reactivate(user_id):
        user = _user_or_error(user_id)
        if not user:
            return error('USER_NOT_FOUND', 'Utilisateur introuvable.', 404)
        if user.active:
            return error('USER_ALREADY_ACTIVE', 'Cet utilisateur est déjà actif.', 409)
        code = service.reactivate(user, current_user_id())
        return jsonify(**service.public(user), access_code=code)
