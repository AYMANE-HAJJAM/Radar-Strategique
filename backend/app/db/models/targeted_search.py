from app.db.extensions import db
from app.db.models import utcnow
from sqlalchemy.dialects.postgresql import JSONB


JSON = db.JSON().with_variant(JSONB(), 'postgresql')


class TargetedSearchSession(db.Model):
    __tablename__ = 'targeted_search_sessions'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    original_prompt = db.Column(db.Text, nullable=False)
    creator_user_id = db.Column(db.BigInteger, nullable=False, index=True)
    current_version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(16), nullable=False, default='DRAFT', index=True)
    last_run_at = db.Column(db.DateTime(timezone=True))
    run_summary = db.Column(JSON, nullable=False, default=dict, server_default='{}')
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.CheckConstraint(
        "status IN ('DRAFT','CONFIRMED','RUNNING','COMPLETED','FAILED','CANCELLED')",
        name='valid_targeted_search_status'),)


class TargetedSearchBriefVersion(db.Model):
    __tablename__ = 'targeted_search_brief_versions'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('targeted_search_sessions.id', ondelete='CASCADE'), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    brief = db.Column(JSON, nullable=False)
    refinement_prompt = db.Column(db.Text)
    created_by_user_id = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint('session_id', 'version', name='uq_targeted_brief_session_version'),
                      db.Index('ix_targeted_brief_versions_session_id', 'session_id'))


class TargetedSearchResultLink(db.Model):
    __tablename__ = 'targeted_search_result_links'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('targeted_search_sessions.id', ondelete='CASCADE'), nullable=False)
    brief_version = db.Column(db.Integer, nullable=False)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id', ondelete='CASCADE'), nullable=False)
    match_status = db.Column(db.String(16), nullable=False)
    review_status = db.Column(db.String(16), nullable=False, default='PENDING', index=True)
    relevance_score = db.Column(db.Integer, nullable=False)
    content_fingerprint = db.Column(db.String(64), nullable=False)
    match_reason = db.Column(db.Text)
    first_matched_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_matched_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.ForeignKeyConstraint(('session_id','brief_version'),
            ('targeted_search_brief_versions.session_id','targeted_search_brief_versions.version'),
            name='fk_targeted_result_brief_version',ondelete='CASCADE'),
        db.UniqueConstraint('session_id', 'result_id', name='uq_targeted_session_result'),
        db.CheckConstraint("match_status IN ('NEW','KNOWN','UPDATED')", name='valid_targeted_match_status'),
        db.CheckConstraint("review_status IN ('PENDING','PERTINENT','REJECTED')", name='valid_targeted_review_status'),
        db.CheckConstraint('relevance_score >= 0 AND relevance_score <= 100', name='targeted_relevance_score_range'),
        db.Index('ix_targeted_result_links_session_id', 'session_id'),
        db.Index('ix_targeted_result_links_result_id', 'result_id'),
    )


class TargetedSearchFeedback(db.Model):
    __tablename__ = 'targeted_search_feedback'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('targeted_search_sessions.id', ondelete='CASCADE'), nullable=False)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id', ondelete='CASCADE'))
    brief_version = db.Column(db.Integer, nullable=False)
    decision = db.Column(db.String(24), nullable=False)
    reason = db.Column(db.Text)
    user_id = db.Column(db.BigInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.ForeignKeyConstraint(('session_id','brief_version'),
            ('targeted_search_brief_versions.session_id','targeted_search_brief_versions.version'),
            name='fk_targeted_feedback_brief_version',ondelete='CASCADE'),
        db.Index('ix_targeted_feedback_session_id', 'session_id'),
        db.Index('ix_targeted_feedback_result_id', 'result_id'),
        db.Index('ix_targeted_feedback_user_id', 'user_id'),
    )
