"""Durable PMMP listing index for Radar 1 discovery sync.

Remembers every listing seen on the public board, including notices that will
later fail ARCHERITAGE relevance. Does not write Radar business results.
"""
from dataclasses import dataclass, field

from app.db.extensions import db
from app.db.models import utcnow
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.modules.radar1_markets.pmmp_listing_collector import (
    DUPLICATE, LISTING_URL, NEW, UNCHANGED, UPDATED, ListingCrawl, ListingObservation,
    PmmpListing, PmmpListingCollector, SOURCE, new_pmmp_collector,
)

DEFAULT_OVERLAP_PAGES = 3
ACTIONABLE = frozenset({NEW, UPDATED})


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

    def classify(self, listing):
        now = utcnow()
        row = self._find(listing)
        if row is None:
            db.session.add(PmmpListingIndex(
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
            ))
            db.session.flush()
            return NEW
        row.last_seen_at = now
        if row.fingerprint == listing.fingerprint:
            db.session.flush()
            return UNCHANGED
        self._apply(row, listing, changed_at=now)
        db.session.flush()
        return UPDATED

    def _find(self, listing):
        if listing.consultation_id:
            row = db.session.scalar(db.select(PmmpListingIndex).where(
                PmmpListingIndex.source == (listing.source or SOURCE),
                PmmpListingIndex.consultation_id == listing.consultation_id))
            if row is not None:
                return row
        return db.session.scalar(db.select(PmmpListingIndex).where(
            PmmpListingIndex.identity_key == listing.identity))

    def _apply(self, row, listing, *, changed_at):
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
                  commit=True):
    """Run a crawl against the durable index. Production Radar 1 is not switched."""
    if mode not in {'full', 'incremental', 'reconciliation', 'baseline'}:
        raise ValueError('mode must be full, incremental, reconciliation, or baseline.')
    if mode == 'baseline':
        raise ValueError('Use import_baseline() for offline baseline import.')
    if overlap_pages is None:
        overlap_pages = _overlap_default()
    crawl_mode = 'full' if mode == 'reconciliation' else mode
    crawl = PmmpListingCollector(
        http, listing_url=listing_url, delay_seconds=delay_seconds,
    ).collect(
        mode=crawl_mode, index=DurableListingIndex(),
        overlap_pages=overlap_pages, max_pages=max_pages)
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
