from app.db.extensions import db
from app.db.models import utcnow


class PmmpListingIndex(db.Model):
    """Durable lightweight PMMP listing memory. Not a Radar business result."""

    __tablename__ = 'pmmp_listing_index'
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(120), nullable=False, default='marchespublics.gov.ma')
    consultation_id = db.Column(db.String(32), index=True)
    organization = db.Column(db.String(32))
    detail_url = db.Column(db.Text)
    reference = db.Column(db.String(255))
    buyer = db.Column(db.Text)
    title = db.Column(db.Text)
    publication_date = db.Column(db.String(32))
    deadline = db.Column(db.String(32))
    procedure = db.Column(db.String(120))
    category = db.Column(db.String(64))
    location = db.Column(db.String(255))
    fingerprint = db.Column(db.String(64), nullable=False)
    identity_key = db.Column(db.String(64), nullable=False, unique=True)
    first_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    __table_args__ = (
        db.Index('ix_pmmp_listing_index_source_consultation', 'source', 'consultation_id'),
        db.Index(
            'uq_pmmp_listing_index_source_consultation',
            'source', 'consultation_id',
            unique=True,
            postgresql_where=db.text('consultation_id IS NOT NULL'),
            sqlite_where=db.text('consultation_id IS NOT NULL'),
        ),
    )
