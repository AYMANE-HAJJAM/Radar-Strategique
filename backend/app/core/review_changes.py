"""Business-only review diffs. Discovery identity and content hashes stay separate."""
import html
import json
import re
from decimal import Decimal, InvalidOperation

from app.core.dedup import normalize_text


CORE_FIELDS = ('title', 'institution', 'reference', 'publication_date', 'deadline', 'source_status')
PROCUREMENT_FIELDS = (
    'procedure_type', 'location_evidence', 'location', 'city_region', 'territory',
    'deadline_time', 'estimated_amount', 'estimated_currency', 'estimated_amount_tax_mode',
    'estimated_lots', 'provisional_bond_amount', 'provisional_bond_currency',
    'competition_prize_amount', 'competition_prize_currency', 'eligibility_conditions',
    'competition_regulation_available', 'document_types',
)
NUMERIC_FIELDS = {'estimated_amount', 'provisional_bond_amount', 'competition_prize_amount'}


def normalized(value, field=None):
    if value is None or value == '':
        return None
    if field == 'competition_regulation_available' and value is False:
        return None
    if field in NUMERIC_FIELDS:
        try:
            return str(Decimal(str(value)).normalize())
        except InvalidOperation:
            pass
    if isinstance(value, dict):
        return {key: normalized(item, key) for key, item in sorted(value.items())} or None
    if isinstance(value, list):
        # Lot / document ordering is presentation metadata, not a tender amendment.
        return sorted((normalized(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True)) or None
    if isinstance(value, str):
        value = html.unescape(re.sub(r'<[^>]+>', ' ', value))
        value = value.translate(str.maketrans({'\u2019': "'", '\u2018': "'", '\u2013': '-', '\u2014': '-'}))
        return normalize_text(value) or None
    return value


def business_snapshot(row):
    values = {field: getattr(row, field, None) for field in CORE_FIELDS}
    for field in ('deadline', 'publication_date'):
        values[field] = values[field].isoformat() if values[field] else None
    values.update({field: (row.radar_metadata or {}).get(field) for field in PROCUREMENT_FIELDS})
    return values


def candidate_snapshot(candidate):
    values = {field: getattr(candidate, field, None) for field in CORE_FIELDS}
    for field in ('deadline', 'publication_date'):
        values[field] = values[field].isoformat() if values[field] else None
    fields = candidate.radar_fields()
    values.update({field: fields.get(field) for field in PROCUREMENT_FIELDS})
    return values


def business_changes(before, after):
    # Missing keys in old audit snapshots mean unknown, rather than an invented old value.
    # An estimate placeholder can carry MAD/TTC without any amount. Enriching
    # those labels does not change the opportunity's commercial value.
    ignored = set()
    if before.get('estimated_amount') is None and after.get('estimated_amount') is None and not (
            before.get('estimated_lots') or after.get('estimated_lots')):
        ignored.update(('estimated_currency', 'estimated_amount_tax_mode'))
    return [{'field': field, 'before': before[field], 'after': after.get(field)}
            for field in (*CORE_FIELDS, *PROCUREMENT_FIELDS)
            if field not in ignored and field in before and
            normalized(before[field], field) != normalized(after.get(field), field)]


def legacy_review_snapshot(snapshot):
    values = {field: snapshot[field] for field in CORE_FIELDS if field in snapshot}
    metadata = snapshot.get('radar_metadata') or {}
    values.update({field: metadata[field] for field in PROCUREMENT_FIELDS if field in metadata})
    return values


def review_contexts(rows):
    """Fetch history once per result page, rather than issuing queries per cell."""
    from app.db.extensions import db
    from app.db.models import MarketReview, ResultAuditEvent

    ids = [row.id for row in rows if row.review_status == 'PENDING']
    reviews, events = {}, {}
    if ids:
        for review in db.session.scalars(db.select(MarketReview).where(MarketReview.result_id.in_(ids))
                                        .order_by(MarketReview.id.desc())):
            reviews.setdefault(review.result_id, review)
        for event in db.session.scalars(db.select(ResultAuditEvent).where(
                ResultAuditEvent.result_id.in_(ids), ResultAuditEvent.event_type.in_(('APPROVED', 'REJECTED'))
        ).order_by(ResultAuditEvent.id.desc())):
            events.setdefault(event.result_id, event)
    return {row.id: _review_context(row, reviews.get(row.id), events.get(row.id)) for row in rows}


def review_context(row):
    return review_contexts([row])[row.id]


def _review_context(row, review, event):
    """Only report persisted decisions and diffs backed by recorded values."""
    state = review.decision.upper() if review else event.event_type if event else None
    before = None
    if review:
        before = review.snapshot.get('business_snapshot') or legacy_review_snapshot(review.snapshot)
    elif event:
        before = (event.event_metadata or {}).get('business_snapshot')
    changes = business_changes(before, business_snapshot(row)) if before is not None else []
    reopened = row.review_status == 'PENDING' and state in {'APPROVED', 'REJECTED'}
    if reopened and not changes and before is None:
        changes = (row.update_reason or {}).get('changes') or []
    return {'previous_review_status': state if reopened else None,
            'review_changes': changes if reopened else [],
            'review_changes_available': bool(before is not None) if reopened else False}
