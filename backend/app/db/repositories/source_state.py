from datetime import timedelta, timezone

from app.db.extensions import db
from app.db.models import SourceState, utcnow


class SourceStateService:
    def __init__(self, radar_code=''):
        self.radar_code = radar_code

    def _row(self, url):
        return db.session.scalar(db.select(SourceState).where(
            SourceState.source_url == url, SourceState.radar_code == self.radar_code))

    def get(self, url):
        row = self._row(url)
        return {} if row is None else {
            'content_hash': row.content_hash, 'etag': row.etag, 'last_modified': row.last_modified,
            'last_checked_at': row.last_checked_at, 'last_changed_at': row.last_changed_at,
            'health': row.health,
        }

    def refresh_due(self, url, days):
        state = self.get(url)
        checked = state.get('last_checked_at')
        if checked is not None and checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return checked is None or checked <= utcnow() - timedelta(days=max(0, days))

    def record(self, result):
        row = self._row(result.source.index_url)
        if row is None:
            row = SourceState(source_url=result.source.index_url, source_name=result.source.name,
                              radar_code=self.radar_code)
            db.session.add(row)
        changed = result.status == 'CHANGED'
        row.content_hash = result.content_hash or row.content_hash
        row.etag = result.etag or row.etag
        row.last_modified = result.last_modified or row.last_modified
        row.last_checked_at = utcnow()
        row.last_changed_at = utcnow() if changed or row.last_changed_at is None else row.last_changed_at
        row.health = 'HEALTHY' if result.status in {'CHANGED', 'UNCHANGED', 'NOT_MODIFIED'} else result.status
        row.last_status_code = result.error_code or (304 if result.status == 'NOT_MODIFIED' else 200)
        db.session.flush()
