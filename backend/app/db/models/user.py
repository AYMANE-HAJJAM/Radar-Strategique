from app.db.extensions import db
from app.db.models import utcnow


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(8), nullable=False, default='USER', index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    access_code_hash = db.Column(db.String(255), nullable=False)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime(timezone=True))
    revoked_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (db.CheckConstraint("role IN ('ADMIN','USER')", name='valid_user_role'),)


class AuthAuditEvent(db.Model):
    __tablename__ = 'auth_audit_events'
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    subject_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(40), nullable=False, index=True)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
