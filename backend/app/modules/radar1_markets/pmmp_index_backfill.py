"""One-time business backfill from durable pmmp_listing_index into Radar 1.

Reads existing index rows only (no board recrawl). Applies the same cheap
preliminary filter and MarketsCollector._process path used in production, then
returns kept candidates for the normal orchestrator persist path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.extensions import db
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.modules.radar1_markets.collector import COUNTERS, MarketsCollector, listing_to_search_hit
from app.modules.radar1_markets.pmmp_listing_index import listing_from_record
from app.modules.radar1_markets.policy import (
    folded, has_architectural_context, has_heritage_context,
    is_out_of_scope_infrastructure, preliminary_plausible,
)


REFERENCE_NOTICE = '04/2026/AUS'


@dataclass
class BackfillStats:
    indexed_considered: int = 0
    skipped_prefilter: int = 0
    skipped_missing_url: int = 0
    sent_to_detail: int = 0
    kept_candidates: int = 0
    prefilter_reasons: dict = field(default_factory=dict)
    reference_notice: dict | None = None
    errors: list = field(default_factory=list)

    def as_dict(self):
        return {
            'indexed_considered': self.indexed_considered,
            'skipped_prefilter': self.skipped_prefilter,
            'skipped_missing_url': self.skipped_missing_url,
            'sent_to_detail': self.sent_to_detail,
            'kept_candidates': self.kept_candidates,
            'prefilter_reasons': dict(self.prefilter_reasons),
            'reference_notice': self.reference_notice,
            'errors': list(self.errors),
        }


def cheap_listing_prefilter(listing):
    """Deterministic listing-only gate before any detail HTTP.

    Uses the same policy helpers as Radar 1; does not invent a second classifier.
    """
    title = listing.title or ''
    scope = ' '.join(filter(None, (
        title, listing.buyer, listing.procedure, listing.category, listing.location,
        listing.reference)))
    prelim = preliminary_plausible(title, scope)
    if prelim.get('decision') == 'reject':
        return {
            'decision': 'reject',
            'reason_code': prelim.get('reason_code'),
            'rejection_reason': prelim.get('rejection_reason') or 'preliminary_reject',
        }
    text = folded(scope)
    if (is_out_of_scope_infrastructure(text)
            and not has_architectural_context(text)
            and not has_heritage_context(text)):
        return {
            'decision': 'reject',
            'reason_code': 'REJECT_OUT_OF_SCOPE_INFRASTRUCTURE',
            'rejection_reason': 'infrastructure_without_architecture',
        }
    return {'decision': 'continue', 'reason_code': None, 'rejection_reason': None}


def backfill_from_index(collector: MarketsCollector, radar, *, limit=None):
    """Process durable index rows through the existing Radar 1 collector pipeline.

    Returns (candidates, BackfillStats). Candidates are already policy-accepted
    MarketCandidate objects ready for orchestrator normalize/dedup/persist.
    """
    query = db.select(PmmpListingIndex).order_by(PmmpListingIndex.id)
    if limit is not None:
        query = query.limit(int(limit))
    rows = db.session.scalars(query).all()
    listings = [listing_from_record(row) for row in rows]
    # End the read transaction before long PMMP detail HTTP (idle-in-tx timeout).
    db.session.rollback()
    stats = BackfillStats(indexed_considered=len(listings))
    counter = {**dict.fromkeys(COUNTERS, 0), 'query_index': None,
               'source_strategy': 'PMMP_INDEX_BACKFILL', 'query_family': 'backfill',
               'query_text': 'pmmp_listing_index_backfill', 'domains': list(collector.pmmp_domains),
               'recency_days': None, 'new_identity': 0, 'blocked': 0,
               'parser_failures': 0, 'billable_search': False}
    collector.report.query_metrics.append(counter)
    collector.active_stats = counter
    collector.report.metrics['discovery_mode'] = 'pmmp_index_backfill'
    try:
        for index, listing in enumerate(listings, start=1):
            is_reference = bool(listing.reference and REFERENCE_NOTICE.lower() in listing.reference.lower())
            gate = cheap_listing_prefilter(listing)
            if gate['decision'] == 'reject':
                stats.skipped_prefilter += 1
                reason = gate.get('rejection_reason') or gate.get('reason_code') or 'prefilter'
                stats.prefilter_reasons[reason] = stats.prefilter_reasons.get(reason, 0) + 1
                if is_reference:
                    stats.reference_notice = {
                        'reference': listing.reference,
                        'consultation_id': listing.consultation_id,
                        'stage': 'prefilter',
                        'decision': 'reject',
                        'reason_code': gate.get('reason_code'),
                        'rejection_reason': gate.get('rejection_reason'),
                    }
                continue
            hit = listing_to_search_hit(listing)
            if not hit.url:
                stats.skipped_missing_url += 1
                stats.prefilter_reasons['missing_detail_url'] = (
                    stats.prefilter_reasons.get('missing_detail_url', 0) + 1)
                if is_reference:
                    stats.reference_notice = {
                        'reference': listing.reference,
                        'consultation_id': listing.consultation_id,
                        'stage': 'prefilter',
                        'decision': 'reject',
                        'reason_code': 'missing_detail_url',
                    }
                continue
            before = len(collector.report.candidates)
            before_trace = len(collector.report.trace)
            stats.sent_to_detail += 1
            try:
                collector._process(hit, radar, counter, hit.url)
            except Exception as error:  # noqa: BLE001 — backfill must continue
                stats.errors.append({
                    'reference': listing.reference,
                    'consultation_id': listing.consultation_id,
                    'error_type': type(error).__name__,
                    'message': str(error)[:200],
                })
                db.session.rollback()
                continue
            finally:
                # Feedback scoring may open a short DB read; never hold it across
                # the next PMMP detail HTTP call (idle-in-transaction timeout).
                db.session.rollback()
            kept = len(collector.report.candidates) > before
            if is_reference:
                event = None
                if collector.report.trace[before_trace:]:
                    event = collector.report.trace[-1]
                business = (event or {}).get('business_relevance') or {}
                candidate = collector.report.candidates[-1] if kept else None
                stats.reference_notice = {
                    'reference': listing.reference,
                    'consultation_id': listing.consultation_id,
                    'stage': 'pipeline',
                    'kept': kept,
                    'decision': business.get('decision') or (
                        getattr(candidate, 'business_category', None) and 'keep'),
                    'classification': (
                        getattr(candidate, 'business_category', None)
                        or business.get('business_category')),
                    'reason_code': business.get('reason_code'),
                    'rejection_reason': business.get('rejection_reason'),
                    'resolution_state': getattr(candidate, 'resolution_state', None) if kept else (
                        (event or {}).get('resolution_state')),
                    'trace_reason': (event or {}).get('reason'),
                }
        collector._finish_query(counter)
    finally:
        collector.active_stats = None
        db.session.rollback()
    stats.kept_candidates = len(collector.report.candidates)
    collector.report.metrics['backfill'] = stats.as_dict()
    return collector.report.candidates, stats


def classify_trace_outcomes(trace):
    """Summarize collector trace into accepted / review / rejected buckets."""
    accepted, review, rejected = [], [], []
    for event in trace or []:
        reason = event.get('reason')
        business = event.get('business_relevance') or {}
        row = {
            'reference': event.get('reference'),
            'title': (event.get('title') or '')[:180],
            'decision': business.get('decision'),
            'classification': business.get('business_category'),
            'reason_code': business.get('reason_code'),
            'rejection_reason': business.get('rejection_reason'),
            'trace_reason': reason,
            'resolution_state': event.get('resolution_state'),
        }
        if reason in {'verified_offer', 'credible_fallback'}:
            if business.get('decision') == 'review' or business.get('business_category') == 'P2_REVIEW':
                review.append(row)
            else:
                accepted.append(row)
        elif reason not in {'known_unchanged_or_duplicate'}:
            rejected.append(row)
    return {'accepted': accepted, 'review': review, 'rejected': rejected}
