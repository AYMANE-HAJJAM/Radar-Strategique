from unittest.mock import Mock,patch
import pytest
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.agent_schemas import TokenUsage
from backend.app.core.collector_registry import COLLECTORS
from backend.app.integrations.openai.base import SearchResponse,SearchProviderError
from backend.app.integrations.http.html import PublicPages

@pytest.mark.parametrize('code',list(COLLECTORS)[1:])
def test_failed_paid_search_usage_is_persisted(app,code):
    app.config['SEARCH_PROVIDER']='openai'
    for number in range(2,6):app.config[f'RADAR{number}_DIRECT_FEEDS']=()
    provider=Mock()
    provider.search.side_effect=SearchProviderError('incomplete',SearchResponse([],TokenUsage(input_tokens=11,output_tokens=7),'audit-model',1))
    collector=COLLECTORS[code](provider,app.config)
    with patch('app.core.orchestrator.build_collector',return_value=collector):
        summary=AgentOrchestrator(app,dry_run=True).run_radar(code)
    assert summary.search_calls==provider.search.call_count==3
    assert summary.ai_calls==0
    assert summary.input_tokens==33 and summary.output_tokens==21
    assert summary.run_metadata['search_api_calls']==3
    assert summary.run_metadata['web_search_calls']==3
    assert summary.run_metadata['search_models']==['audit-model']


def test_failed_direct_request_counted_but_cache_hit_not_counted():
    pages=PublicPages(('example.com',))
    with patch('app.integrations.http.html.build_opener') as opener:
        opener.return_value.open.side_effect=OSError('offline')
        with pytest.raises(OSError):pages.get('https://example.com/x')
    assert pages.request_attempts==1
    pages.cache['https://example.com/x']=('https://example.com/x',object())
    pages.get('https://example.com/x')
    assert pages.request_attempts==1


def test_project_resolution_failures_consume_budget(app):
    from backend.app.modules.radar2_projects.collector import ProjectsCollector
    from backend.app.modules.radar2_projects.service import ProjectsRadarAgent
    provider=Mock();provider.search.side_effect=SearchProviderError('timeout')
    app.config['RADAR2_RESOLUTION_MAX_SEARCHES']=1
    collector=ProjectsCollector(provider,app.config)
    item=ProjectsRadarAgent().normalize_candidate({'title':'Future project','officially_announced':True})
    collector._resolve(item);collector._resolve(item)
    assert provider.search.call_count==1
    assert collector.report.metrics['resolution_search_calls']==1
    assert collector.report.usage_events==[None]
