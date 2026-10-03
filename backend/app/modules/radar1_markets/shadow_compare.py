"""Safe legacy vs pmmp_index discovery comparison without business persistence.

Default mode forbids paid search and AI. Index mutations roll back unless
commit_index=True. Does not write Result / ResultObservation rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time

REFERENCE_NOTICE = '04/2026/AUS'


class PaidSearchForbidden(RuntimeError):
    """Raised when a shadow run would call the paid search provider."""


@dataclass
class ShadowCompareResult:
    legacy_candidates: int
    pmmp_candidates: int
    overlap: int
    unique_to_legacy: int
    unique_to_pmmp: int
    legacy_relevant: int
    pmmp_relevant: int
    reference_in_legacy: bool
    reference_in_pmmp: bool
    reference: str = REFERENCE_NOTICE
    legacy_keys: set = field(default_factory=set)
    pmmp_keys: set = field(default_factory=set)
    notes: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)

    def as_dict(self):
        payload = {
            'legacy_candidates': self.legacy_candidates,
            'pmmp_candidates': self.pmmp_candidates,
            'overlap': self.overlap,
            'unique_to_legacy': self.unique_to_legacy,
            'unique_to_pmmp': self.unique_to_pmmp,
            'legacy_relevant_after_policy': self.legacy_relevant,
            'pmmp_relevant_after_policy': self.pmmp_relevant,
            'reference': self.reference,
            'reference_in_legacy': self.reference_in_legacy,
            'reference_in_pmmp': self.reference_in_pmmp,
            'notes': list(self.notes),
        }
        if self.detail:
            payload['detail'] = self.detail
        return payload


def candidate_key(item):
    """Stable comparison key for a listing, SearchHit, or MarketCandidate."""
    reference = _field(item, 'reference')
    consultation = _field(item, 'consultation_id')
    url = _field(item, 'url') or _field(item, 'detail_url') or _field(item, 'official_url')
    if consultation:
        return f'cid:{consultation}'
    if url:
        return f'url:{url.strip().lower()}'
    if reference:
        buyer = _field(item, 'buyer') or _field(item, 'institution') or ''
        return f'ref:{reference.strip().lower()}|{buyer.strip().lower()}'
    title = _field(item, 'title') or ''
    return f'title:{title.strip().lower()}'


def compare_candidate_sets(legacy_items, pmmp_items, *, reference=REFERENCE_NOTICE,
                           legacy_relevant=None, pmmp_relevant=None):
    """Compare two discovery sets without I/O or persistence."""
    legacy_keys = {candidate_key(item) for item in legacy_items}
    pmmp_keys = {candidate_key(item) for item in pmmp_items}
    overlap = legacy_keys & pmmp_keys
    legacy_only = legacy_keys - pmmp_keys
    pmmp_only = pmmp_keys - legacy_keys
    legacy_rel = list(legacy_relevant) if legacy_relevant is not None else list(legacy_items)
    pmmp_rel = list(pmmp_relevant) if pmmp_relevant is not None else list(pmmp_items)
    return ShadowCompareResult(
        legacy_candidates=len(legacy_keys),
        pmmp_candidates=len(pmmp_keys),
        overlap=len(overlap),
        unique_to_legacy=len(legacy_only),
        unique_to_pmmp=len(pmmp_only),
        legacy_relevant=len({candidate_key(item) for item in legacy_rel}),
        pmmp_relevant=len({candidate_key(item) for item in pmmp_rel}),
        reference_in_legacy=_has_reference(legacy_items, reference),
        reference_in_pmmp=_has_reference(pmmp_items, reference),
        reference=reference,
        legacy_keys=legacy_keys,
        pmmp_keys=pmmp_keys,
    )


def shadow_compare(collector, radar, *, listing_http=None, commit_index=False,
                   reference=REFERENCE_NOTICE, allow_paid=False):
    """Run legacy and pmmp_index discovery side by side without Result writes.

    allow_paid=False (default) blocks provider.search and zeros discovery /
    resolution search budgets. Legacy then uses direct HTTP discovery only.
    """
    from app.db.extensions import db
    from app.modules.radar1_markets.pmmp_listing_index import sync_listings
    from app.modules.radar1_markets.pmmp_listing_collector import (
        NEW, UPDATED, UNCHANGED, DUPLICATE)
    from app.modules.radar1_markets.collector import COUNTERS, listing_to_search_hit

    notes = []
    detail = {
        'paid_search_allowed': allow_paid,
        'business_results_written': False,
        'index_committed': bool(commit_index),
    }
    guard = _install_paid_guard(collector, allow_paid=allow_paid)
    notes.append(guard['note'])

    # --- Legacy (direct-only when paid forbidden) ---
    legacy_started = time.perf_counter()
    legacy_collector = _clone_for_shadow(collector, mode='legacy', allow_paid=allow_paid)
    _install_paid_guard(legacy_collector, allow_paid=allow_paid)
    legacy_candidates = list(legacy_collector.legacy_discovery(radar) or [])
    legacy_elapsed = time.perf_counter() - legacy_started
    legacy_metrics = dict(legacy_collector.report.metrics)
    notes.append('legacy_path=legacy_discovery' + ('' if allow_paid else '_direct_only_zero_paid'))
    detail['legacy'] = {
        'elapsed_seconds': round(legacy_elapsed, 1),
        'total_candidates': len(legacy_candidates),
        'pmmp_observations': legacy_metrics.get('pmmp_observations', 0),
        'marchefacile_observations': legacy_metrics.get('marchefacile_observations', 0),
        'institutional_observations': legacy_metrics.get('institutional_observations', 0),
        'relevant_after_policy': len(legacy_candidates),
        'search_calls': legacy_metrics.get('search_calls', 0),
        'discovery_search_calls': legacy_metrics.get('discovery_search_calls', 0),
        'resolution_search_calls': legacy_metrics.get('resolution_search_calls', 0),
        'accepted_or_review': [_candidate_sample(c) for c in legacy_candidates],
        'near_reject_sample': _near_rejects(legacy_collector.report.trace),
        'health': legacy_collector.report.health,
        'health_reasons': list(legacy_collector.report.health_reasons),
        'truncated': list(legacy_collector.report.truncated),
    }

    if listing_http is not None:
        collector.listing_http = listing_http
    indexed = _index_size()
    detail['index_size_before'] = indexed

    if indexed == 0:
        notes.append('pmmp_index_empty')
        pmmp_seen = []
        pmmp_relevant = []
        sync = None
        pmmp_collector = None
        detail['pmmp'] = {'skipped': True, 'reason': 'empty_index'}
    else:
        counting_http = _CountingHttp(
            getattr(collector, 'listing_http', None) or _live_listing_http())
        pmmp_started = time.perf_counter()
        sync = sync_listings(
            mode='incremental',
            overlap_pages=collector.config.get('RADAR1_PMMP_OVERLAP_PAGES', 3),
            commit=False,
            http=counting_http,
            delay_seconds=0 if getattr(collector, 'listing_http', None) is not None else 0.35)
        pmmp_elapsed = time.perf_counter() - pmmp_started
        pmmp_seen = [item.listing for item in sync.actionable]
        notes.append(
            f"pmmp_sync stop={sync.stop_reason} new={sync.counts.get(NEW, 0)} "
            f"updated={sync.counts.get(UPDATED, 0)} actionable={len(sync.actionable)}")
        pmmp_collector = _clone_for_shadow(collector, mode='pmmp_index', allow_paid=allow_paid)
        _install_paid_guard(pmmp_collector, allow_paid=allow_paid)
        stats = {**dict.fromkeys(COUNTERS, 0), 'query_index': None,
                 'source_strategy': 'PMMP_INDEX', 'query_family': 'shadow',
                 'query_text': 'pmmp_listing_index', 'domains': [],
                 'recency_days': None, 'new_identity': 0, 'blocked': 0,
                 'parser_failures': 0, 'billable_search': False}
        pmmp_collector.report.query_metrics.append(stats)
        pmmp_collector.active_stats = stats
        try:
            for item in sync.actionable:
                hit = listing_to_search_hit(item.listing)
                if hit.url:
                    pmmp_collector._process(hit, radar, stats, hit.url)
        finally:
            pmmp_collector.active_stats = None
        pmmp_relevant = list(pmmp_collector.report.candidates)

        unchanged_pages = _unchanged_page_streak(sync)
        detail['pmmp'] = {
            'elapsed_seconds': round(pmmp_elapsed, 1),
            'pages_fetched': sync.pages_fetched,
            'declared_pages': sync.declared_pages,
            'declared_results': sync.declared_results,
            'listings_inspected': len(sync.observations),
            'new': sync.counts.get(NEW, 0),
            'updated': sync.counts.get(UPDATED, 0),
            'unchanged': sync.counts.get(UNCHANGED, 0),
            'duplicates': sync.counts.get(DUPLICATE, 0),
            'actionable': len(sync.actionable),
            'stop_reason': sync.stop_reason,
            'http_requests': counting_http.requests,
            'http_get': counting_http.gets,
            'http_post': counting_http.posts,
            'overlap_pages_config': collector.config.get('RADAR1_PMMP_OVERLAP_PAGES', 3),
            'unchanged_page_streak_at_stop': unchanged_pages,
            'three_page_overlap_stop_ok': (
                sync.stop_reason == 'incremental_overlap'
                and sync.pages_fetched <= max(6, 2 * int(collector.config.get('RADAR1_PMMP_OVERLAP_PAGES', 3)))
            ),
            'relevant_after_policy': len(pmmp_relevant),
            'search_calls': pmmp_collector.report.metrics.get('search_calls', 0),
            'accepted_or_review': [_candidate_sample(c) for c in pmmp_relevant],
            'near_reject_sample': _near_rejects(pmmp_collector.report.trace),
            'health': pmmp_collector.report.health,
            'health_reasons': list(pmmp_collector.report.health_reasons),
        }

        # Policy sample over inspected listings (including UNCHANGED) for near-scope view.
        detail['pmmp']['listing_policy_sample'] = _listing_policy_sample(
            [item.listing for item in sync.observations if item.state != DUPLICATE],
            collector.config, limit=40)

        if not commit_index:
            db.session.rollback()
            notes.append('index_changes_rolled_back')

    detail['reference'] = _reference_report(
        reference=reference,
        sync=sync,
        indexed=indexed,
        collector=collector,
        radar=radar,
        allow_paid=allow_paid,
        pmmp_relevant=pmmp_relevant if indexed else [],
    )

    # Coverage sets: compare relevant kept candidates, and also raw discovery keys.
    result = compare_candidate_sets(
        legacy_candidates, pmmp_seen,
        reference=reference,
        legacy_relevant=legacy_candidates,
        pmmp_relevant=pmmp_relevant if indexed else [])
    legacy_rel_keys = {candidate_key(c) for c in legacy_candidates}
    pmmp_rel_keys = {candidate_key(c) for c in (pmmp_relevant if indexed else [])}
    detail['coverage'] = {
        'discovery_overlap': result.overlap,
        'discovery_unique_to_legacy': result.unique_to_legacy,
        'discovery_unique_to_pmmp_actionable': result.unique_to_pmmp,
        'relevant_overlap': len(legacy_rel_keys & pmmp_rel_keys),
        'relevant_unique_to_legacy': len(legacy_rel_keys - pmmp_rel_keys),
        'relevant_unique_to_pmmp': len(pmmp_rel_keys - legacy_rel_keys),
        'legacy_relevant_keys': sorted(legacy_rel_keys),
        'pmmp_relevant_keys': sorted(pmmp_rel_keys),
    }
    detail['go_no_go'] = _recommend(detail, notes)
    result.notes = notes
    result.detail = detail
    return result


def _recommend(detail, notes):
    pmmp = detail.get('pmmp') or {}
    legacy = detail.get('legacy') or {}
    reference = detail.get('reference') or {}
    reasons = []
    if pmmp.get('skipped'):
        reasons.append('pmmp_index_empty')
        return {'verdict': 'C', 'label': 'NOT READY — incremental-performance issue',
                'reasons': reasons + ['baseline required before pmmp_index']}
    if legacy.get('search_calls', 0) or pmmp.get('search_calls', 0):
        reasons.append('paid_search_occurred_in_shadow')
        return {'verdict': 'E', 'label': 'NOT READY — other concrete issue',
                'reasons': reasons}
    pages = pmmp.get('pages_fetched') or 0
    declared = pmmp.get('declared_pages') or 0
    if declared and pages > max(12, int(0.1 * declared)):
        reasons.append(f'incremental_walked_{pages}_of_{declared}_pages')
        return {'verdict': 'C', 'label': 'NOT READY — incremental-performance issue',
                'reasons': reasons}
    if not pmmp.get('three_page_overlap_stop_ok') and pmmp.get('stop_reason') not in {
            'incremental_overlap', 'final_page'}:
        reasons.append(f"unexpected_stop={pmmp.get('stop_reason')}")
        return {'verdict': 'C', 'label': 'NOT READY — incremental-performance issue',
                'reasons': reasons}
    if not reference.get('present_in_index'):
        reasons.append('known_reference_missing_from_index')
        return {'verdict': 'B', 'label': 'NOT READY — discovery issue', 'reasons': reasons}
    # Actionable may be zero right after a full baseline — expected.
    if pmmp.get('stop_reason') == 'incremental_overlap' and pages <= 6:
        reasons.append('incremental_overlap_stop_ok')
        reasons.append('index_memory_present')
        if reference.get('policy_if_evaluated', {}).get('decision') in {'keep', 'review', 'accept'}:
            reasons.append('known_reference_policy_ok')
        elif reference.get('sync_state') == 'UNCHANGED':
            reasons.append('known_reference_unchanged_expected_after_baseline')
        return {'verdict': 'A', 'label': 'READY TO ENABLE pmmp_index IN PRODUCTION',
                'reasons': reasons,
                'caveat': ('Shadow legacy side was direct-HTTP only (zero paid). '
                           'Enable only after one staging SearchRun with '
                           'RADAR1_DISCOVERY_MODE=pmmp_index.')}
    if pmmp.get('actionable', 0) == 0 and pmmp.get('stop_reason') == 'final_page' and pages > 20:
        reasons.append('full_board_walk_on_incremental')
        return {'verdict': 'C', 'label': 'NOT READY — incremental-performance issue',
                'reasons': reasons}
    reasons.append('needs_manual_review_of_shadow_detail')
    return {'verdict': 'E', 'label': 'NOT READY — other concrete issue', 'reasons': reasons}


def _reference_report(*, reference, sync, indexed, collector, radar, allow_paid, pmmp_relevant):
    from app.db.extensions import db
    from app.db.models.pmmp_listing_index import PmmpListingIndex
    from app.modules.radar1_markets.collector import listing_to_search_hit
    from app.modules.radar1_markets.policy import evaluate_relevance

    row = None
    if indexed:
        row = db.session.scalar(
            db.select(PmmpListingIndex).where(PmmpListingIndex.reference.ilike(f'%{reference}%')))
    sync_state = None
    listing = None
    if sync is not None:
        for item in sync.observations:
            ref = (item.listing.reference or '')
            if reference.lower() in ref.lower():
                sync_state = item.state
                listing = item.listing
                break
    if listing is None and row is not None:
        from app.modules.radar1_markets.pmmp_listing_index import listing_from_record
        listing = listing_from_record(row)
        sync_state = sync_state or 'UNCHANGED'
    policy = {}
    pipeline = {}
    if listing is not None:
        hit = listing_to_search_hit(listing)
        context = ' '.join(filter(None, (hit.title, hit.institution, hit.location, hit.procedure_type)))
        policy = evaluate_relevance(
            hit.title, collector.config.get('RADAR1_KEYWORD_GROUPS'), scope=context,
            procedure_type=hit.procedure_type,
            threshold_mad=collector.config.get('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000))
        # Optional full downstream evaluation without paid search (detail HTTP only).
        probe = _clone_for_shadow(collector, mode='pmmp_index', allow_paid=allow_paid)
        _install_paid_guard(probe, allow_paid=allow_paid)
        from app.modules.radar1_markets.collector import COUNTERS
        stats = {**dict.fromkeys(COUNTERS, 0), 'query_index': None,
                 'source_strategy': 'PMMP_INDEX', 'query_family': 'reference_probe',
                 'query_text': reference, 'domains': [], 'recency_days': None,
                 'new_identity': 0, 'blocked': 0, 'parser_failures': 0,
                 'billable_search': False}
        probe.report.query_metrics.append(stats)
        probe.active_stats = stats
        try:
            if hit.url:
                probe._process(hit, radar, stats, hit.url)
        finally:
            probe.active_stats = None
        kept = probe.report.candidates
        pipeline = {
            'kept': bool(kept),
            'search_calls': probe.report.metrics.get('search_calls', 0),
            'trace_tail': probe.report.trace[-3:] if probe.report.trace else [],
            'candidate': _candidate_sample(kept[0]) if kept else None,
            'reject_reasons': [t.get('reason') for t in probe.report.trace
                               if t.get('reason') not in {'verified_offer', 'credible_fallback'}][-5:],
        }
    in_relevant = _has_reference(pmmp_relevant, reference)
    return {
        'reference': reference,
        'present_in_index': row is not None,
        'consultation_id': getattr(row, 'consultation_id', None) if row else None,
        'index_title': (row.title[:180] if row and row.title else None),
        'index_buyer': (row.buyer[:120] if row and row.buyer else None),
        'sync_state': sync_state,
        'actionable_in_this_run': sync_state in {'NEW', 'UPDATED'},
        'unchanged_expected_after_baseline': sync_state == 'UNCHANGED',
        'in_pmmp_relevant_kept': in_relevant,
        'policy_if_evaluated': {
            'decision': policy.get('decision'),
            'business_category': policy.get('business_category'),
            'reason_code': policy.get('reason_code'),
            'rejection_reason': policy.get('rejection_reason'),
        } if policy else None,
        'pipeline_if_evaluated': pipeline,
    }


def _listing_policy_sample(listings, config, *, limit=40):
    from app.modules.radar1_markets.policy import evaluate_relevance
    rows = []
    for listing in listings[:limit]:
        title = listing.title or ''
        context = ' '.join(filter(None, (title, listing.buyer, listing.location, listing.procedure)))
        decision = evaluate_relevance(
            title, config.get('RADAR1_KEYWORD_GROUPS'), scope=context,
            procedure_type=listing.procedure,
            threshold_mad=config.get('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000))
        rows.append({
            'reference': listing.reference,
            'title': (title or '')[:160],
            'buyer': (listing.buyer or '')[:100],
            'procedure': listing.procedure,
            'decision': decision.get('decision'),
            'business_category': decision.get('business_category'),
            'reason_code': decision.get('reason_code'),
            'rejection_reason': decision.get('rejection_reason'),
        })
    accepted = [r for r in rows if r['decision'] in {'keep', 'review'}]
    rejected = [r for r in rows if r['decision'] == 'reject']
    # Prefer rejects that still mention heritage/architecture tokens as "closest".
    needles = ('patrimoine', 'architect', 'restauration', 'médina', 'medina',
               'monument', 'heritage', 'valorisation', 'réhabilitation', 'rehabilitation')
    def closeness(row):
        text = f"{row['title']} {row['reference']}".lower()
        return sum(1 for n in needles if n in text)
    rejected.sort(key=closeness, reverse=True)
    return {'accepted_or_review': accepted[:20], 'closest_rejects': rejected[:15]}


def _candidate_sample(candidate):
    meta = getattr(candidate, 'metadata', None) or {}
    business = meta.get('business_relevance') or {}
    pmmp = meta.get('pmmp') or {}
    estimate = None
    if getattr(candidate, 'estimated_amount', None) is not None:
        estimate = {
            'amount': candidate.estimated_amount,
            'verified': getattr(candidate, 'estimated_amount_verified', None),
            'currency': 'MAD',
        }
    elif isinstance(pmmp.get('estimate'), dict):
        estimate = pmmp.get('estimate')
    return {
        'reference': getattr(candidate, 'reference', None),
        'title': (getattr(candidate, 'title', None) or '')[:180],
        'buyer': getattr(candidate, 'institution', None),
        'procedure': getattr(candidate, 'procedure_type', None) or pmmp.get('procedure'),
        'estimate': estimate,
        'classification': business.get('business_category') or getattr(candidate, 'business_category', None),
        'decision': business.get('decision'),
        'reason_code': business.get('reason_code'),
        'rejection_reason': business.get('rejection_reason'),
        'resolution_state': getattr(candidate, 'resolution_state', None),
        'url': getattr(candidate, 'official_url', None) or getattr(candidate, 'url', None),
    }


def _near_rejects(trace, *, limit=12):
    needles = ('patrimoine', 'architect', 'restauration', 'medina', 'médina',
               'monument', 'valorisation', 'rehabilitation', 'réhabilitation',
               'concours')
    rejects = []
    for event in trace or []:
        reason = event.get('reason') or ''
        if reason in {'verified_offer', 'credible_fallback'}:
            continue
        title = event.get('title') or ''
        text = f"{title} {event.get('reference') or ''}".lower()
        score = sum(1 for n in needles if n in text)
        business = event.get('business_relevance') or {}
        rejects.append({
            'reference': event.get('reference'),
            'title': title[:160],
            'reason': reason,
            'decision': business.get('decision'),
            'business_category': business.get('business_category'),
            'reason_code': business.get('reason_code'),
            'closeness': score,
        })
    rejects.sort(key=lambda row: (row['closeness'], row['reference'] or ''), reverse=True)
    return rejects[:limit]


def _unchanged_page_streak(sync):
    from app.modules.radar1_markets.pmmp_listing_collector import UNCHANGED, NEW, UPDATED, DUPLICATE
    # Reconstruct trailing unchanged pages from observation order (page-major).
    # Observations are appended page by page; approximate by fingerprinting page chunks of 10.
    pages = []
    bucket = []
    for item in sync.observations:
        bucket.append(item)
        if len(bucket) >= 10:
            pages.append(bucket)
            bucket = []
    if bucket:
        pages.append(bucket)
    streak = 0
    for page in pages:
        states = {item.state for item in page if item.state != DUPLICATE}
        if states and states <= {UNCHANGED}:
            streak += 1
        else:
            streak = 0
    return streak


def _install_paid_guard(collector, *, allow_paid):
    provider = collector.provider

    def blocked(*args, **kwargs):
        raise PaidSearchForbidden(
            'Shadow validation forbids paid search. Re-run with allow_paid=True only if explicitly authorized.')

    if allow_paid:
        return {'note': 'paid_search_allowed=true'}
    collector.provider = _GuardedProvider(provider, blocked)
    # Zero search budgets so _budget_available short-circuits before search.
    collector.config['RADAR1_DISCOVERY_MAX_CALLS'] = 0
    collector.config['RADAR1_RESOLUTION_MAX_CALLS'] = 0
    collector.config['RADAR1_MIN_SEARCH_QUERIES'] = 0
    collector.config['RADAR1_NORMAL_SEARCH_BUDGET'] = 0
    collector.config['RADAR1_NORMAL_RESOLUTION_BUDGET'] = 0
    return {'note': 'paid_search_forbidden_budgets_zeroed'}


class _GuardedProvider:
    def __init__(self, inner, blocked):
        self._inner = inner
        self._blocked = blocked

    def search(self, *args, **kwargs):
        return self._blocked(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _CountingHttp:
    def __init__(self, inner):
        self.inner = inner
        self.gets = 0
        self.posts = 0

    @property
    def requests(self):
        return self.gets + self.posts

    def get(self, url):
        self.gets += 1
        return self.inner.get(url)

    def post(self, url, fields):
        self.posts += 1
        return self.inner.post(url, fields)


def _live_listing_http():
    from app.modules.radar1_markets.pmmp_listing_collector import PmmpHttp
    return PmmpHttp(delay_seconds=0.35)


def _clone_for_shadow(collector, *, mode, allow_paid=False):
    """Fresh collector sharing provider/config with discovery mode override.

    Pass pages=None so RADAR1_DIRECT_DISCOVERY_ENABLED stays effective (the
    MarketsCollector constructor disables direct discovery when pages is set
    unless RADAR1_FORCE_DIRECT_DISCOVERY is true).
    """
    from app.modules.radar1_markets.collector import MarketsCollector
    config = dict(collector.config)
    config['RADAR1_DISCOVERY_MODE'] = mode
    if not allow_paid:
        config['RADAR1_DISCOVERY_MAX_CALLS'] = 0
        config['RADAR1_RESOLUTION_MAX_CALLS'] = 0
        config['RADAR1_MIN_SEARCH_QUERIES'] = 0
        config['RADAR1_NORMAL_SEARCH_BUDGET'] = 0
        config['RADAR1_NORMAL_RESOLUTION_BUDGET'] = 0
        config['RADAR1_FORCE_DIRECT_DISCOVERY'] = True
    clone = MarketsCollector(collector.provider, config, pages=None)
    if hasattr(collector, 'listing_http'):
        clone.listing_http = collector.listing_http
    return clone


def _index_size():
    from app.db.extensions import db
    from app.db.models.pmmp_listing_index import PmmpListingIndex
    return db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0


def _field(item, name):
    if item is None:
        return None
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _has_reference(items, reference):
    needle = (reference or '').strip().lower()
    if not needle:
        return False
    for item in items:
        value = _field(item, 'reference') or ''
        if needle in value.strip().lower():
            return True
    return False
