"""Radar 1 discovery observations are distinct from validated final offers."""
import logging
from datetime import date
from datetime import datetime
from pydantic import ValidationError
from urllib.parse import urljoin

from app.core.validation import today_in_morocco
from app.core.collector_base import CollectionReport, ProviderUnavailable
from app.modules.radar1_markets.parser import normalize_hit
from app.modules.radar1_markets.policy import (
    source_role, relevant, aggregate_title, detail_url, DEFAULT_WHITELIST, normalize_domain,
    evaluate_relevance, folded, preliminary_plausible, REASON_REJECT_NO_DOMAIN,
    REASON_REJECT_NO_ROLE, REASON_REJECT_GENERIC, has_architectural_context,
    has_strong_architectural_scope,
)
from app.integrations.http.html import PublicPages, AccessLimitedPages
from app.integrations.pmmp.parser import (
    extract_rows, verify_detail, enrich_detail, labelled_fields, procurement_metadata, _amount)
from app.integrations.pmmp.client import detail_from_official_identity, canonical_detail_url
from app.modules.radar1_markets.resolution import VERIFIED, CREDIBLE, UNRESOLVED, strong_identity, credible_fallback, with_resolution
from app.integrations.openai.base import SearchHit, SearchProviderError
from app.modules.radar1_markets.official_link_resolver import OfficialLinkResolver
from app.core.dedup import identity_keys, discovery_snapshot
from app.modules.radar1_markets.discovery_strategies import build_discovery_plan, direct_discovery_plan

logger = logging.getLogger(__name__)
COUNTERS = ('raw_results_count', 'allowed_domain_results', 'aggregate_pages_detected',
    'individual_tenders_extracted', 'candidates_created', 'rejected_by_source', 'rejected_by_parser',
    'rejected_by_freshness', 'rejected_by_relevance', 'official_resolution_attempts',
    'rejected_by_resolution', 'official_urls_resolved', 'duplicates_skipped', 'control_reference_filtered', 'kept_p1', 'kept_p2', 'kept_p3',
    'verified_official', 'unverified_credible', 'unresolved', 'http_403', 'http_429',
    'queries_with_results', 'queries_with_zero_results', 'deduped_before_enrichment',
    'pmmp_raw', 'aggregator_raw', 'institutional_raw', 'discovery_search_calls',
    'resolution_search_calls', 'query_scope_filtered', 'direct_pages_fetched',
    'pmmp_observations', 'marchefacile_observations', 'institutional_observations',
    'unique_identities', 'generic_pages', 'procurement_pages',
    'page_type_tender_detail', 'page_type_tender_list', 'page_type_procurement_category',
    'page_type_institutional_procurement', 'page_type_generic_org', 'page_type_non_procurement',
    'topography_rejected', 'technical_only_rejected', 'heritage_kept',
    'consultation_architecturale_kept', 'concours_architectural_kept', 'architecture_kept')


class MarketsCollector:
    def __init__(self, provider, config, *, pages=None):
        self.provider, self.config = provider, config
        self.direct_discovery_enabled = config.get('RADAR1_DIRECT_DISCOVERY_ENABLED', True) and (
            pages is None or config.get('RADAR1_FORCE_DIRECT_DISCOVERY', False))
        self.report = CollectionReport(metrics={**dict.fromkeys(COUNTERS, 0), 'pages_discovered': 0,
            'relevant_candidates': 0, 'rejected': 0, 'search_calls': 0, 'raw_results': 0,
            'usable_results': 0, 'cost_warning': False})
        self.on_progress = lambda: None
        self.known_unchanged = lambda candidate: False
        self.domains = tuple(dict.fromkeys(normalize_domain(d) for d in config.get('RADAR1_SOURCE_WHITELIST', DEFAULT_WHITELIST)))
        self.official = tuple(d for d in self.domains if source_role('https://' + d, config) in
                              {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'})
        self.pmmp_domains = tuple(d for d in self.official if d == 'marchespublics.gov.ma')
        self.active_stats = None
        self.pages = AccessLimitedPages(pages or PublicPages(self.domains, config['SOURCE_HTTP_TIMEOUT_SECONDS']), self.report.metrics,
                                        self._record_page_error)
        self.lookup_cache = {}
        self.query_performance = {}
        self.seen, self.discovered_pages, self.expanded_pages = set(), set(), set()
        self.discovery_seen = set()
        self.examined = 0

    def _business(self, candidate, context=None):
        pmmp = (candidate.metadata or {}).get('pmmp') or {}
        domains = pmmp.get('activity_domains') or []
        domain_text = ' '.join(domains) if isinstance(domains, (list, tuple)) else str(domains or '')
        context = context if context is not None else ' '.join(filter(None, (
            candidate.raw_text, candidate.institution, candidate.location_evidence,
            domain_text, pmmp.get('procedure'), pmmp.get('main_category'), pmmp.get('object'),
            candidate.procedure_type)))
        return evaluate_relevance(candidate.title, self.config.get('RADAR1_KEYWORD_GROUPS'), scope=context,
            estimated_amount=candidate.estimated_amount,
            amount_verified=candidate.estimated_amount_verified,
            procedure_type=candidate.procedure_type,
            threshold_mad=self.config.get('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000))

    def _with_metadata(self, candidate, **updates):
        """Apply metadata updates via model_copy so bounded_metadata always re-validates."""
        return candidate.model_copy(update={'metadata': {**candidate.metadata, **updates}})

    def _should_enrich_before_reject(self, business, candidate):
        """Defer listing rejects that detail may overturn (competition / major / heritage)."""
        code = business.get('reason_code')
        if code not in {REASON_REJECT_NO_DOMAIN, REASON_REJECT_NO_ROLE, REASON_REJECT_GENERIC}:
            return False
        if candidate.source_type not in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}:
            return False
        if not detail_url(candidate.url or candidate.official_url):
            return False
        title = candidate.title or ''
        # Architectural role wording makes the listing plausible enough to enrich once.
        if has_strong_architectural_scope(title) or has_architectural_context(title):
            return True
        return bool(business.get('role_fit'))

    def _apply_feedback(self, business, candidate, context):
        """Adaptive score after hard policy; never overrides hard reject."""
        from flask import has_app_context, current_app
        if not has_app_context() or business.get('decision') == 'reject':
            business = {**business, 'feedback': {'applied': 'skipped', 'feedback_score': 0.0}}
            return business
        try:
            from app.modules.radar1_markets.feedback import get_feedback_service
            explanation = get_feedback_service().score(
                current_app._get_current_object(), candidate.title, scope=context,
                category=business.get('business_category'),
                procedure=candidate.procedure_type,
                hard_decision=business.get('decision'))
        except Exception as error:
            logger.info('radar1_feedback_unavailable error_type=%s', type(error).__name__)
            return {**business, 'feedback': {'applied': 'unavailable', 'feedback_score': 0.0}}
        adjusted = explanation.get('adjusted_decision') or business['decision']
        updated = {**business, 'feedback': explanation}
        if business['decision'] == 'keep' and adjusted == 'review':
            updated.update(decision='review', priority=2, score=3,
                           business_category='P2_REVIEW',
                           reason_code=business.get('reason_code') or 'REVIEW_AMBIGUOUS_RELEVANCE')
        return updated

    def _record_page_error(self, code):
        if self.active_stats is not None:
            key = 'http_' + str(code)
            self.active_stats[key] += 1

    def _inc(self, stats, key, amount=1):
        stats[key] += amount
        self.report.metrics[key] += amount

    def _warn(self, reason):
        self.report.health = 'DEGRADED'
        if reason not in self.report.health_reasons:
            self.report.health_reasons.append(reason)

    def _trace(self, hit, reason, candidate=None, discovery=None, stats=None):
        event = dict(query_index=stats['query_index'] if stats else None,
            reference=hit.reference, title=hit.title[:250], reason=reason,
            discovered_from=discovery or hit.url, original_discovery_url=discovery or hit.url,
            official_url=candidate.official_url if candidate else None,
            official_resolved_from=candidate.metadata.get('official_resolved_from') if candidate else None,
            source_type=source_role(hit.url, self.config),
            resolution_state=candidate.resolution_state if candidate else UNRESOLVED,
            resolution_error=candidate.resolution_error if candidate else None,
            business_relevance=self._business(candidate) if candidate else
                evaluate_relevance(hit.title, self.config.get('RADAR1_KEYWORD_GROUPS')))
        if len(self.report.trace) < self.config['RADAR1_MAX_CANDIDATES']:
            self.report.trace.append(event)
        logger.info('procurement_decision=%s query=%s reference=%s source=%s', reason,
                    event['query_index'], hit.reference, hit.url)

    def _reject(self, stats, kind, hit, reason, candidate=None, discovery=None):
        self._inc(stats, 'rejected_by_' + kind)
        self.report.metrics['rejected'] += 1
        self._trace(hit, reason, candidate, discovery, stats)
        if kind in {'parser', 'resolution'}:
            self._warn(reason)

    def _truncate(self, reason):
        if reason not in self.report.truncated:
            self.report.truncated.append(reason)

    def _page_type(self, url, page, rows):
        if detail_url(url):
            kind = 'tender_detail'
        elif rows and source_role(url, self.config) == 'OFFICIAL_INSTITUTIONAL':
            kind = 'institutional_procurement'
        elif rows and ('secteur/' in url or 'category' in url):
            kind = 'procurement_category'
        elif rows:
            kind = 'tender_list'
        elif any(word in folded(page.text) for word in ('appel d offres', 'marches publics', 'consultations', 'achats')):
            kind = 'generic_org'
        else:
            kind = 'non_procurement'
        self.report.metrics['page_type_' + kind] += 1
        return kind

    def _budget_available(self, strategy='DISCOVERY'):
        metric = 'resolution_search_calls' if strategy == 'RESOLUTION' else 'discovery_search_calls'
        limit = (self.config.get('RADAR1_RESOLUTION_MAX_CALLS', self.config.get('RADAR1_MAX_RESOLUTION_QUERIES', 4))
                 if strategy == 'RESOLUTION' else
                 min(self.config.get('RADAR1_DISCOVERY_MAX_CALLS', self.config['RADAR1_MAX_QUERIES_PER_RUN']),
                     self.config['RADAR1_MAX_QUERIES_PER_RUN']))
        if self.report.metrics[metric] >= limit:
            self._truncate(('resolution' if strategy == 'RESOLUTION' else 'discovery') + '_query_limit')
            return False
        return True

    def _query(self, query, days, domains, *, strategy='RESOLUTION', family='official_resolution'):
        if not domains or not self._budget_available(strategy):
            return [], None
        if strategy == 'RESOLUTION':
            pass
        self.report.queries_executed += 1
        stats = {**dict.fromkeys(COUNTERS, 0), 'query_index': self.report.queries_executed,
                 'source_strategy': strategy, 'query_family': family,
                 'query_text': query, 'domains': list(domains), 'recency_days': days,
                 'new_identity': 0, 'blocked': 0, 'parser_failures': 0}
        self.report.query_metrics.append(stats)
        self.report.metrics['search_calls'] += 1
        self.report.metrics['resolution_search_calls' if strategy == 'RESOLUTION' else 'discovery_search_calls'] += 1
        try:
            response = self.provider.search(query, recency_days=days, domains=domains)
            self.report.usage_events.append(response)
            self.report.successful_queries += 1
            stats['provider'] = response.diagnostics
            raw = response.raw_results_count if response.raw_results_count is not None else len(response.hits)
            self._inc(stats, 'raw_results_count', raw)
            self.report.metrics['raw_results'] += raw
            self._inc(stats, 'queries_with_results' if raw else 'queries_with_zero_results')
            source_metric = {'PMMP': 'pmmp_raw', 'AGGREGATOR': 'aggregator_raw',
                             'INSTITUTIONAL': 'institutional_raw'}.get(strategy)
            if source_metric:
                self._inc(stats, source_metric, raw)
            if response.diagnostics.get('response_status') not in (None, 'completed'):
                self._warn('provider_partial_response')
            hits = []
            allowed = set()
            for hit in response.hits:
                if not source_role(hit.url, self.config):
                    self._reject(stats, 'source', hit, 'outside_whitelist')
                    continue
                allowed.add(hit.url)
                self.discovered_pages.add(hit.url)
                hits.append(hit)
            self._inc(stats, 'allowed_domain_results', len(allowed))
            self.report.metrics['pages_discovered'] = len(self.discovered_pages)
            return hits, stats
        except SearchProviderError as error:
            stats['error'] = error.kind
            self.report.query_errors.append({'query_index': stats['query_index'], 'kind': error.kind})
            self.report.usage_events.append(error.response)
            self._warn('search_provider_error')
            if len(self.report.query_errors) >= 3 and not self.report.successful_queries:
                self.report.health = 'FAILED'
                raise ProviderUnavailable('Search provider unavailable after three failed queries.')
            return [], stats
        finally:
            self.on_progress()

    def _finish_query(self, stats):
        if stats is not None:
            stats['blocked'] = stats['http_403'] + stats['http_429']
            stats['parser_failures'] = stats['rejected_by_parser']
            logger.info('query=%s strategy=%s family=%s text=%r raw=%s usable=%s new_identity=%s duplicates=%s blocked=%s parser_failures=%s',
                stats['query_index'], stats['source_strategy'], stats['query_family'], stats['query_text'],
                stats['raw_results_count'], stats['candidates_created'], stats['new_identity'],
                stats['duplicates_skipped'], stats['blocked'], stats['parser_failures'])
            if stats['source_strategy'] not in {'RESOLUTION', 'CONTROL'}:
                key = f"{stats['source_strategy']}:{stats['query_family']}"
                saved = self.query_performance.setdefault(key, dict(executions=0, raw_results=0,
                    usable_observations=0, relevant_candidates=0, official_resolution_success=0,
                    zero_results=0, duplicates_skipped=0, generic_pages=0,
                    parser_failures=0, last_successful_at=None))
                saved['executions'] += 1
                saved['raw_results'] += stats['raw_results_count']
                saved['usable_observations'] += stats['candidates_created']
                saved['relevant_candidates'] += stats.get('relevant_candidates', 0)
                saved['official_resolution_success'] += stats.get('official_resolution_success', 0)
                saved['zero_results'] += int(stats['raw_results_count'] == 0)
                saved['duplicates_skipped'] += stats['duplicates_skipped']
                saved['generic_pages'] += stats['generic_pages']
                saved['parser_failures'] += stats['parser_failures']
                if stats['raw_results_count']:
                    saved['last_successful_at'] = today_in_morocco().isoformat()
                self.report.query_performance = self.query_performance
        self.on_progress()

    def _direct_page(self, source):
        """Inspect a public category/search page without spending a provider call."""
        stats = {**dict.fromkeys(COUNTERS, 0), 'query_index': None,
                 'source_strategy': source.strategy, 'query_family': source.family,
                 'query_text': source.url, 'domains': [normalize_domain(source.url)],
                 'recency_days': None, 'new_identity': 0, 'blocked': 0,
                 'parser_failures': 0, 'billable_search': False}
        self.report.query_metrics.append(stats)
        try:
            self.active_stats = stats
            url, page = self.pages.get(source.url)
            self.report.metrics['direct_pages_fetched'] += 1
            rows = extract_rows(page, url)
            stats['page_type'] = self._page_type(url, page, rows)
            stats['raw_results_count'] = len(rows)
            self.report.metrics['raw_results_count'] += len(rows)
            self.report.metrics['raw_results'] += len(rows)
            source_metric = {'PMMP': 'pmmp_raw', 'AGGREGATOR': 'aggregator_raw',
                             'INSTITUTIONAL': 'institutional_raw'}.get(source.strategy)
            if source_metric:
                self.report.metrics[source_metric] += len(rows)
            if rows:
                self.report.metrics['procurement_pages'] += 1
            else:
                self.report.metrics['generic_pages'] += 1
            return rows, stats
        except (OSError, ValueError, TimeoutError) as error:
            self.report.source_errors += 1
            stats['error'] = type(error).__name__
            self._warn('direct_source_unavailable')
            return [], stats

    def _discover(self, hit, stats):
        """Never use final eligibility to discard a discovery container."""
        container = aggregate_title(hit.title) or (not detail_url(hit.url) and not hit.reference)
        if hit.reference and detail_url(hit.url) and not aggregate_title(hit.title):
            return [hit]  # Identity is enough even if the provider calls it a discovery page.
        if hit.kind == 'discovery_page' or container:
            if hit.url in self.expanded_pages:
                return []
            self.expanded_pages.add(hit.url)
            try:
                url, page = self.pages.get(hit.url)
                fields = labelled_fields(page)
                if not fields.get('title') and fields.get('reference') and page.h1:
                    fields['title'] = ' '.join(page.h1).strip()[:2000]
                if detail_url(url) and not aggregate_title(hit.title) and fields.get('title'):
                    return [SearchHit(**fields, url=url, kind='tender', evidence=page.text[:2000])]
                self._inc(stats, 'aggregate_pages_detected')
                rows = extract_rows(page, url)
                self._page_type(url, page, rows)
                if not rows:
                    self._reject(stats, 'parser', hit, 'no_tender_rows_or_detail_fields')
                return rows
            except (OSError, ValueError, TimeoutError) as error:
                self.report.source_errors += 1
                if hit.title and strong_identity(self._normalize(hit), self.config):
                    self._warn('discovery_page_access_limited')
                    return [hit]
                self._reject(stats, 'parser', hit, 'page_fetch_or_parse:' + type(error).__name__ + ':' + str(getattr(error, 'code', '')))
                return []
        return [hit]

    def _normalize(self, hit, discovery=None):
        if not (hit.title.strip() or hit.reference):
            raise ValueError('Discovery requires title or reference')
        # Optional extraction errors must not destroy otherwise usable identity.
        updates = {'title': (hit.title or hit.reference)[:2000], 'evidence': hit.evidence[:20000]}
        for field, limit in (('reference', 255), ('institution', 255), ('location', 500),
                             ('official_date_evidence', 500), ('procedure_type', 100), ('status', 100)):
            value = getattr(hit, field)
            if value and len(value) > limit:
                updates[field] = None if field not in {'status', 'procedure_type'} else 'unknown'
        if hit.deadline_at:
            try:
                if datetime.fromisoformat(hit.deadline_at.replace('Z', '+00:00')).tzinfo is None:
                    updates['deadline_at'] = None
            except ValueError:
                updates['deadline_at'] = None
        candidate = normalize_hit(hit.model_copy(update=updates), self.official)
        role = source_role(hit.url, self.config) or 'DISCOVERY_ONLY'
        procurement = {}
        if hit.estimated_amount:
            amount, currency = _amount(hit.estimated_amount)
            if amount is not None:
                procurement.update(estimated_amount=amount, estimated_currency=currency,
                    estimated_amount_tax_mode='TTC' if 'ttc' in folded(hit.estimated_amount) else
                    'HT' if 'ht' in folded(hit.estimated_amount).split() else 'UNKNOWN',
                    estimated_amount_source='MARCHE_FACILE' if 'marchefacile' in normalize_domain(hit.url) else 'SECONDARY',
                    estimated_amount_verified=False)
        if hit.provisional_bond:
            amount, currency = _amount(hit.provisional_bond)
            if amount is not None:
                procurement.update(provisional_bond_amount=amount, provisional_bond_currency=currency)
        # Supported Moroccan procurement indexes establish country scope, while
        # location remains explicitly unknown until enrichment.
        morocco = True if role == 'PROCUREMENT_AGGREGATOR' and candidate.morocco_related is None else candidate.morocco_related
        return candidate.model_copy(update={'url': hit.url, 'source_type': role, 'morocco_related': morocco,
            **procurement,
            'metadata': {**candidate.metadata, 'original_discovery_url': discovery or hit.url,
                         'discovered_from': discovery or hit.url, 'pipeline': 'procurement_v5'}})

    def _observe(self, hit, stats, discovery=None):
        if self.examined >= self.config['RADAR1_MAX_CANDIDATES']:
            self._truncate('candidate_limit')
            return None
        self.examined += 1
        self._inc(stats, 'individual_tenders_extracted')
        if not source_role(hit.url, self.config):
            self._reject(stats, 'source', hit, 'linked_source_outside_whitelist', discovery=discovery)
            return None
        try:
            candidate = self._normalize(hit, discovery)
        except (ValueError, TypeError) as error:
            reason = 'normalization:' + (','.join('.'.join(map(str, item['loc'])) for item in error.errors())
                                        if isinstance(error, ValidationError) else type(error).__name__)
            self._reject(stats, 'parser', hit, reason, discovery=discovery)
            return None
        self.report.observations.append(candidate)
        self._inc(stats, 'candidates_created')
        self.report.metrics['usable_results'] += 1
        observation_metric = ('pmmp_observations' if candidate.source_type == 'OFFICIAL_PROCUREMENT' else
            'marchefacile_observations' if normalize_domain(candidate.url) == 'marchefacile.ma' else
            'institutional_observations' if candidate.source_type == 'OFFICIAL_INSTITUTIONAL' else None)
        if observation_metric:
            self.report.metrics[observation_metric] += 1
        family = stats.get('query_family')
        if family in {'architecture', 'rehabilitation', 'heritage', 'urbanism',
                      'project_management', 'built_environment'}:
            key = 'observations_' + family
            stats[key] = stats.get(key, 0) + 1
            self.report.metrics[key] = self.report.metrics.get(key, 0) + 1
        return candidate

    def _lookup(self, query):
        if query in self.lookup_cache:
            return self.lookup_cache[query]
        domain = query.split('site:', 1)[1].split()[0] if 'site:' in query else None
        domains = (domain,) if domain in self.official else self.official
        hits, stats = self._query(query, 90, domains)
        if stats is None:
            return []
        found = []
        previous_stats, self.active_stats = self.active_stats, stats
        for hit in hits:
            observed_url = hit.url
            target = detail_from_official_identity(hit.url)
            if target and not detail_url(hit.url):
                hit = hit.model_copy(update={'url': target, 'kind': 'discovery_page'})
            for row in self._discover(hit, stats):
                item = self._observe(row, stats, hit.url)
                if item is None or not detail_url(item.url):
                    continue
                if item.source_type not in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}:
                    continue
                try:
                    item = enrich_detail(item, self.pages)
                    item = verify_detail(item, self.pages)
                    item = self._with_metadata(item, observed_official_url=observed_url)
                    found.append(item)
                except (OSError, ValueError, TimeoutError) as error:
                    self._reject(stats, 'parser', row, 'resolution_detail:' + type(error).__name__, item)
        self._finish_query(stats)
        self.active_stats = previous_stats
        self.lookup_cache[query] = found
        return found

    def _linked_official(self, candidate):
        """Follow exposed official offer links before spending on another search."""
        secondary_url, page = self.pages.get(candidate.url or candidate.metadata['discovery_url'])
        secondary = procurement_metadata(page, secondary_url)
        links = list(dict.fromkeys(urljoin(candidate.url, href) for href, _ in page.links))
        links = [url for url in links if detail_url(url) and source_role(url, self.config) in
                 {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}]
        for url in links[:5]:
            try:
                found = enrich_detail(candidate.model_copy(update={'url': url, 'official_url': url}), self.pages)
                # The original identity must be visible on the official snapshot.
                _, official_page = self.pages.get(url)
                identity = candidate.reference or candidate.title
                if not identity or folded(identity) not in folded(official_page.text) or not OfficialLinkResolver.matches(candidate, found):
                    continue
                fallback = {}
                if found.estimated_amount is None and secondary.get('estimated_amount') is not None:
                    fallback = {key: value for key, value in secondary.items()
                                if key.startswith('estimated_')}
                return found.model_copy(update={'source_type': source_role(url, self.config), **fallback,
                    'metadata': {**candidate.metadata, 'official_resolved_from': candidate.url}})
            except (OSError, ValueError, TimeoutError):
                continue
        return None

    def _inspect_official_link(self, candidate):
        """An indexed public page may be readable by the hosted web tool when
        direct GET is denied. No challenges, forms or private access are used.
        The returned official URL must be tool-observed and locally verified.
        """
        url = candidate.url or candidate.metadata['discovery_url']
        query = (f'Open public procurement page {url}. For reference "{candidate.reference or candidate.title}", '
                 'follow its explicit official tender/detail hyperlink (not its homepage or DCE download). '
                 'Return that official notice and its exact observed URL. Do not invent or construct a URL.')
        hits, stats = self._query(query, 90, tuple(dict.fromkeys((*self.official, normalize_domain(url)))))
        if stats is None:
            return None
        matches = []
        for hit in hits:
            observed_url = hit.url
            if not detail_url(hit.url):
                target = detail_from_official_identity(hit.url)
                if target:
                    hit = hit.model_copy(update={'url': target, 'reference': candidate.reference,
                                                'title': candidate.title, 'kind': 'tender'})
            if not detail_url(hit.url) or source_role(hit.url, self.config) not in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}:
                continue
            for row in self._discover(hit, stats):
                found = self._observe(row, stats, url)
                if found is None:
                    continue
                try:
                    found = enrich_detail(found, self.pages)
                    if OfficialLinkResolver.matches(candidate, found):
                        found = self._with_metadata(found, observed_official_url=observed_url)
                        matches.append(found)
                except (OSError, ValueError, TimeoutError) as error:
                    self._reject(stats, 'parser', row, 'hosted_link_detail:' + type(error).__name__, found)
        self._finish_query(stats)
        if len({(item.reference, item.institution) for item in matches}) != 1:
            return None
        found = matches[0]
        return found.model_copy(update={'metadata': {**found.metadata, **candidate.metadata,
            'observed_official_url': found.metadata.get('observed_official_url'), 'official_resolved_from': url}})

    def _process(self, hit, radar, stats, discovery=None):
        signature = (folded(hit.reference or ''), folded(hit.institution or ''),
                     folded(hit.title or ''))
        if signature in self.discovery_seen and any(signature):
            self._inc(stats, 'duplicates_skipped')
            self._inc(stats, 'deduped_before_enrichment')
            return
        if any(signature):
            self.discovery_seen.add(signature)
        candidate = self._observe(hit, stats, discovery)
        if candidate is None:
            return
        keys = {(i, key) for i, key in enumerate(identity_keys(candidate)) if key and
                (i != 0 or (detail_url(candidate.url) and candidate.source_type in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'})) and (i != 2 or candidate.institution)}
        seen = bool(keys & self.seen)
        self.seen.update(keys)
        if seen or self.known_unchanged(candidate):
            self._inc(stats, 'duplicates_skipped')
            self._inc(stats, 'deduped_before_enrichment')
            self._trace(hit, 'known_unchanged_or_duplicate', discovery=discovery, stats=stats)
            return
        stats['new_identity'] += 1
        self.report.metrics['unique_identities'] += 1
        context = ' '.join(filter(None, (candidate.raw_text, candidate.institution,
                                         candidate.location_evidence)))
        # Cheap pre-detail filter — skip obvious noise before HTTP enrichment.
        preliminary = preliminary_plausible(candidate.title, context)
        if preliminary['decision'] == 'reject':
            candidate = candidate.model_copy(update={'business_category': 'REJECT'})
            candidate = self._with_metadata(
                candidate, business_relevance=preliminary, preliminary_relevance='reject')
            logger.info('radar1_preliminary_reject reason=%s title=%s',
                        preliminary.get('reason_code'), (candidate.title or '')[:120])
            self._reject(stats, 'relevance', hit, 'irrelevant_business_purpose', candidate, discovery)
            return
        candidate = self._with_metadata(candidate, preliminary_relevance='continue')
        business = self._business(candidate, context)
        candidate = candidate.model_copy(update={'business_category': business['business_category']})
        candidate = self._with_metadata(candidate, business_relevance=business)
        meaningful_title = bool(candidate.title and folded(candidate.title) != folded(candidate.reference or '')
                                and folded(candidate.title) not in {'consultation pmmp', 'details', 'detail'})
        if meaningful_title and business['decision'] == 'reject':
            if self._should_enrich_before_reject(business, candidate):
                logger.info(
                    'radar1_defer_reject_for_detail reason=%s code=%s title=%s',
                    business.get('rejection_reason'), business.get('reason_code'),
                    (candidate.title or '')[:120])
                candidate = self._with_metadata(candidate, preliminary_relevance='plausible_continue')
            else:
                reason = business.get('rejection_reason')
                if reason == 'topography_only':
                    self._inc(stats, 'topography_rejected')
                elif reason == 'technical_only':
                    self._inc(stats, 'technical_only_rejected')
                logger.info('radar1_hard_reject reason=%s code=%s title=%s',
                            reason, business.get('reason_code'), (candidate.title or '')[:120])
                self._reject(stats, 'relevance', hit, 'irrelevant_business_purpose', candidate, discovery)
                return
        snapshot = discovery_snapshot(candidate)
        original = candidate
        attempts, errors = [], []
        query_start = len(self.report.query_metrics)
        self.report.metrics['relevant_candidates'] += 1
        stats['relevant_candidates'] = stats.get('relevant_candidates', 0) + 1
        self._inc(stats, 'official_resolution_attempts')
        resolver = OfficialLinkResolver(self.official)
        try:
            if candidate.source_type in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'} and detail_url(candidate.url):
                try:
                    candidate = enrich_detail(candidate, self.pages)
                    logger.info('radar1_detail_enrichment=ok url=%s', (candidate.official_url or '')[:120])
                except (OSError, ValueError, TimeoutError) as error:
                    if 'mismatch' in str(error).lower():
                        raise
                    errors.append(str(error)[:150])
                    candidate = self._with_metadata(candidate, detail_enrichment_status='unavailable')
                    logger.info('radar1_detail_enrichment=unavailable error_type=%s', type(error).__name__)
                    candidate = resolver.resolve(original.model_copy(update={
                        'official_confirmation': False, 'official_url': None}), self._lookup)
                    attempts.extend(resolver.attempts)
            else:
                # Identity recovery does not depend on opening a secondary page.
                candidate = resolver.resolve(candidate, self._lookup)
                attempts.extend(resolver.attempts)
                if not candidate.official_confirmation:
                    try:
                        linked = self._linked_official(original)
                    except (OSError, ValueError, TimeoutError) as error:
                        errors.append(type(error).__name__ + ':' + str(getattr(error, 'code', '')))
                        linked = None
                    candidate = linked or self._inspect_official_link(original) or candidate
            if candidate.official_confirmation:
                candidate = OfficialLinkResolver.merge_secondary_procurement(original, candidate)
            if not candidate.official_confirmation or not detail_url(candidate.official_url):
                raise ValueError('official_resolution_failed')
            if candidate.source_status in {'closed', 'expired', 'awarded', 'cancelled'} or (candidate.deadline and candidate.deadline < today_in_morocco()):
                self._reject(stats, 'freshness', hit, 'closed_or_expired', candidate, discovery)
                return
            candidate = verify_detail(candidate, self.pages)
            candidate = candidate.model_copy(update={'url': canonical_detail_url(candidate.official_url),
                'official_url': canonical_detail_url(candidate.official_url)})
            candidate = with_resolution(candidate, VERIFIED, attempts=[query['query_text'] for query in self.report.query_metrics[query_start:]])
        except (OSError, ValueError, TimeoutError) as error:
            errors.append(str(error)[:150])
            # Explicit contradictions or closed official evidence never become fallback.
            contradicted = any(word in str(error).lower() for word in ('mismatch', 'closed procurement'))
            fallback = original
            if not contradicted and credible_fallback(fallback, self.config):
                candidate = with_resolution(fallback, CREDIBLE, error='; '.join(errors), attempts=[query['query_text'] for query in self.report.query_metrics[query_start:]])
                self._warn('official_verification_pending')
            else:
                candidate = with_resolution(fallback, UNRESOLVED, error='; '.join(errors), attempts=[query['query_text'] for query in self.report.query_metrics[query_start:]])
                self._inc(stats, 'unresolved')
                self._reject(stats, 'resolution', hit, 'official_resolution_failed', candidate, discovery)
                return
        context = ' '.join(filter(None, (candidate.raw_text, candidate.institution,
                                         candidate.location_evidence)))
        final_business = self._apply_feedback(self._business(candidate), candidate, context)
        candidate = candidate.model_copy(update={'business_category': final_business['business_category']})
        if final_business['decision'] == 'reject' or aggregate_title(candidate.title):
            reason = final_business.get('rejection_reason')
            if reason == 'topography_only':
                self._inc(stats, 'topography_rejected')
            elif reason == 'technical_only':
                self._inc(stats, 'technical_only_rejected')
            logger.info('radar1_final_reject reason=%s code=%s feedback=%s',
                        reason, final_business.get('reason_code'),
                        (final_business.get('feedback') or {}).get('feedback_score'))
            self._reject(stats, 'relevance', hit, 'irrelevant_business_purpose', candidate, discovery)
            return
        candidate = self._with_metadata(
            candidate, discovery_snapshot=snapshot, business_relevance=final_business)
        logger.info('radar1_final_decision=%s category=%s reason=%s feedback=%s enrichment=%s',
                    final_business.get('decision'), final_business.get('business_category'),
                    final_business.get('reason_code'),
                    (final_business.get('feedback') or {}).get('feedback_score'),
                    (candidate.metadata or {}).get('detail_enrichment_status'))
        if candidate.resolution_state == VERIFIED and (candidate.morocco_related is not True or not candidate.institution or not candidate.deadline):
            self._reject(stats, 'parser', hit, 'missing_geography_buyer_or_deadline', candidate, discovery)
            return
        decision = radar.validate_candidate(candidate)
        if not decision.accepted:
            kind = 'freshness' if any('OLD' in r or 'EXPIRED' in r or 'FUTURE' in r for r in decision.reasons) else 'parser'
            self._reject(stats, kind, hit, ','.join(decision.reasons), candidate, discovery)
            return
        if candidate.resolution_state == VERIFIED:
            self._inc(stats, 'official_urls_resolved')
            self._inc(stats, 'verified_official')
            stats['official_resolution_success'] = stats.get('official_resolution_success', 0) + 1
        else:
            self._inc(stats, 'unverified_credible')
        business = final_business
        self._inc(stats, 'architecture_kept')
        title = folded(candidate.title)
        if business['priority'] == 1:
            self._inc(stats, 'heritage_kept')
        if 'consultation architecturale' in title:
            self._inc(stats, 'consultation_architecturale_kept')
        if 'concours architectural' in title:
            self._inc(stats, 'concours_architectural_kept')
        self._inc(stats, 'kept_p' + str(business['priority']))
        self.report.candidates.append(candidate)
        self._trace(hit, 'verified_offer' if candidate.resolution_state == VERIFIED else 'credible_fallback', candidate, discovery, stats)

    def collect(self, radar):
        control = self.config.get('RADAR1_CONTROL_REFERENCE')
        if control:
            # Development-only opt-in, no hard-coded references in production.
            plans = [('CONTROL', 'exact_reference', f'site:marchespublics.gov.ma "{control}"', self.pmmp_domains, 90)]
        else:
            plans = [(p.strategy, p.family, p.text, p.domains, p.recency_days) for p in
                     build_discovery_plan(self.config, mode=self.config.get('RADAR1_SEARCH_MODE', 'normal_coverage'),
                                          performance=self.query_performance)]
        try:
            target = min(self.config.get('RADAR1_TARGET_UNIQUE_OBSERVATIONS', 15),
                         self.config.get('RADAR1_TARGET_OBSERVATIONS', 15))
            required_sources = 2 if self.direct_discovery_enabled else 1
            required_families = (self.config.get('RADAR1_MIN_PRODUCTIVE_FAMILIES', 4)
                                 if self.direct_discovery_enabled else 1)
            source_yield = set()
            family_yield = {}
            if not control and self.direct_discovery_enabled:
                for source in direct_discovery_plan(self.config):
                    productive_families = len({family for (_, family), value in family_yield.items() if value > 0})
                    if (self.report.metrics['relevant_candidates'] >= target and
                            len(source_yield) >= required_sources and productive_families >= required_families):
                        break
                    # A productive first ladder step suppresses its normalized/accent fallback.
                    if source.variant and family_yield.get((source.strategy, source.family), 0) >= 3:
                        continue
                    rows, stats = self._direct_page(source)
                    before = self.report.metrics['relevant_candidates']
                    for row in rows[:self.config.get('RADAR1_QUERY_OBSERVATION_LIMIT', 20)]:
                        self._process(row, radar, stats, source.url)
                    gained = self.report.metrics['relevant_candidates'] - before
                    family_yield[(source.strategy, source.family)] = (
                        family_yield.get((source.strategy, source.family), 0) + gained)
                    if gained:
                        source_yield.add(source.strategy)
                    self._finish_query(stats)
                    self.active_stats = None
            for strategy, family, query, domains, days in plans:
                if not self._budget_available('DISCOVERY') or self.examined >= self.config['RADAR1_MAX_CANDIDATES']:
                    break
                minimum = min(self.config.get('RADAR1_MIN_SEARCH_QUERIES', 0),
                              self.config.get('RADAR1_DISCOVERY_MAX_CALLS',
                                              self.config['RADAR1_MAX_QUERIES_PER_RUN']))
                productive_families = len({family for (_, family), value in family_yield.items() if value > 0})
                if ((self.direct_discovery_enabled or
                        self.report.metrics['discovery_search_calls'] >= minimum) and
                        self.report.metrics['relevant_candidates'] >= target and
                        len(source_yield) >= required_sources and productive_families >= required_families):
                    break
                if family_yield.get((strategy, family), 0) >= 3:
                    continue
                if control and self.report.candidates:
                    break
                hits, stats = self._query(query, days, domains, strategy=strategy, family=family)
                if stats is None:
                    continue
                self.active_stats = stats
                query_limit = self.config.get('RADAR1_QUERY_OBSERVATION_LIMIT', 20)
                for hit_index, hit in enumerate(hits):
                    if self.examined >= self.config['RADAR1_MAX_CANDIDATES']:
                        self._truncate('candidate_limit')
                        break
                    if stats['individual_tenders_extracted'] >= query_limit:
                        stats['deferred_source_pages'] = len(hits) - hit_index
                        self._truncate('query_observation_limit')
                        break
                    for row in self._discover(hit, stats):
                        if self.examined >= self.config['RADAR1_MAX_CANDIDATES']:
                            self._truncate('candidate_limit')
                            break
                        if stats['individual_tenders_extracted'] >= query_limit:
                            self._truncate('query_observation_limit')
                            break
                        if control and folded(control) not in folded((row.reference or '') + ' ' + row.title):
                            self._inc(stats, 'control_reference_filtered')
                            continue
                        self._process(row, radar, stats, hit.url)
                gained = stats.get('relevant_candidates', 0)
                family_yield[(strategy, family)] = family_yield.get((strategy, family), 0) + gained
                if gained:
                    source_yield.add(strategy)
                self._finish_query(stats)
                self.active_stats = None
            paid_calls = self.report.metrics['search_calls']
            kept = len(self.report.candidates)
            self.report.metrics['relevant_observations_per_search_call'] = round(
                self.report.metrics['relevant_candidates'] / paid_calls, 3) if paid_calls else None
            self.report.metrics['final_kept_per_search_call'] = round(
                kept / paid_calls, 3) if paid_calls else None
            if not self.report.successful_queries and self.report.queries_executed:
                self.report.health = 'FAILED'
                raise ProviderUnavailable('All search queries failed.')
            useful_paths = {q['source_strategy'] for q in self.report.query_metrics
                            if q.get('candidates_created', 0) and q['source_strategy'] != 'RESOLUTION'}
            if self.report.metrics['pmmp_observations']:
                useful_paths.add('PMMP')
            if self.report.metrics['marchefacile_observations']:
                useful_paths.add('AGGREGATOR')
            if self.report.metrics['institutional_observations']:
                useful_paths.add('INSTITUTIONAL')
            if not self.report.metrics['usable_results']:
                self._warn('zero_raw_results' if not self.report.metrics['raw_results'] else 'zero_usable_observations')
            elif not self.report.metrics['relevant_candidates']:
                self._warn('zero_relevant_observations')
            if self.report.metrics['rejected_by_source'] > self.report.metrics['candidates_created']:
                self._warn('most_discovered_links_outside_whitelist')
            if (self.report.health == 'DEGRADED' and not self.report.candidates and
                    self.report.queries_executed >= self.config.get('RADAR1_ZERO_YIELD_QUERY_LIMIT', 4)):
                self.report.metrics['cost_warning'] = True
            if self.report.candidates and (self.report.health == 'DEGRADED' or
                    len(useful_paths) < required_sources and len(self.report.candidates) < target):
                self.report.health = 'PARTIAL'
            self.report.candidates.sort(key=lambda c: (c.resolution_state == VERIFIED, c.publication_date or date.min), reverse=True)
            return self.report.candidates
        finally:
            logger.info('collection_totals health=%s metrics=%s reasons=%s', self.report.health,
                        self.report.metrics, self.report.health_reasons)
            self.on_progress()
