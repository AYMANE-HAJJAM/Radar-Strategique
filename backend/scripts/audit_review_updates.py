"""Read-only inspection of Guelmim / Sidi Ifni review and reopen events."""
import json
from pathlib import Path

from sqlalchemy import text
from app import create_app
from app.db.extensions import db
from app.db.models import Result, ResultAuditEvent, ResultObservation, MarketReview
from app.core.review_changes import legacy_review_snapshot, business_changes, business_snapshot


def main():
    app = create_app({'SQLALCHEMY_ENGINE_OPTIONS': {'connect_args': {'connect_timeout': 10}}})
    with app.app_context():
        # Database enforces read-only access even if this script is extended later.
        db.session.execute(text('SET TRANSACTION READ ONLY'))
        rows = db.session.scalars(db.select(Result).where(Result.radar_id == 1,
            db.or_(Result.title.ilike('%guelmim%'), Result.title.ilike('%sidi ifni%')))).all()
        report = []
        for row in rows:
            events = db.session.scalars(db.select(ResultAuditEvent).where(
                ResultAuditEvent.result_id == row.id).order_by(ResultAuditEvent.id)).all()
            observations = db.session.scalars(db.select(ResultObservation).where(
                ResultObservation.result_id == row.id).order_by(ResultObservation.id)).all()
            reviews = db.session.scalars(db.select(MarketReview).where(
                MarketReview.result_id == row.id).order_by(MarketReview.id)).all()
            reopens = []
            for event in events:
                if event.event_type != 'REOPENED':
                    continue
                before = [o for o in observations if o.created_at < event.created_at]
                after = [o for o in observations if o.created_at >= event.created_at]
                changes = business_changes(legacy_review_snapshot(before[-1].snapshot),
                    legacy_review_snapshot(after[0].snapshot)) if before and after else None
                reopens.append({'at': event.created_at.isoformat(),
                    'previous_review': event.event_metadata.get('previous_review_status'),
                    'detected_fields': event.event_metadata.get('changed_fields'),
                    'business_changes': changes,
                    'materially_justified': bool(changes) if changes is not None else None})
            report.append({'id': row.id, 'title': row.title, 'reference': row.reference,
                'review_status': row.review_status, 'discovery_status': row.discovery_status,
                'update_reason': row.update_reason, 'current_business_fields': business_snapshot(row),
                'reviews': [{'decision': r.decision, 'at': r.reviewed_at.isoformat()} for r in reviews],
                'reopens': reopens})
        db.session.rollback()
        Path('docs/REVIEW_UPDATE_CURRENT_AUDIT.json').write_text(
            json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True, default=str, indent=2))


if __name__ == '__main__':
    main()
