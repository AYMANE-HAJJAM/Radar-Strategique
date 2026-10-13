"""Independent, leased, bounded PMMP listing refresh.

Separate from Radar business SearchRuns. A successful pass means the page/time
budget finished — not that the full catalogue was reconciled.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta, timezone
from time import monotonic
from uuid import uuid4

from flask import current_app, has_app_context

from app.db.extensions import db
from app.db.models import utcnow
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.db.models.pmmp_refresh_checkpoint import PmmpRefreshCheckpoint
from app.modules.radar1_markets.pmmp_listing_collector import (
    DUPLICATE, NEW, UNCHANGED, UPDATED, PmmpListingCollector,
    extract_page_state, page_signature_text,
)
from app.modules.radar1_markets.pmmp_listing_index import DurableListingIndex

CHECKPOINT_ID = 1
DEFAULT_FRONT = 5
DEFAULT_DEEP = 15
DEFAULT_MAX_SECONDS = 90
DEFAULT_LEASE_SECONDS = 180


class RefreshLeaseHeld(RuntimeError):
    """Another worker holds a valid refresh lease."""


def _aware(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass
class RefreshPassResult:
    acquired: bool
    lease_owner: str | None
    stop_reason: str
    pass_success: bool
    cycle_complete: bool
    pages: int
    new: int
    updated: int
    unchanged: int
    duplicates: int
    front_pages: int
    deep_pages: int
    cursor_page: int
    declared_pages: int | None
    error: str | None = None

    def to_dict(self):
        return {
            'acquired': self.acquired,
            'lease_owner': self.lease_owner,
            'stop_reason': self.stop_reason,
            'pass_success': self.pass_success,
            'cycle_complete': self.cycle_complete,
            'pages': self.pages,
            'new': self.new,
            'updated': self.updated,
            'unchanged': self.unchanged,
            'duplicates': self.duplicates,
            'front_pages': self.front_pages,
            'deep_pages': self.deep_pages,
            'cursor_page': self.cursor_page,
            'declared_pages': self.declared_pages,
            'error': self.error,
            'catalogue_reconciled': self.cycle_complete,
        }


def ensure_checkpoint():
    row = db.session.get(PmmpRefreshCheckpoint, CHECKPOINT_ID)
    if row is None:
        row = PmmpRefreshCheckpoint(id=CHECKPOINT_ID, status='idle', updated_at=utcnow())
        db.session.add(row)
        db.session.commit()
    return row


def _config(name, default):
    if has_app_context():
        return int(current_app.config.get(name, default))
    return default


def _lease_seconds():
    return _config('RADAR1_PMMP_REFRESH_LEASE_SECONDS', DEFAULT_LEASE_SECONDS)


def _lease_expired(row, now):
    if row.status != 'running':
        return True
    lease_until = _aware(row.lease_until)
    heartbeat = _aware(row.heartbeat_at)
    now = _aware(now)
    if lease_until is None or lease_until <= now:
        if heartbeat is None:
            return True
        ttl = timedelta(seconds=_lease_seconds())
        return heartbeat <= now - ttl
    return False


def acquire_lease(*, force_expired=False):
    """CAS acquire. force_expired only uses the expired-lease predicate (S4)."""
    ensure_checkpoint()
    row = db.session.get(PmmpRefreshCheckpoint, CHECKPOINT_ID)
    now = utcnow()
    if force_expired:
        if row.status != 'running' or not _lease_expired(row, now):
            return None
    elif row.status not in ('idle', 'failed') and not _lease_expired(row, now):
        return None
    owner = uuid4().hex
    lease_until = now + timedelta(seconds=_lease_seconds())
    # Re-check with CAS on status/owner snapshot to avoid races across processes.
    previous_owner = row.lease_owner
    previous_status = row.status
    updated = db.session.execute(
        db.update(PmmpRefreshCheckpoint).where(
            PmmpRefreshCheckpoint.id == CHECKPOINT_ID,
            PmmpRefreshCheckpoint.status == previous_status,
            db.or_(
                PmmpRefreshCheckpoint.lease_owner.is_(None),
                PmmpRefreshCheckpoint.lease_owner == previous_owner,
            ),
        ).values(
            status='running',
            lease_owner=owner,
            lease_until=lease_until,
            heartbeat_at=now,
            last_started_at=now,
            last_error=None,
            updated_at=now,
            last_new=0,
            last_updated=0,
            last_unchanged=0,
            last_pages=0,
            last_stop_reason=None,
        ).execution_options(synchronize_session=False)
    ).rowcount
    db.session.commit()
    if not updated:
        return None
    return owner


def release_expired_lease():
    """Operator helper: same CAS as reclaim, never kills a live lease."""
    owner = acquire_lease(force_expired=True)
    if owner is None:
        return False
    # Immediately park as idle without crawling — operator asked only to clear dead lock.
    now = utcnow()
    db.session.execute(
        db.update(PmmpRefreshCheckpoint).where(
            PmmpRefreshCheckpoint.id == CHECKPOINT_ID,
            PmmpRefreshCheckpoint.lease_owner == owner,
        ).values(
            status='idle',
            lease_owner=None,
            lease_until=None,
            last_finished_at=now,
            last_error='force_released_expired_lease',
            updated_at=now,
        )
    )
    db.session.commit()
    return True


def _heartbeat(owner):
    now = utcnow()
    db.session.execute(
        db.update(PmmpRefreshCheckpoint).where(
            PmmpRefreshCheckpoint.id == CHECKPOINT_ID,
            PmmpRefreshCheckpoint.lease_owner == owner,
            PmmpRefreshCheckpoint.status == 'running',
        ).values(
            heartbeat_at=now,
            lease_until=now + timedelta(seconds=_lease_seconds()),
            updated_at=now,
        )
    )


def _finish(owner, *, status, stop_reason, counts, pages, cursor_page, page_state,
            page_signature, declared_pages, declared_results, cycle_complete, error=None):
    now = utcnow()
    values = dict(
        status=status,
        lease_owner=None if status != 'running' else owner,
        lease_until=None if status != 'running' else (now + timedelta(seconds=_lease_seconds())),
        heartbeat_at=now if status == 'running' else None,
        last_finished_at=now,
        last_stop_reason=stop_reason,
        last_new=counts.get(NEW, 0),
        last_updated=counts.get(UPDATED, 0),
        last_unchanged=counts.get(UNCHANGED, 0),
        last_pages=pages,
        cursor_page=cursor_page,
        page_state=page_state,
        page_signature=page_signature,
        declared_pages=declared_pages,
        declared_results=declared_results,
        last_error=(error or '')[:255] or None,
        updated_at=now,
        cycle_complete=bool(cycle_complete),
    )
    if status == 'idle' and not error:
        values['last_success_at'] = now
    if cycle_complete:
        values['last_cycle_completed_at'] = now
        values['cursor_page'] = 0
        values['page_state'] = None
        values['page_signature'] = None
        values['cycle_new'] = 0
        values['cycle_updated'] = 0
        values['cycle_unchanged'] = 0
        values['cycle_pages'] = 0
    else:
        row = db.session.get(PmmpRefreshCheckpoint, CHECKPOINT_ID)
        values['cycle_new'] = (row.cycle_new or 0) + counts.get(NEW, 0)
        values['cycle_updated'] = (row.cycle_updated or 0) + counts.get(UPDATED, 0)
        values['cycle_unchanged'] = (row.cycle_unchanged or 0) + counts.get(UNCHANGED, 0)
        values['cycle_pages'] = (row.cycle_pages or 0) + pages
    db.session.execute(
        db.update(PmmpRefreshCheckpoint).where(
            PmmpRefreshCheckpoint.id == CHECKPOINT_ID,
            PmmpRefreshCheckpoint.lease_owner == owner,
        ).values(**values)
    )
    db.session.commit()


def refresh_status():
    row = ensure_checkpoint()
    indexed = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
    pending = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex).where(
        db.or_(
            PmmpListingIndex.processing_state.is_(None),
            PmmpListingIndex.processing_state.in_(
                ('PENDING_PROCESSING', 'FAILED_RETRYABLE')),
        )
    )) or 0
    now = utcnow()
    lease_valid = (
        row.status == 'running'
        and row.lease_owner
        and not _lease_expired(row, now)
    )
    return {
        'indexed': indexed,
        'pending_business': pending,
        'status': row.status,
        'lease_owner': row.lease_owner,
        'lease_until': row.lease_until.isoformat() if row.lease_until else None,
        'heartbeat_at': row.heartbeat_at.isoformat() if row.heartbeat_at else None,
        'lease_held': lease_valid,
        'cursor_page': row.cursor_page,
        'declared_pages': row.declared_pages,
        'declared_results': row.declared_results,
        'cycle_complete': bool(row.cycle_complete),
        'last_cycle_completed_at': (
            row.last_cycle_completed_at.isoformat() if row.last_cycle_completed_at else None),
        'last_pass_success_at': row.last_success_at.isoformat() if row.last_success_at else None,
        'last_started_at': row.last_started_at.isoformat() if row.last_started_at else None,
        'last_finished_at': row.last_finished_at.isoformat() if row.last_finished_at else None,
        'last_pass': {
            'new': row.last_new,
            'updated': row.last_updated,
            'unchanged': row.last_unchanged,
            'pages': row.last_pages,
            'stop_reason': row.last_stop_reason,
        },
        'cycle_counters': {
            'new': row.cycle_new,
            'updated': row.cycle_updated,
            'unchanged': row.cycle_unchanged,
            'pages': row.cycle_pages,
        },
        'last_error': row.last_error,
        'pass_success_means': 'page_or_time_budget_finished',
        'catalogue_reconciled_means': 'deep_cycle_wrapped_declared_pages',
    }


def run_refresh(*, http=None, front_pages=None, deep_pages=None, max_seconds=None,
                delay_seconds=0.35, force_expired_lease=False):
    """Bounded front + deep refresh under a DB lease."""
    front_pages = front_pages if front_pages is not None else _config(
        'RADAR1_PMMP_REFRESH_FRONT_PAGES', DEFAULT_FRONT)
    deep_pages = deep_pages if deep_pages is not None else _config(
        'RADAR1_PMMP_REFRESH_DEEP_PAGES', DEFAULT_DEEP)
    max_seconds = max_seconds if max_seconds is not None else _config(
        'RADAR1_PMMP_REFRESH_MAX_SECONDS', DEFAULT_MAX_SECONDS)

    owner = acquire_lease(force_expired=force_expired_lease)
    if owner is None:
        status = refresh_status()
        raise RefreshLeaseHeld(
            f"Refresh lease held by {status.get('lease_owner')}; "
            f"heartbeat={status.get('heartbeat_at')}")

    started = monotonic()
    counts = {NEW: 0, UPDATED: 0, UNCHANGED: 0, DUPLICATE: 0}
    front_done = 0
    deep_done = 0
    stop_reason = 'budget'
    cycle_complete = False
    error = None
    checkpoint = db.session.get(PmmpRefreshCheckpoint, CHECKPOINT_ID)
    cursor = checkpoint.cursor_page or 0
    deep_page_state = checkpoint.page_state
    page_state = deep_page_state
    page_signature = checkpoint.page_signature
    declared_pages = checkpoint.declared_pages
    declared_results = checkpoint.declared_results

    collector = PmmpListingCollector(http=http, delay_seconds=delay_seconds)
    index = DurableListingIndex()

    def still_budget():
        return monotonic() - started < max_seconds

    try:
        # --- Front pass: always fresh session from page 1 ---
        if front_pages > 0 and still_budget():
            front_done, front_stop, declared_pages, declared_results, _, _ = (
                _walk_segment(
                    collector, index, owner, counts,
                    mode='incremental',
                    max_pages=front_pages,
                    resume_page_state=None,
                    skip_classify_until_page=0,
                    started=started,
                    max_seconds=max_seconds,
                )
            )
            stop_reason = front_stop
            # Front does not advance the deep cursor or replace deep PAGESTATE.

        # --- Deep segment: resume from durable cursor (not front PAGESTATE) ---
        if deep_pages > 0 and still_budget() and stop_reason not in {'pagination_loop'}:
            deep_done, stop_reason, declared_pages, declared_results, page_state, page_signature, cursor, cycle_complete = (
                _walk_deep(
                    collector, index, owner, counts,
                    max_pages=deep_pages,
                    cursor_page=cursor,
                    resume_page_state=deep_page_state,
                    started=started,
                    max_seconds=max_seconds,
                    declared_pages=declared_pages,
                )
            )

        pass_success = error is None and stop_reason not in {'error'}
        _finish(
            owner, status='idle', stop_reason=stop_reason, counts=counts,
            pages=front_done + deep_done, cursor_page=cursor, page_state=page_state,
            page_signature=page_signature, declared_pages=declared_pages,
            declared_results=declared_results, cycle_complete=cycle_complete,
        )
        return RefreshPassResult(
            acquired=True, lease_owner=owner, stop_reason=stop_reason,
            pass_success=pass_success, cycle_complete=cycle_complete,
            pages=front_done + deep_done, new=counts[NEW], updated=counts[UPDATED],
            unchanged=counts[UNCHANGED], duplicates=counts[DUPLICATE],
            front_pages=front_done, deep_pages=deep_done, cursor_page=cursor,
            declared_pages=declared_pages, error=None,
        )
    except RefreshLeaseHeld:
        raise
    except Exception as exc:
        error = f'{type(exc).__name__}:{exc}'[:255]
        try:
            _finish(
                owner, status='failed', stop_reason='error', counts=counts,
                pages=front_done + deep_done, cursor_page=cursor, page_state=page_state,
                page_signature=page_signature, declared_pages=declared_pages,
                declared_results=declared_results, cycle_complete=False, error=error,
            )
        except Exception:
            db.session.rollback()
        return RefreshPassResult(
            acquired=True, lease_owner=owner, stop_reason='error',
            pass_success=False, cycle_complete=False,
            pages=front_done + deep_done, new=counts[NEW], updated=counts[UPDATED],
            unchanged=counts[UNCHANGED], duplicates=counts[DUPLICATE],
            front_pages=front_done, deep_pages=deep_done, cursor_page=cursor,
            declared_pages=declared_pages, error=error,
        )


class _BudgetStop(Exception):
    """Stop the collector loop when the shared time budget is exhausted."""


def _walk_segment(collector, index, owner, counts, *, mode, max_pages,
                  resume_page_state, skip_classify_until_page,
                  started, max_seconds):
    pages = 0
    stop = 'max_pages'
    declared_pages = None
    declared_results = None
    page_state = resume_page_state
    page_signature = None

    def on_page(page_num, html, rows, observations, decl_pages, decl_results):
        nonlocal pages, declared_pages, declared_results, page_state, page_signature, stop
        if page_num <= skip_classify_until_page:
            return
        for item in observations:
            counts[item.state] = counts.get(item.state, 0) + 1
        pages += 1
        declared_pages = decl_pages or declared_pages
        declared_results = decl_results or declared_results
        page_state = extract_page_state(html)
        page_signature = page_signature_text(html)
        db.session.commit()
        _heartbeat(owner)
        db.session.commit()
        if monotonic() - started >= max_seconds:
            stop = 'time_budget'
            raise _BudgetStop()

    index.on_page = lambda: None
    try:
        crawl = collector.collect(
            mode=mode, index=index, overlap_pages=_overlap(),
            max_pages=max_pages, on_page=on_page,
            resume_page_state=resume_page_state,
            skip_classify_until_page=skip_classify_until_page,
        )
        stop = crawl.stop_reason if stop == 'max_pages' else stop
        declared_pages = crawl.declared_pages or declared_pages
        declared_results = crawl.declared_results or declared_results
    except _BudgetStop:
        pass
    return pages, stop, declared_pages, declared_results, page_state, page_signature


def _walk_deep(collector, index, owner, counts, *, max_pages, cursor_page,
               resume_page_state, started, max_seconds, declared_pages):
    pages = 0
    stop = 'max_pages'
    declared_results = None
    page_state = resume_page_state
    page_signature = None
    cursor = cursor_page
    cycle_complete = False

    def on_page(page_num, html, rows, observations, decl_pages, decl_results):
        nonlocal pages, declared_pages, declared_results, page_state, page_signature, cursor, stop
        if page_num <= cursor_page:
            _heartbeat(owner)
            db.session.commit()
            return
        for item in observations:
            counts[item.state] = counts.get(item.state, 0) + 1
        pages += 1
        cursor = page_num
        declared_pages = decl_pages or declared_pages
        declared_results = decl_results or declared_results
        page_state = extract_page_state(html)
        page_signature = page_signature_text(html)
        row = db.session.get(PmmpRefreshCheckpoint, CHECKPOINT_ID)
        row.cursor_page = cursor
        row.page_state = page_state
        row.page_signature = page_signature
        row.declared_pages = declared_pages
        row.declared_results = declared_results
        db.session.commit()
        _heartbeat(owner)
        db.session.commit()
        if monotonic() - started >= max_seconds:
            stop = 'time_budget'
            raise _BudgetStop()

    index.on_page = lambda: None
    try:
        crawl = collector.collect(
            mode='reconciliation', index=index, overlap_pages=1,
            max_pages=max_pages, on_page=on_page,
            resume_page_state=resume_page_state if cursor_page > 0 else None,
            skip_classify_until_page=cursor_page,
        )
        if stop == 'max_pages':
            stop = crawl.stop_reason
        declared_pages = crawl.declared_pages or declared_pages
        declared_results = crawl.declared_results
        if stop in {'final_page', 'empty_page'} or (
                declared_pages is not None and cursor >= declared_pages):
            cycle_complete = True
            if stop == 'final_page':
                stop = 'cycle_complete'
    except _BudgetStop:
        pass
    return pages, stop, declared_pages, declared_results, page_state, page_signature, cursor, cycle_complete


def _overlap():
    return _config('RADAR1_PMMP_OVERLAP_PAGES', 3)


def run_refresh_job(app):
    """Background entry for the job runner."""
    with app.app_context():
        return run_refresh().to_dict()
