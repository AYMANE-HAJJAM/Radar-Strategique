import re
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from app.modules.radar2_projects.schemas import ProjectCandidate
from app.core.collector_base import sources_unchanged, CollectionReport, ProviderUnavailable, query_batches, run_source_adapters, paid_search_budget
from app.integrations.http.html import PublicPages, AccessLimitedPages
from app.modules.radar2_projects.policy import classify_signal, folded, parse_date
from app.integrations.openai.base import SearchProviderError
from app.core.dedup import identity_keys


QUERIES = (
    'projet réhabilitation architecture Maroc',
    'convention réhabilitation médina',
    'programme aménagement urbain Maroc',
    'projet patrimoine Maroc',
    'projet équipement culturel Maroc',
    'programme développement territorial Maroc',
    'projet architecture publique Maroc',
    'étude préalable aménagement Maroc',
)
COUNTERS = ('direct_pages', 'paid_search_calls', 'resolution_search_calls', 'raw_results',
    'project_observations', 'official_confirmed', 'secondary_only', 'duplicates', 'updates',
    'rejected_vague', 'rejected_old', 'rejected_irrelevant', 'rejected_completed',
    'rejected_tender', 'final_kept', 'maturity_a', 'maturity_b', 'maturity_c', 'maturity_d')


class ProjectsCollector:
    def __init__(self, provider, config, *, pages=None):
        self.provider, self.config = provider, config
        self.report = CollectionReport(metrics={**dict.fromkeys(COUNTERS, 0), 'collector_health': 'HEALTHY'})
        self.on_progress = lambda: None
        self.known_unchanged = lambda candidate: False
        self.source_recent = lambda url, days: False
        self.domains = tuple(config.get('RADAR2_SOURCE_WHITELIST', ()))
        self.official_domains = tuple(config.get('RADAR2_OFFICIAL_DOMAINS', ()))
        self.secondary_domains = tuple(config.get('RADAR2_SECONDARY_DOMAINS', ()))
        self.pages = AccessLimitedPages(pages or PublicPages(self.domains, config.get('SOURCE_HTTP_TIMEOUT_SECONDS', 20)), {'http_403': 0, 'http_429': 0})
        self.seen = set()

    @staticmethod
    def _host(url):
        return (urlsplit(url).hostname or '').lower().removeprefix('www.')

    def _official(self, url):
        host = self._host(url)
        return any(host == d or host.endswith('.' + d) for d in self.official_domains)

    def _date_from_text(self, text):
        match = re.search(r'\b(20\d{2}-\d{2}-\d{2}|\d{2}/\d{2}/20\d{2})\b', text)
        if match:
            return parse_date(match.group())
        months = {'janvier': 1, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
                  'juillet': 7, 'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11, 'decembre': 12}
        value = folded(text)
        match = re.search(r'\b(\d{1,2})\s+(' + '|'.join(months) + r')\s+(20\d{2})\b', value)
        return datetime(int(match[3]), months[match[2]], int(match[1])).date() if match else None

    def _candidate(self, *, title, url, evidence, institution=None, publication_date=None, location=None):
        published = parse_date(publication_date) if isinstance(publication_date, str) else publication_date
        published = published or self._date_from_text(evidence)
        facts = classify_signal(title, evidence, published)
        if facts['rejection']:
            key = {'vague': 'rejected_vague', 'old': 'rejected_old', 'irrelevant': 'rejected_irrelevant',
                   'completed': 'rejected_completed', 'published_tender': 'rejected_tender'}[facts['rejection']]
            self.report.metrics[key] += 1
            return None
        official = self._official(url)
        return ProjectCandidate(title=title[:2000], project_name=title[:2000],
            signal_type=facts['signal_type'], maturity=facts['maturity'],
            institution=institution, location=location, project_scope=', '.join(facts['scope'])[:2000],
            estimated_budget=facts['budget'], partners=[], announcement_date=published,
            publication_date=published, source_url=url, url=url, official_url=url if official else None,
            source=self._host(url), source_quality='OFFICIAL_PRIMARY' if official else 'RELIABLE_SECONDARY',
            source_status='active', relevance_priority=facts['priority'],
            evidence_summary=' '.join(evidence.split())[:2000], signal_evidence=' '.join(evidence.split())[:2000],
            morocco_related=True, current_evidence=True, project_completed=facts['completed'],
            new_phase_confirmed=facts['recent_update'], published_tender=facts['tender'],
            financing_secured=facts['signal_type'] == 'FINANCING_APPROVED',
            program_approved=facts['signal_type'] == 'PROGRAM_APPROVED',
            officially_announced=facts['signal_type'] in {'PROJECT_ANNOUNCED', 'CONVENTION_SIGNED'},
            vague_statement=facts['vague'], future_opportunity_uncertain=facts['maturity'] == 'C',
            metadata={'discovery_url': url, 'source_type': 'OFFICIAL' if official else 'SECONDARY'})

    def _add(self, candidate):
        if candidate is None:
            return
        self.report.metrics['project_observations'] += 1
        keys = {key for key in identity_keys(candidate) if key}
        if keys & self.seen:
            self.report.metrics['duplicates'] += 1
            return
        self.seen.update(keys)
        if self.known_unchanged(candidate):
            self.report.metrics['duplicates'] += 1
            return
        self.report.candidates.append(candidate)
        self.report.observations.append(candidate)
        self.report.metrics['official_confirmed' if candidate.official_url else 'secondary_only'] += 1
        self.report.metrics['maturity_' + candidate.maturity.lower()] += 1
        self.report.metrics['final_kept'] += 1

    def extract_candidates(self, *, title, url, evidence, **facts):
        """Split explicit bullet/paragraph project lists while avoiding sentence-level fragmentation."""
        blocks = [b.strip(' \t-*•') for b in re.split(r'[\r\n]+', evidence) if b.strip()]
        observed = facts.get('publication_date')
        observed = parse_date(observed) if isinstance(observed, str) else observed
        concrete = [b for b in blocks if len(b) >= 25 and classify_signal(b, b, observed)['signal_type']]
        if len(concrete) < 2:
            candidate = self._candidate(title=title, url=url, evidence=evidence, **facts)
            return [candidate] if candidate else []
        output = []
        for block in concrete:
            candidate = self._candidate(title=block[:500], url=url, evidence=block, **facts)
            if candidate:
                output.append(candidate)
        return output

    def _direct(self):
        details_fetched = 0
        def consume(item, result):
            nonlocal details_fetched
            for candidate in self.extract_candidates(title=item.get('title') or result.source.name,
                    url=item.get('url') or result.url, evidence=item.get('evidence') or item.get('title') or '',
                    publication_date=item.get('date'), institution=result.source.name):
                self._add(candidate)
            title = item.get('title') or ''
            if (details_fetched < self.config.get('RADAR2_DIRECT_PAGE_LIMIT', 12) and
                    any(word in folded(title) for word in ('projet', 'programme', 'rehabilitation', 'restauration',
                        'amenagement', 'patrimoine', 'medina', 'architecture', 'convention', 'etude'))):
                try:
                    final, detail = self.pages.get(item.get('url') or result.url)
                    details_fetched += 1
                    self.report.metrics['direct_pages'] += 1
                    for candidate in self.extract_candidates(title=' '.join(detail.h1).strip() or title,
                            url=final, evidence=detail.text, institution=result.source.name,
                            publication_date=self._date_from_text(detail.text)):
                        self._add(candidate)
                except (OSError, ValueError, TimeoutError):
                    pass
        run_source_adapters(self, consume)
        if getattr(self, 'source_adapters', None):
            return
        limit = self.config.get('RADAR2_DIRECT_PAGE_LIMIT', 12)
        for feed in self.config.get('RADAR2_DIRECT_FEEDS', ()):
            if self.report.metrics['direct_pages'] >= limit:
                break
            try:
                url, page = self.pages.get(feed)
                self.report.metrics['direct_pages'] += 1
                links = []
                for href, label in page.links:
                    target = urljoin(url, href)
                    if self._official(target) and len(label.strip()) > 20 and any(
                            word in folded(label) for word in ('projet', 'rehabilitation', 'amenagement',
                            'patrimoine', 'medina', 'architecture', 'urban', 'convention', 'programme')):
                        links.append((target, label.strip()))
                for target, label in list(dict.fromkeys(links))[:max(0, limit-self.report.metrics['direct_pages'])]:
                    if self.source_recent(target, self.config.get('RADAR2_SOURCE_REFRESH_DAYS', 7)):
                        continue
                    try:
                        final_url, detail = self.pages.get(target)
                        self.report.metrics['direct_pages'] += 1
                        title = ' '.join(detail.h1).strip() or label
                        for candidate in self.extract_candidates(title=title, url=final_url, evidence=detail.text,
                                                  publication_date=self._date_from_text(detail.text)):
                            self._add(candidate)
                    except (OSError, ValueError, TimeoutError):
                        continue
            except (OSError, ValueError, TimeoutError):
                continue

    def _resolve(self, candidate):
        if candidate.official_url or self.report.metrics['resolution_search_calls'] >= self.config['RADAR2_RESOLUTION_MAX_SEARCHES']:
            return candidate
        query = f'"{candidate.project_name[:120]}"'
        self.report.metrics['resolution_search_calls'] += 1
        try:
            response = self.provider.search(query, recency_days=90, domains=self.official_domains)
            self.report.usage_events.append(response)
            self.report.queries_executed += 1
            for hit in response.hits:
                if self._official(hit.url) and folded(candidate.project_name) in folded(hit.title + ' ' + hit.evidence):
                    return candidate.model_copy(update={'official_url': hit.url,
                        'source_quality': 'OFFICIAL_PRIMARY',
                        'metadata': {**candidate.metadata, 'official_resolved_from': hit.url}})
        except SearchProviderError as error:
            self.report.usage_events.append(error.response)
            self.report.query_errors.append({'query': query, 'kind': error.kind})
        finally:
            self.on_progress()
        return candidate

    def collect(self, radar):
        self._direct()
        fetched = 0
        target = self.config.get('RADAR2_TARGET_OBSERVATIONS', 12)
        direct_yield = len(self.report.candidates)
        fallback = paid_search_budget(self.config, 2) if hasattr(self, 'source_adapters') else self.config['RADAR2_DISCOVERY_MAX_SEARCHES']
        budget = 0 if direct_yield >= self.config.get('RADAR2_DIRECT_MIN_YIELD', 2) else fallback
        if sources_unchanged(self.report): budget = 0
        self.report.metrics['escalation_level'] = 0 if budget == 0 else 1
        queries = QUERIES[:min(self.config['RADAR2_DISCOVERY_MAX_SEARCHES'], budget)]
        for query, themes in query_batches(queries, self.config.get('RADAR2_SEARCH_BATCH_SIZE', 3)):
            if len(self.report.candidates) >= target:
                break
            self.report.metrics['paid_search_calls'] += 1
            try:
                response = self.provider.search(query, recency_days=30, domains=self.domains)
                self.report.usage_events.append(response)
                self.report.queries_executed += len(themes)
                self.report.successful_queries += 1
                self.report.metrics['raw_results'] += response.raw_results_count if response.raw_results_count is not None else len(response.hits)
                for hit in response.hits:
                    candidates = self.extract_candidates(title=hit.title, url=hit.url, evidence=hit.evidence,
                            institution=hit.institution, publication_date=hit.publication_date, location=hit.location)
                    if not candidates and fetched < self.config.get('RADAR2_SEARCH_DETAIL_FETCH_LIMIT', 10):
                        try:
                            final, detail = self.pages.get(hit.url); fetched += 1
                            candidates = self.extract_candidates(title=' '.join(detail.h1).strip() or hit.title,
                                url=final, evidence=detail.text, institution=hit.institution,
                                publication_date=hit.publication_date, location=hit.location)
                        except (OSError, ValueError, TimeoutError):
                            pass
                    for candidate in candidates:
                        self._add(candidate)
            except SearchProviderError as error:
                self.report.usage_events.append(error.response)
                self.report.query_errors.append({'query': query, 'kind': error.kind})
                if len(self.report.query_errors) >= 3 and not self.report.successful_queries:
                    self.report.health = 'FAILED'
                    raise ProviderUnavailable('Radar 2 search provider unavailable.')
            self.on_progress()
        self.report.candidates = [self._resolve(item) for item in self.report.candidates]
        self.report.metrics['official_confirmed'] = sum(bool(item.official_url) for item in self.report.candidates)
        self.report.metrics['secondary_only'] = len(self.report.candidates) - self.report.metrics['official_confirmed']
        if not self.report.candidates:
            self.report.health = 'DEGRADED'
            self.report.health_reasons.append('no_current_project_signals')
        elif self.report.metrics['secondary_only']:
            self.report.health = 'PARTIAL'
            self.report.health_reasons.append('secondary_confirmation_pending')
        self.report.metrics['collector_health'] = self.report.health
        self.on_progress()
        return self.report.candidates
