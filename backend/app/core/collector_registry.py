from app.modules.radar1_markets.collector import MarketsCollector
from app.modules.radar2_projects.collector import ProjectsCollector
from app.modules.radar3_institutions.collector import InstitutionsCollector
from app.modules.radar4_policies.collector import PoliciesCollector
from app.modules.radar5_funding.collector import FundingCollector
from app.integrations.openai.registry import build_search_provider
from app.integrations.openai.base import SearchProviderError
from app.core.collector_base import ProviderUnavailable
from app.integrations.openai.disabled import DisabledSearchProvider
from app.db.repositories.source_state import SourceStateService
from app.integrations.http.adapters import build_source_adapters
from app.core.source_catalog import DEFAULT_SOURCES

COLLECTORS = {'RADAR_1_MARKETS': MarketsCollector, 'RADAR_2_PROJECTS': ProjectsCollector,
              'RADAR_3_INSTITUTIONS': InstitutionsCollector}
COLLECTORS['RADAR_4_POLICIES'] = PoliciesCollector
COLLECTORS['RADAR_5_FUNDING'] = FundingCollector

SEARCH_LIMIT_SETTINGS = {
    'RADAR_1_MARKETS': 'RADAR1_MAX_QUERIES_PER_RUN',
    'RADAR_2_PROJECTS': 'RADAR2_DISCOVERY_MAX_SEARCHES',
    'RADAR_3_INSTITUTIONS': 'RADAR3_SEARCH_MAX_CALLS',
    'RADAR_4_POLICIES': 'RADAR4_SEARCH_MAX_CALLS',
    'RADAR_5_FUNDING': 'RADAR5_SEARCH_MAX_CALLS',
}


def build_collector(code, config):
    collector_type = COLLECTORS.get(code)
    if collector_type is None or (config['SEARCH_PROVIDER'] == 'disabled' and config.get('TESTING')):
        return None
    try:
        purpose = ('projects' if code == 'RADAR_2_PROJECTS' else 'institutions' if code == 'RADAR_3_INSTITUTIONS'
                   else 'policies' if code == 'RADAR_4_POLICIES' else 'funding' if code == 'RADAR_5_FUNDING' else 'procurement')
        provider = (DisabledSearchProvider() if config['SEARCH_PROVIDER'] == 'disabled'
                    else build_search_provider(config, purpose=purpose))
        collector_config = dict(config)
        if code == 'RADAR_1_MARKETS':
            collector_config['RADAR1_DISCOVERY_MAX_CALLS'] = min(
                collector_config['RADAR1_DISCOVERY_MAX_CALLS'], collector_config['RADAR1_NORMAL_SEARCH_BUDGET'])
            collector_config['RADAR1_RESOLUTION_MAX_CALLS'] = min(
                collector_config['RADAR1_RESOLUTION_MAX_CALLS'], collector_config['RADAR1_NORMAL_RESOLUTION_BUDGET'])
            collector_config['RADAR1_MIN_SEARCH_QUERIES'] = 0
        collector = collector_type(provider, collector_config)
        if code in DEFAULT_SOURCES:
            records = config.get(code.replace('RADAR_', 'RADAR').replace('_PROJECTS', '_SOURCES')
                                 .replace('_INSTITUTIONS', '_SOURCES').replace('_POLICIES', '_SOURCES')
                                 .replace('_FUNDING', '_SOURCES'), DEFAULT_SOURCES[code])
            collector.source_adapters = build_source_adapters(records, collector.domains,
                timeout=config.get('SOURCE_HTTP_TIMEOUT_SECONDS', 20), state=SourceStateService(code))
            if code in {'RADAR_3_INSTITUTIONS', 'RADAR_4_POLICIES'}:
                from app.modules.radar3_institutions.institution_policy_source import InstitutionSourceAdapter, PolicySourceAdapter
                adapter_type = InstitutionSourceAdapter if code == 'RADAR_3_INSTITUTIONS' else PolicySourceAdapter
                collector.source_adapters = [adapter_type(a.definition, a.domains, timeout=a.timeout, state=a.state)
                                             for a in collector.source_adapters]
        return collector
    except SearchProviderError as error:
        raise ProviderUnavailable('Search provider initialization failed.') from error
