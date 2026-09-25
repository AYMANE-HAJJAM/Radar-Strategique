from app.db.extensions import db
from app.db.models import utcnow
from sqlalchemy.dialects.postgresql import JSONB


class Result(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    radar_id = db.Column(db.Integer, db.ForeignKey('radars.id'), nullable=False)
    title = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(255))
    url = db.Column(db.Text)
    reference = db.Column(db.String(255), index=True)
    institution = db.Column(db.String(255), index=True)
    publication_date = db.Column(db.Date)
    deadline = db.Column(db.Date, index=True)
    status = db.Column(db.String(32), nullable=False, default='new')
    # Independent Radar 1 dimensions. Legacy status remains for backward compatibility.
    discovery_status = db.Column(db.String(16), index=True)
    review_status = db.Column(db.String(16), index=True)
    reviewed_by = db.Column(db.BigInteger)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    update_reason = db.Column(db.JSON)
    priority = db.Column(db.String(32), nullable=False, default='normal')
    ai_score = db.Column(db.Integer)
    fingerprint = db.Column(db.String(64), nullable=False)
    canonical_url = db.Column(db.Text)
    url_key = db.Column(db.String(64), index=True)
    reference_key = db.Column(db.String(64), index=True)
    identity_key = db.Column(db.String(64), index=True)
    content_hash = db.Column(db.String(64))
    source_status = db.Column(db.String(100))
    source_metadata = db.Column(db.JSON, nullable=False, default=dict, server_default='{}')
    analysis = db.Column(db.JSON)
    radar_metadata = db.Column(db.JSON().with_variant(JSONB(), 'postgresql'), nullable=False, default=dict, server_default='{}')
    first_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.UniqueConstraint('radar_id', 'fingerprint', name='uq_results_radar_fingerprint'),
        db.Index('ix_results_radar_first_seen', 'radar_id', 'first_seen_at'),
        db.CheckConstraint('ai_score >= 0 AND ai_score <= 100', name='score_range'),
        db.CheckConstraint("discovery_status IS NULL OR discovery_status IN ('NEW','UPDATED','UNCHANGED')",
                           name='valid_discovery_status'),
        db.CheckConstraint("review_status IS NULL OR review_status IN ('PENDING','APPROVED','REJECTED')",
                           name='valid_review_status'),
    )
