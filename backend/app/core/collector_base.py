from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class CollectionReport:
    candidates: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    query_metrics: list = field(default_factory=list)
    health: str = 'HEALTHY'
    health_reasons: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    queries_executed: int = 0
    successful_queries: int = 0
    query_errors: list = field(default_factory=list)
    source_errors: int = 0
    truncated: list = field(default_factory=list)
    usage_events: list = field(default_factory=list)
    query_performance: dict = field(default_factory=dict)


class Collector(Protocol):
    report: CollectionReport
    def collect(self, radar): ...


class ProviderUnavailable(RuntimeError):
    kind = 'search_provider_unavailable'


def query_batches(queries, size):
    """Combine related discovery themes into one bounded provider request."""
    size = max(1, int(size))
    values = list(queries)
    for index in range(0, len(values), size):
        group = values[index:index + size]
        if len(group) == 1:
            yield group[0], group
            continue
        # Quoted OR terms preserve each precise production query while allowing
        # the provider to search them in one request.
        yield 'Search each theme and return concrete hits for every productive theme: ' + \
              ' OR '.join(f'({query})' for query in group), group


def run_source_adapters(collector, consume):
    """Run due direct sources and expose normalized items to a radar collector."""
    report = collector.report
    metrics = report.metrics
    metrics.setdefault('direct_http_requests', 0)
    metrics.setdefault('conditional_304_count', 0)
    metrics.setdefault('source_pages_changed', 0)
    metrics.setdefault('source_pages_unchanged', 0)
    metrics.setdefault('source_health', {})
    for adapter in getattr(collector, 'source_adapters', ()):
        result = adapter.fetch()
        metrics['direct_http_requests'] += result.http_requests
        metrics['conditional_304_count'] += int(result.status == 'NOT_MODIFIED')
        metrics['source_pages_changed'] += int(result.status == 'CHANGED')
        metrics['source_pages_unchanged'] += int(result.status in {'UNCHANGED', 'NOT_MODIFIED'})
        metrics['source_health'][result.source.name] = (
            'HEALTHY' if result.status in {'CHANGED', 'UNCHANGED', 'NOT_MODIFIED'} else result.status)
        if result.status == 'CHANGED':
            for item in result.items:
                consume(item, result)


def paid_search_budget(config, radar_number):
    return max(0, int(config.get(f'RADAR{radar_number}_NORMAL_SEARCH_BUDGET', 0)))


def sources_unchanged(report):
    """A scheduled cache hit is not a discovery gap needing another paid search."""
    metrics = report.metrics
    return bool(metrics.get('source_pages_unchanged', 0) and not metrics.get('source_pages_changed', 0))
