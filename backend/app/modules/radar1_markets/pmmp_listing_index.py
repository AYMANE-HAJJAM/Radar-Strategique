"""Durable PMMP listing index for Radar 1 discovery sync.

Remembers every listing seen on the public board, including notices that will
later fail ARCHERITAGE relevance. Does not write Radar business results.
"""
from dataclasses import dataclass, field

from app.db.extensions import db
from app.db.models import SearchRun, utcnow
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.modules.radar1_markets.pmmp_listing_collector import (
    DUPLICATE, LISTING_URL, NEW, UNCHANGED, UPDATED, ListingCrawl, ListingObservation,
    PmmpListing, PmmpListingCollector, SOURCE, new_pmmp_collector,
)

DEFAULT_OVERLAP_PAGES = 3
ACTIONABLE = frozenset({NEW, UPDATED})
PROCESSING = 'PROCESSING'
PENDING = 'PENDING_PROCESSING'


@dataclass
class ListingSyncResult:
    """Outcome of a durable sync. actionable is NEW + UPDATED only."""
    mode: str
    stop_reason: str
    pages_fetched: int
    declared_pages: int | None
    declared_results: int | None
    observations: list
    actionable: list
    counts: dict = field(default_factory=dict)


class DurableListingIndex:
    """ListingIndex-compatible adapter that persists to pmmp_listing_index."""

    def __init__(self, session=None, on_page=None):
        self.session = session if session is not None else db.session
        self.on_page = on_page

    def finish_page(self):
        if self.on_page:
            self.session.commit()
            self.on_page()

    def classify(self, listing):
        now = utcnow()
        row = self._find(listing)
        if row is None:
            self.session.add(PmmpListingIndex(
                source=listing.source or SOURCE,
                consultation_id=listing.consultation_id,
                organization=listing.organization,
                detail_url=listing.detail_url,
                reference=listing.reference,
                buyer=listing.buyer,
                title=listing.title,
                publication_date=listing.publication_date,
                deadline=listing.deadline,
                procedure=listing.procedure,
                category=listing.category,
                location=listing.location,
                fingerprint=listing.fingerprint,
                identity_key=listing.identity,
                first_seen_at=now,
                last_seen_at=now,
                last_changed_at=now,
                processing_state=PENDING,
            ))
            self.session.flush()
            return NEW
        row.last_seen_at = now
        if row.fingerprint == listing.fingerprint:
            self.session.flush()
            return UNCHANGED
        self._apply_content(row, listing, changed_at=now)
        if self._actively_owned(row):
            # Keep the live business claim; fingerprint mismatch requeues after release.
            row.processing_reason = 'listing_changed_while_processing'
            self.session.flush()
            return UPDATED
        # CAS requeue: never steal a row that is currently PROCESSING for an active run.
        active = db.select(SearchRun.id).where(SearchRun.status.in_(('initialized', 'running')))
        requeued = self.session.execute(
            db.update(PmmpListingIndex).where(
                PmmpListingIndex.id == row.id,
                PmmpListingIndex.fingerprint == listing.fingerprint,
                db.or_(
                    PmmpListingIndex.processing_state.is_(None),
                    PmmpListingIndex.processing_state != PROCESSING,
                    PmmpListingIndex.processing_run_id.is_(None),
                    PmmpListingIndex.processing_run_id.not_in(active),
                ),
            ).values(
                processing_state=PENDING,
                processing_run_id=None,
                processing_started_at=None,
                processing_reason='listing_fingerprint_changed',
            )
        ).rowcount
        if not requeued:
            # Lost the race to an active claim; leave ownership intact.
            row.processing_reason = 'listing_changed_while_processing'
        else:
            self.session.refresh(row)
        self.session.flush()
        return UPDATED

    def _actively_owned(self, row):
        if row.processing_state != PROCESSING or row.processing_run_id is None:
            return False
        status = self.session.scalar(
            db.select(SearchRun.status).where(SearchRun.id == row.processing_run_id))
        return status in ('initialized', 'running')

    def _find(self, listing):
        if listing.consultation_id:
            row = self.session.scalar(db.select(PmmpListingIndex).where(
                PmmpListingIndex.source == (listing.source or SOURCE),
                PmmpListingIndex.consultation_id == listing.consultation_id))
            if row is not None:
                return row
        return self.session.scalar(db.select(PmmpListingIndex).where(
            PmmpListingIndex.identity_key == listing.identity))

    def _apply_content(self, row, listing, *, changed_at):
        row.organization = listing.organization
        row.detail_url = listing.detail_url
        row.reference = listing.reference
        row.buyer = listing.buyer
        row.title = listing.title
        row.publication_date = listing.publication_date
        row.deadline = listing.deadline
        row.procedure = listing.procedure
        row.category = listing.category
        row.location = listing.location
        row.fingerprint = listing.fingerprint
        row.identity_key = listing.identity
        row.last_changed_at = changed_at


def listing_from_record(record):
    """Build a PmmpListing from a crawl dict or ORM row."""
    if isinstance(record, PmmpListing):
        return record
    if isinstance(record, PmmpListingIndex):
        return PmmpListing(
            source=record.source, consultation_id=record.consultation_id,
            organization=record.organization, reference=record.reference,
            title=record.title, buyer=record.buyer,
            publication_date=record.publication_date, deadline=record.deadline,
            procedure=record.procedure, category=record.category,
            location=record.location, detail_url=record.detail_url)
    return PmmpListing(
        source=record.get('source') or SOURCE,
        consultation_id=record.get('consultation_id'),
        organization=record.get('organization'),
        reference=record.get('reference'),
        title=record.get('title'),
        buyer=record.get('buyer'),
        publication_date=record.get('publication_date'),
        deadline=record.get('deadline'),
        procedure=record.get('procedure'),
        category=record.get('category'),
        location=record.get('location'),
        detail_url=record.get('detail_url'),
        estimated_amount=record.get('estimated_amount'),
    )


def import_baseline(records, *, commit=True):
    """Load a full-crawl dataset into the durable index without business results."""
    index = DurableListingIndex()
    observations = []
    for record in records:
        listing = listing_from_record(record)
        state = index.classify(listing)
        observations.append(ListingObservation(listing, state))
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return _sync_result(
        mode='baseline', stop_reason='import_complete', pages_fetched=0,
        declared_pages=None, declared_results=None, observations=observations)


def sync_listings(*, mode='incremental', overlap_pages=None, http=None,
                  listing_url=LISTING_URL, delay_seconds=0.35, max_pages=None,
                  commit=True, independent=False, on_page=None,
                  resume_page_state=None, skip_classify_until_page=0):
    """Compare discovered listings to the durable index. Honors collector mode.

    A normal run uses a separate session and commits each page before the next
    network request when independent=True. Partial discovery is safe because each
    row remains pending. Caller progress commits cannot certify business processing.
    """
    if mode not in {'full', 'incremental', 'reconciliation', 'baseline'}:
        raise ValueError('mode must be full, incremental, reconciliation, or baseline.')
    if mode == 'baseline':
        raise ValueError('Use import_baseline() for offline baseline import.')
    if overlap_pages is None:
        overlap_pages = _overlap_default()
    session = None
    if independent:
        from sqlalchemy.orm import Session
        session = Session(db.engine, expire_on_commit=False)
    try:
        page_hook = (on_page or (lambda: None)) if independent else on_page
        crawl = PmmpListingCollector(
            http, listing_url=listing_url, delay_seconds=delay_seconds,
        ).collect(
            mode=mode,
            index=DurableListingIndex(session, page_hook if independent else None),
            overlap_pages=overlap_pages, max_pages=max_pages,
            resume_page_state=resume_page_state,
            skip_classify_until_page=skip_classify_until_page,
            on_page=(None if independent else None))
    finally:
        if session is not None:
            session.close()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return _sync_result(
        mode=mode, stop_reason=crawl.stop_reason, pages_fetched=crawl.pages_fetched,
        declared_pages=crawl.declared_pages, declared_results=crawl.declared_results,
        observations=crawl.observations)


def actionable_listings(result):
    """Listings that should enter a later relevance pipeline."""
    return list(result.actionable)


def _overlap_default():
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            return int(current_app.config.get('RADAR1_PMMP_OVERLAP_PAGES', DEFAULT_OVERLAP_PAGES))
    except Exception:
        pass
    return DEFAULT_OVERLAP_PAGES


def _sync_result(*, mode, stop_reason, pages_fetched, declared_pages, declared_results, observations):
    counts = {}
    for observation in observations:
        counts[observation.state] = counts.get(observation.state, 0) + 1
    actionable = [item for item in observations if item.state in ACTIONABLE]
    return ListingSyncResult(
        mode=mode, stop_reason=stop_reason, pages_fetched=pages_fetched,
        declared_pages=declared_pages, declared_results=declared_results,
        observations=observations, actionable=actionable, counts=counts)


# Re-export collector entry for callers that need both.
__all__ = [
    'ACTIONABLE', 'DEFAULT_OVERLAP_PAGES', 'DurableListingIndex', 'ListingSyncResult',
    'actionable_listings', 'import_baseline', 'listing_from_record', 'new_pmmp_collector',
    'sync_listings',
]
