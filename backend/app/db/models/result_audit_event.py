from sqlalchemy.dialects.postgresql import JSONB

from app.db.extensions import db
from app.db.models import utcnow


class ResultAuditEvent(db.Model):
    """Append-only product lifecycle events, separate from run observations."""
    __tablename__ = 'result_audit_events'
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id'), nullable=False, index=True)
    event_type = db.Column(db.String(24), nullable=False)
    performed_by = db.Column(db.BigInteger)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    event_metadata = db.Column(db.JSON().with_variant(JSONB(), 'postgresql'), nullable=False, default=dict)
