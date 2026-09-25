from app.db.extensions import db
from app.db.models import utcnow


class SourceState(db.Model):
    __tablename__ = 'source_states'
    id = db.Column(db.Integer, primary_key=True)
    radar_code = db.Column(db.String(40), nullable=False, default='', server_default='')
    source_name = db.Column(db.String(200), nullable=False)
    source_url = db.Column(db.Text, nullable=False)
    __table_args__ = (db.UniqueConstraint('radar_code', 'source_url', name='uq_source_states_radar_url'),)
    etag = db.Column(db.String(500))
    last_modified = db.Column(db.String(200))
    content_hash = db.Column(db.String(64))
    last_checked_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_changed_at = db.Column(db.DateTime(timezone=True))
    health = db.Column(db.String(20), nullable=False, default='HEALTHY')
    last_status_code = db.Column(db.Integer)
