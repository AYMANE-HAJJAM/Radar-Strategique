"""Singleton durable cursor/lease for independent PMMP listing refresh."""
from app.db.extensions import db
from app.db.models import utcnow


class PmmpRefreshCheckpoint(db.Model):
    __tablename__ = 'pmmp_refresh_checkpoint'
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(16), nullable=False, default='idle', server_default='idle')
    lease_owner = db.Column(db.String(64))
    lease_until = db.Column(db.DateTime(timezone=True))
    heartbeat_at = db.Column(db.DateTime(timezone=True))
    cursor_page = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    page_state = db.Column(db.Text)
    page_signature = db.Column(db.Text)
    declared_pages = db.Column(db.Integer)
    declared_results = db.Column(db.Integer)
    cycle_complete = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    last_cycle_completed_at = db.Column(db.DateTime(timezone=True))
    last_success_at = db.Column(db.DateTime(timezone=True))
    last_started_at = db.Column(db.DateTime(timezone=True))
    last_finished_at = db.Column(db.DateTime(timezone=True))
    last_new = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_updated = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_unchanged = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_pages = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_stop_reason = db.Column(db.String(64))
    cycle_new = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    cycle_updated = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    cycle_unchanged = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    cycle_pages = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_error = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('idle', 'running', 'failed')",
            name='valid_pmmp_refresh_status'),
        db.CheckConstraint('id = 1', name='singleton_pmmp_refresh_checkpoint'),
    )
