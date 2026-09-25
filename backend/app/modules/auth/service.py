import secrets
import string

from werkzeug.security import check_password_hash, generate_password_hash

from app.db.extensions import db
from app.db.models import AuthAuditEvent, User, utcnow

ALPHABET = ''.join(character for character in string.ascii_uppercase + string.digits if character not in 'O0I1')


class AccessService:
    @staticmethod
    def generate_code():
        raw = ''.join(secrets.choice(ALPHABET) for _ in range(10))
        return f'{raw[:4]}-{raw[4:8]}-{raw[8:]}'

    @staticmethod
    def normalize_code(value):
        compact = ''.join(character for character in str(value).upper() if character.isalnum())
        return f'{compact[:4]}-{compact[4:8]}-{compact[8:]}' if len(compact) == 10 else ''

    @staticmethod
    def public(user):
        return {'id': user.id, 'name': user.display_name, 'role': user.role, 'active': user.active,
                'created_at': user.created_at.isoformat(),
                'last_login_at': user.last_login_at.isoformat() if user.last_login_at else None,
                'revoked_at': user.revoked_at.isoformat() if user.revoked_at else None}

    @staticmethod
    def audit(action, actor_id=None, subject_id=None, metadata=None):
        db.session.add(AuthAuditEvent(actor_user_id=actor_id, subject_user_id=subject_id,
                                      action=action, metadata_json=metadata or {}))

    def authenticate(self, code):
        normalized = self.normalize_code(code)
        if not normalized:
            return None
        for user in db.session.scalars(db.select(User).where(User.active.is_(True))).all():
            if check_password_hash(user.access_code_hash, normalized):
                user.last_login_at = utcnow()
                self.audit('USER_LOGIN', user.id, user.id)
                db.session.commit()
                return user
        return None

    def create(self, name, role, actor_id=None):
        name = str(name).strip()
        role = str(role).upper()
        if not 2 <= len(name) <= 120 or role not in {'ADMIN', 'USER'}:
            raise ValueError('Nom ou rôle invalide.')
        code = self.generate_code()
        user = User(display_name=name, role=role, access_code_hash=generate_password_hash(code))
        db.session.add(user)
        db.session.flush()
        self.audit('USER_CREATED', actor_id, user.id, {'role': role})
        db.session.commit()
        return user, code

    def regenerate(self, user, actor_id):
        code = self.generate_code()
        user.access_code_hash = generate_password_hash(code)
        user.session_version += 1
        user.active = True
        user.revoked_at = None
        self.audit('ACCESS_REGENERATED', actor_id, user.id)
        db.session.commit()
        return code

    def deactivate(self, user, actor_id):
        if user.role == 'ADMIN':
            active_admins = db.session.scalar(db.select(db.func.count(User.id)).where(
                User.role == 'ADMIN', User.active.is_(True))) or 0
            if active_admins <= 1:
                raise ValueError('Le dernier administrateur actif ne peut pas être désactivé.')
        user.active = False
        user.revoked_at = utcnow()
        user.session_version += 1
        self.audit('USER_DEACTIVATED', actor_id, user.id)
        db.session.commit()

    def reactivate(self, user, actor_id):
        code = self.generate_code()
        user.access_code_hash = generate_password_hash(code)
        user.session_version += 1
        user.active = True
        user.revoked_at = None
        self.audit('USER_REACTIVATED', actor_id, user.id)
        db.session.commit()
        return code
