from app.db.extensions import db
from app.db.models import utcnow


class ResultObservation(db.Model):
    """Append-only per-run decisions preserve versions, rejections and rediscoveries."""
    __tablename__ = 'result_observations'
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('search_runs.id'), nullable=False, index=True)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id'), nullable=False, index=True)
    state = db.Column(db.String(32), nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
