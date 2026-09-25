from app.db.extensions import db
from app.db.models import utcnow


class MarketReview(db.Model):
    """Append-only human decisions for a specific Radar 1 evidence version."""
    __tablename__ = 'market_reviews'
    id = db.Column(db.Integer, primary_key=True)
    result_id = db.Column(db.Integer, db.ForeignKey('results.id'), nullable=False, index=True)
    content_hash = db.Column(db.String(64), nullable=False)
    decision = db.Column(db.String(16), nullable=False)
    reviewed_by = db.Column(db.BigInteger, nullable=False)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    previous_review_reason = db.Column(db.Text)
    snapshot = db.Column(db.JSON, nullable=False)
