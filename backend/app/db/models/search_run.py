from app.db.extensions import db
from app.db.models import utcnow
from app.core.agent_schemas import Stage
from sqlalchemy.dialects.postgresql import JSONB


class SearchRun(db.Model):
    __tablename__ = 'search_runs'
    id = db.Column(db.Integer, primary_key=True)
    radar_id = db.Column(db.Integer, db.ForeignKey('radars.id'), nullable=False)
    status = db.Column(db.String(24), nullable=False, default='initialized')
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at = db.Column(db.DateTime(timezone=True))
    new_results_count = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text)
    agent_name = db.Column(db.String(100))
    current_stage = db.Column(db.String(24), nullable=False, default=Stage.INITIALIZING, server_default='INITIALIZING')
    stage_history = db.Column(db.JSON, nullable=False, default=list, server_default='[]')
    trigger_type = db.Column(db.String(24), nullable=False, default='manual', server_default='manual')
    triggered_by = db.Column(db.BigInteger)
    launched_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    launcher = db.relationship('User', foreign_keys=[launched_by_user_id])
    candidates_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    duplicate_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    analyzed_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    updated_results_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    rejected_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    candidate_errors_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    input_tokens = db.Column(db.BigInteger, nullable=False, default=0, server_default='0')
    output_tokens = db.Column(db.BigInteger, nullable=False, default=0, server_default='0')
    cached_tokens = db.Column(db.BigInteger, nullable=False, default=0, server_default='0')
    ai_calls = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    direct_fetches = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    search_calls = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    resolution_search_calls = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    estimated_ai_cost = db.Column(db.Numeric(18, 8))
    error_kind = db.Column(db.String(40))
    manual_review_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    accepted_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    queries_executed = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    candidates_after_rules = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    run_metadata = db.Column(db.JSON().with_variant(JSONB(), 'postgresql'), nullable=False, default=dict, server_default='{}')
    __table_args__ = (
        db.Index('ix_search_runs_radar_started', 'radar_id', 'started_at'),
        db.Index('uq_search_runs_active_radar', 'radar_id', unique=True,
                 postgresql_where=db.text("status IN ('initialized', 'running')"),
                 sqlite_where=db.text("status IN ('initialized', 'running')")),
        db.CheckConstraint('new_results_count >= 0', name='nonnegative_results'),
        db.CheckConstraint("status IN ('initialized', 'running', 'completed', 'failed')", name='valid_status'),
    )
