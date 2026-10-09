"""Durable listing-to-business handoff. All functions require an explicit caller.

Index UNCHANGED is intentionally unrelated to processing completion. Completion
of an accepted candidate is committed with its Result/ResultObservation.
"""
from datetime import timedelta

from app.db.extensions import db
from app.db.models import Radar, Result, SearchRun, utcnow
from app.db.models.pmmp_listing_index import PmmpListingIndex as Listing

from .service import MarketsRadarAgent

POLICY_VERSION = 'archeritage-r' + MarketsRadarAgent.rules_version
PENDING = 'PENDING_PROCESSING'
PROCESSING = 'PROCESSING'
PROCESSED = 'PROCESSED'
RETRY = 'FAILED_RETRYABLE'
REJECTED = 'REJECTED'
TERMINAL = (PROCESSED, REJECTED)


def listing_gate(listing):
    """Existing scope gate plus an unambiguous listing deadline, before HTTP/cap."""
    from app.core.validation import today_in_morocco
    from .parser import parse_date
    from .pmmp_index_backfill import cheap_listing_prefilter
    deadline = parse_date(listing.deadline)
    if deadline is not None and deadline < today_in_morocco():
        return {'decision': 'reject', 'reason_code': 'closed_or_expired'}
    return cheap_listing_prefilter(listing)


def recover_legacy(snapshot_for):
    """Use exact successful business snapshots; otherwise queue plausible rows.

    Aggregate backfill counters and technical fingerprints are not policy proof.
    No special casing of run 54: its unproven rows follow the same safe rules.
    Called by the next normal index-mode run, never at migration/startup.
    """
    from app.core.dedup import discovery_snapshot
    from .pmmp_listing_index import listing_from_record
    radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == 'RADAR_1_MARKETS'))
    results = db.session.scalars(db.select(Result).where(Result.radar_id == radar_id)).all()
    evidence = {}
    for result in results:
        metadata = (result.source_metadata or {}).get('metadata') or {}
        snapshot = metadata.get('discovery_snapshot')
        # A credible fallback is persisted, but still needs official verification.
        memory = (result.source_metadata or {}).get('agent_memory') or {}
        if (result.analysis and snapshot and memory.get('rules_version') == MarketsRadarAgent.rules_version and
                (result.radar_metadata or {}).get('resolution_state') != 'UNVERIFIED_BUT_CREDIBLE'):
            state = REJECTED if result.analysis.get('relevant') is False else PROCESSED
            evidence.setdefault(snapshot.get('url'), []).append((snapshot, result.updated_at, state))
    counts = dict(queued=0, restored=0, rejected=0)
    for row in db.session.scalars(db.select(Listing).where(Listing.processing_state.is_(None))):
        listing = listing_from_record(row)
        proof = False
        proof_at = None
        proof_state = PROCESSED
        try:
            snapshot = discovery_snapshot(snapshot_for(listing))
            for old, stamp, state in evidence.get(snapshot.get('url'), []):
                # A policy save preceding this index version cannot certify it.
                changed_at = row.last_changed_at
                if stamp is not None and stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=utcnow().tzinfo)
                if changed_at.tzinfo is None:
                    changed_at = changed_at.replace(tzinfo=utcnow().tzinfo)
                complete = all(snapshot.get(key) for key in ('title', 'reference', 'institution', 'deadline', 'url'))
                if complete and old == snapshot and stamp is not None and stamp >= changed_at:
                    proof = True
                    proof_at = stamp
                    proof_state = state
                    break
        except (ValueError, TypeError):
            pass  # Incomplete parser evidence cannot certify successful processing.
        if proof:
            record_terminal(row, proof_state, 'recovered_exact_business_snapshot')
            row.evaluated_at = proof_at
            counts['restored'] += 1
        else:
            gate = listing_gate(listing)
            if gate['decision'] == 'reject':
                record_terminal(row, REJECTED, 'recovery_prefilter:' + str(gate['reason_code']))
                counts['rejected'] += 1
            else:
                row.processing_state = PENDING
                row.processing_reason = 'legacy_without_successful_processing_evidence'
                counts['queued'] += 1
    db.session.commit()
    return counts


def queue_reconciliation_refresh(scan_started_at, hours):
    """Refresh previously successful active board notices, within the normal cap.

    Rejected noise is not blindly reprocessed. Existing review decisions remain
    owned by ResultWorkflowService; refreshing evidence cannot itself reopen them.
    """
    from .pmmp_listing_index import listing_from_record
    count = 0
    rows = db.session.scalars(db.select(Listing).where(
        Listing.processing_state == PROCESSED,
        Listing.last_seen_at >= scan_started_at,
        db.or_(Listing.evaluated_at.is_(None),
               Listing.evaluated_at <= utcnow() - timedelta(hours=hours))))
    for row in rows:
        listing = listing_from_record(row)
        if listing.detail_url and listing_gate(listing)['decision'] == 'continue':
            row.processing_state = PENDING
            row.processing_reason = 'reconciliation_official_detail_refresh'
            count += 1
    db.session.commit()
    return count


def record_terminal(row, state, reason):
    row.processing_state = state
    row.evaluated_fingerprint = row.fingerprint
    row.evaluated_at = utcnow()
    row.policy_version = POLICY_VERSION
    row.processing_reason = reason[:255]
    row.processing_run_id = None
    row.processing_started_at = None


def release_abandoned():
    """Only an inactive owner's claims may be reclaimed, never another live run."""
    active = db.select(SearchRun.id).where(SearchRun.status.in_(('initialized', 'running')),
                                         SearchRun.started_at <= Listing.processing_started_at).correlate(Listing)
    db.session.execute(db.update(Listing).where(
        Listing.processing_state == PROCESSING,
        db.or_(Listing.processing_run_id.is_(None), Listing.processing_run_id.not_in(active))
    ).values(processing_state=RETRY, processing_run_id=None, processing_started_at=None,
             processing_reason='interrupted_owner_run'))
    db.session.commit()


def pending_rows():
    # New work wins over repeated transient failures; older work wins within a tier.
    return db.session.scalars(db.select(Listing).where(db.or_(
        Listing.processing_state.in_((PENDING, RETRY)),
        db.and_(Listing.processing_state.in_(TERMINAL), db.or_(
            Listing.evaluated_fingerprint.is_(None),
            Listing.policy_version.is_(None),
            Listing.evaluated_fingerprint != Listing.fingerprint,
            Listing.policy_version != POLICY_VERSION))
    )).order_by(Listing.processing_attempts, Listing.first_seen_at, Listing.id)).all()


def claim(row_id, fingerprint, run_id):
    status = db.session.scalar(db.select(SearchRun.status).where(SearchRun.id == run_id).with_for_update())
    if status != 'running':
        return False
    row = db.session.get(Listing, row_id)
    if row is None or row.fingerprint != fingerprint or row.processing_state == PROCESSING:
        return False
    # CAS guards against competing workers and a changed listing version.
    claimed = db.session.execute(db.update(Listing).where(
        Listing.id == row_id, Listing.fingerprint == fingerprint,
        Listing.processing_state == row.processing_state,
    ).values(processing_state=PROCESSING, processing_run_id=run_id,
             processing_started_at=utcnow(), processing_attempts=Listing.processing_attempts + 1,
             processing_reason='business_processing_started')).rowcount
    db.session.commit()  # Durable lease before any external HTTP.
    return bool(claimed)


def can_persist(candidate, run_id):
    """Lock the lease through Result persistence; discard a superseded handoff."""
    token = (getattr(candidate, 'metadata', None) or {}).get('pmmp_processing')
    if not token:
        return True
    status = db.session.scalar(db.select(SearchRun.status).where(SearchRun.id == run_id).with_for_update())
    if status != 'running':
        return False
    row = db.session.scalar(db.select(Listing).where(Listing.id == token['id']).with_for_update()
                            .execution_options(populate_existing=True))
    return bool(row is not None and row.processing_state == PROCESSING
                and row.processing_run_id == run_id and row.fingerprint == token['fingerprint'])


def finish(row_id, fingerprint, run_id, state, reason):
    """Stage completion in the caller's transaction; never commit here."""
    row = db.session.scalar(db.select(Listing).where(
        Listing.id == row_id, Listing.fingerprint == fingerprint,
        Listing.processing_state == PROCESSING, Listing.processing_run_id == run_id
    ).with_for_update().execution_options(populate_existing=True))
    if row is None:
        return False  # An older worker cannot acknowledge a newer version/owner.
    if state in TERMINAL:
        record_terminal(row, state, reason)
    else:
        row.processing_state = state
        row.processing_reason = reason[:255]
        row.processing_run_id = None
        row.processing_started_at = None
    return True


def acknowledge_candidate(candidate, run_id, result_state):
    token = (getattr(candidate, 'metadata', None) or {}).get('pmmp_processing')
    if token:
        # Persisted fallbacks stay retryable until official evidence is available.
        state = (RETRY if getattr(candidate, 'resolution_state', None) == 'UNVERIFIED_BUT_CREDIBLE'
                 else REJECTED if str(result_state) == 'rejected' else PROCESSED)
        finish(token['id'], token['fingerprint'], run_id, state, 'persisted:' + str(result_state))


def release_run(run_id, reason='business_persistence_not_completed'):
    db.session.execute(db.update(Listing).where(
        Listing.processing_state == PROCESSING, Listing.processing_run_id == run_id
    ).values(processing_state=RETRY, processing_run_id=None,
             processing_started_at=None, processing_reason=reason))
    db.session.commit()


def reconciliation_due(radar_id, hours):
    # No scheduler is installed. Only a user-triggered normal run checks this clock.
    rows = db.session.scalars(db.select(SearchRun).where(
        SearchRun.radar_id == radar_id, SearchRun.status == 'completed'
    ).order_by(SearchRun.started_at.desc())).all()
    for run in rows:
        metrics = (run.run_metadata or {}).get('collector_metrics') or {}
        if (metrics.get('pmmp_sync_mode') == 'reconciliation'
                and metrics.get('pmmp_sync_complete') is True):
            stamp = run.finished_at or run.started_at
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=utcnow().tzinfo)
            return utcnow() - stamp >= timedelta(hours=hours)
    return True
