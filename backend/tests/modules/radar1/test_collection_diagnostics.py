from concurrent.futures import Future
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock, patch

import pytest

from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.agent_schemas import RunSummary, RunStatus, Stage
from backend.app.core.validation import today_in_morocco
from backend.app.bot.handlers.jobs import notify_when_finished
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.integrations.http.html import Page
from backend.app.integrations.pmmp.parser import extract_rows
from backend.app.integrations.pmmp.client import is_direct_notice
from backend.app.modules.radar1_markets.policy import domain_match, normalize_domain, source_role
from backend.app.integrations.openai.base import SearchHit, SearchResponse
from backend.app.integrations.openai.search import OpenAISearchProvider
from backend.app.core.agent_job_service import JobTicket
from test_phase3 import CODE, hit, URL

RADAR = RADAR_AGENT_REGISTRY.resolve(CODE)
LIVE_URL = 'https://www.marchespublics.gov.ma/index.php?orgAcronyme=a1t&page=entreprise.EntrepriseDetailConsultation&refConsultation=1034798'


def official_page(title='Etude architecturale patrimoniale', reference='CA11/2026/APDN', deadline=None):
    return Page('<h1>Consultation</h1><dl>' + ''.join(f'<dt>{key}</dt><dd>{value}</dd>' for key, value in {
        'Référence :': reference, 'Objet :': title, 'Acheteur public :': 'APDN',
        'Date limite de remise des plis :': deadline or (today_in_morocco()+timedelta(days=20)).strftime('%d/%m/%Y'),
        'Date de publication :': today_in_morocco().isoformat(), 'Lieu d’exécution :': 'Al Hoceima',
        'Procédure :': 'Consultation architecturale ouverte',
    }.items()) + '</dl>')


def collector(app, hits, page=None):
    provider, pages = Mock(), Mock()
    provider.search.return_value = SearchResponse(hits)
    pages.get.return_value = (LIVE_URL, page or official_page())
    app.config.update(RADAR1_MAX_QUERIES_PER_RUN=8, RADAR1_MIN_DISCOVERIES=1,
                      RADAR1_MIN_SEARCH_QUERIES=1, RADAR1_TARGET_OBSERVATIONS=1,
                      RADAR1_ZERO_YIELD_QUERY_LIMIT=4)
    return MarketsCollector(provider, app.config, pages=pages)


@pytest.mark.parametrize('domain', ['marchespublics.gov.ma', 'www.marchespublics.gov.ma',
    ' HTTPS://WWW.MARCHESPUBLICS.GOV.MA/path ', 'marchespublics.gov.ma.'])
def test_domain_normalization(domain):
    assert normalize_domain(domain) == 'marchespublics.gov.ma'
    assert domain_match(LIVE_URL, (domain,))
    assert domain_match('https://avis.marchespublics.gov.ma/page', (domain,))
    assert not domain_match('https://marchespublics.gov.ma.evil.test/page', (domain,))


def test_live_route_spelling_and_real_aggregator_domain(app):
    assert is_direct_notice(LIVE_URL) and is_direct_notice(URL)
    assert source_role('https://www.marchefacile.ma/marches/27053', app.config) == 'PROCUREMENT_AGGREGATOR'
    assert not is_direct_notice('https://marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch')


def test_provider_url_only_sources_survive_empty_structured_hits():
    response = SimpleNamespace(status='completed', usage=None, output_parsed={'hits': []}, output=[
        {'type': 'web_search_call', 'action': {'type': 'search', 'query': 'patrimoine',
            'sources': [{'type': 'url', 'url': LIVE_URL}]}, 'status': 'completed'},
        {'type': 'message', 'content': [{'type': 'output_text', 'text': '{}', 'annotations': [
            {'type': 'url_citation', 'url': LIVE_URL, 'title': 'Consultation', 'start_index': 0, 'end_index': 12}]}]},
    ])
    report = OpenAISearchProvider('offline', 'test').parse_response(response)
    assert report.raw_results_count == 1 and len(report.hits) == 1
    assert report.hits[0].kind == 'discovery_page' and report.hits[0].title == 'Consultation'
    assert report.hits[0].publication_date is None and report.hits[0].evidence == ''
    assert report.diagnostics['source_pages_preserved'] == 1
    assert report.diagnostics['source_samples'][0]['domain'] == 'www.marchespublics.gov.ma'


def test_captured_live_source_projection_is_not_lost():
    import json
    from pathlib import Path
    response = json.loads((Path(__file__).resolve().parents[2] / 'fixtures/live_search_sources.json').read_text())
    report = OpenAISearchProvider('offline', 'test').parse_response(response)
    assert report.raw_results_count == len(response['output'][0]['action']['sources'])
    assert len(report.hits) == report.raw_results_count > 0
    assert all(hit.kind == 'discovery_page' for hit in report.hits)


def test_provider_open_page_url_and_optional_fields():
    source = {'type': 'url', 'url': LIVE_URL, 'title': 'Avis', 'snippet': 'Architecture', 'published_date': '2026-09-10'}
    response = SimpleNamespace(status='completed', usage=None, output_parsed={'hits': []}, output=[
        {'type': 'web_search_call', 'action': {'type': 'search', 'sources': [source]}},
        {'type': 'web_search_call', 'action': {'type': 'open_page', 'url': LIVE_URL}},
    ])
    report = OpenAISearchProvider('offline', 'test').parse_response(response)
    assert len(report.hits) == 1 and report.web_search_calls == 2
    assert report.hits[0].evidence == 'Architecture' and report.hits[0].publication_date == '2026-09-10'


def test_pmmp_incomplete_reference_creates_observation_before_enrichment(app):
    run = collector(app, [SearchHit(url=LIVE_URL, reference='CA11/2026/APDN')])
    items = run.collect(RADAR)
    assert len(items) == 1 and items[0].detail_verified
    assert items[0].institution == 'APDN' and items[0].title == 'Etude architecturale patrimoniale'
    assert run.report.observations[0].institution is None
    assert run.report.observations[0].deadline is None
    assert run.report.metrics['candidates_created'] == 1
    assert run.report.metrics['official_urls_resolved'] == 1
    assert run.report.health == 'HEALTHY'


def test_url_only_pmmp_source_is_opened_and_parsed(app):
    run = collector(app, [SearchHit(url=LIVE_URL, kind='discovery_page')])
    assert len(run.collect(RADAR)) == 1
    assert run.report.metrics['candidates_created'] == 1


def test_pmmp_list_extracts_detail_link_even_with_short_label(app):
    listing_url = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'
    run = collector(app, [SearchHit(title='Résultats de recherche', url=listing_url, kind='discovery_page')])
    run.pages.reader.get.side_effect = lambda url: (url, Page(f'<a href="{LIVE_URL.replace("&", "&amp;")}">Détails</a>')
                                             if url == listing_url else official_page())
    # A short detail-link label is still an observation, enriched from the official page.
    assert len(run.collect(RADAR)) == 1
    assert run.report.metrics['aggregate_pages_detected'] == 1


def test_realistic_aggregator_table_extracts_fields():
    table = Page('<table><tr><th>Objet</th><th>Acheteur</th><th>Échéance</th><th>Estimation</th></tr>'
        '<tr><td>[CA11/2026/APDN] Etude architecturale patrimoniale</td><td>APDN</td><td>23/09/2026 J-13</td><td>5 M MAD</td></tr>'
        '<tr><td>[12/2026/APDN] Gardiennage</td><td>APDN</td><td>23/09/2026</td><td>1 M MAD</td></tr></table>')
    rows = extract_rows(table, 'https://borjmarchepublic.ma/marches-publics/services/al-hoceima/')
    assert len(rows) == 2
    assert rows[0].title == 'Etude architecturale patrimoniale' and rows[0].reference == 'CA11/2026/APDN'
    assert rows[0].institution == 'APDN' and rows[0].deadline == '23/09/2026'


def test_live_pmmp_combined_cells_icon_link_and_js_actions():
    listing = 'https://www.marchespublics.gov.ma/index.php5?page=entreprise.EntrepriseAdvancedSearch'
    html = '''<table><tr><th></th><th>Procédure Catégorie Publié le</th>
        <th>Référence | Contexte/Programmme Objet Acheteur public</th><th>Lots</th><th>Date limite de remise des plis</th></tr>
        <tr><td></td><td>AOO Services 08/09/2026</td><td>26E011 - ...
        <span>Objet :</span><span>Etude architecturale patrimoniale</span><span>Acheteur public :</span><span>APDN</span></td>
        <td>AL HOCEIMA</td><td>23/09/2026 11:00</td><td>
        <a href="javascript:popUp('refConsultation=1034798')">Lots</a>
        <a href="?page=entreprise.EntrepriseDetailConsultation&amp;refConsultation=1034798&amp;orgAcronyme=a1t"><img alt="Détail"></a>
        </td></tr></table>'''
    rows = extract_rows(Page(html), listing)
    assert len(rows) == 1
    assert rows[0].reference == '26E011' and rows[0].title == 'Etude architecturale patrimoniale'
    assert rows[0].institution == 'APDN' and rows[0].publication_date == '08/09/2026'
    assert rows[0].deadline == '23/09/2026' and is_direct_notice(rows[0].url)
    assert not rows[0].url.startswith('javascript:')


def test_bad_optional_timestamp_does_not_discard_identity(app):
    run = collector(app, [SearchHit(url=LIVE_URL, reference='CA11/2026/APDN', deadline_at='2026-09-23T11:00:00')])
    assert len(run.collect(RADAR)) == 1
    assert run.report.observations[0].deadline_at is None


def test_discovery_kind_with_identity_survives_blocked_page_and_uses_hosted_link(app):
    from urllib.error import HTTPError
    url = 'https://cpmaroc.com/appels-offres/109919'
    run = collector(app, [SearchHit(url=url, kind='discovery_page', title='Etude architecturale patrimoniale',
                                    reference='CA11/2026/APDN', institution='APDN')])
    run.provider.search.side_effect = [run.provider.search.return_value,
                                      SearchResponse([SearchHit(url=LIVE_URL, kind='discovery_page')])]
    def read(target):
        if target == url:
            raise HTTPError(target, 403, 'Forbidden', {}, None)
        return target, official_page()
    run.pages.reader.get.side_effect = read
    assert len(run.collect(RADAR)) == 1
    assert run.provider.search.call_count == 2
    assert 'site:marchespublics.gov.ma' in run.provider.search.call_args.args[0]
    assert run.report.metrics['http_403'] == 0  # Official-first lookup never opens the blocked secondary page.


def test_observed_official_notice_id_resolves_verified_detail_without_document_get(app):
    from urllib.error import HTTPError
    from backend.app.integrations.pmmp.client import detail_from_official_identity
    url = 'https://cpmaroc.com/appels-offres/109919'
    document = LIVE_URL.replace('EntrepriseDetailConsultation', 'EntrepriseDownloadAvisJAL')
    run = collector(app, [SearchHit(url=url, title='Etude architecturale patrimoniale', reference='CA11/2026/APDN', institution='APDN')])
    run.provider.search.side_effect = [run.provider.search.return_value, SearchResponse([SearchHit(url=document)])]
    def read(target):
        assert target != document
        if target == url:
            raise HTTPError(target, 403, 'Forbidden', {}, None)
        assert target == detail_from_official_identity(document)
        return target, official_page()
    run.pages.reader.get.side_effect = read
    items = run.collect(RADAR)
    assert len(items) == 1 and items[0].detail_verified
    assert items[0].metadata['observed_official_url'] == document


def test_cli_writes_unicode_report_even_with_ascii_console(app, tmp_path, monkeypatch):
    import io
    import json
    from backend.scripts import run_live_radar
    class AsciiConsole(io.StringIO):
        def write(self, value):
            value.encode('ascii')
            return super().write(value)
    report = tmp_path / 'report.json'
    summary = RunSummary(id=1, radar_code=CODE, status=RunStatus.COMPLETED, current_stage=Stage.COMPLETED,
                         run_metadata={'collector_health': 'HEALTHY', 'example_title': 'Étude\u202fpatrimoniale'})
    app.config['SEARCH_PROVIDER'] = 'openai'
    monkeypatch.setattr('sys.argv', ['run_live_radar', CODE, '--dry-run', '--report-json', str(report)])
    with patch.object(run_live_radar, 'create_app', return_value=app), patch.object(run_live_radar, 'AgentOrchestrator') as engine, patch('sys.stdout', AsciiConsole()):
        engine.return_value.run_radar.return_value = summary
        assert run_live_radar.main() == 0
    assert json.loads(report.read_text(encoding='utf-8'))['run_metadata']['example_title'] == 'Étude\u202fpatrimoniale'


def test_aggregator_link_recovers_after_official_search(app):
    url = 'https://cpmaroc.com/appels-offres/109919'
    run = collector(app, [SearchHit(title='Etude architecturale patrimoniale', reference='CA11/2026/APDN', url=url)])
    run.pages.reader.get.side_effect = lambda target: (target, Page(f'<a href="{LIVE_URL.replace("&", "&amp;")}">Soumissionner</a>')
                                                if target == url else official_page())
    assert len(run.collect(RADAR)) == 1
    assert run.provider.search.call_count > 1
    assert run.report.candidates[0].metadata['official_resolved_from'] == url


def test_zero_raw_expands_to_budget_and_warns(app, caplog):
    run = collector(app, [])
    with caplog.at_level('INFO'):
        assert run.collect(RADAR) == []
    assert run.provider.search.call_count == 8
    assert run.report.metrics['cost_warning'] and run.report.health == 'DEGRADED'
    assert 'zero_raw_results' in run.report.health_reasons
    assert 'query=8 strategy=' in caplog.text and 'collection_totals health=DEGRADED' in caplog.text


def test_one_generic_result_page_cannot_exhaust_every_query_family(app):
    noise = [SearchHit(title='Gardiennage', url=LIVE_URL.replace('1034798', str(900000+i)), reference=f'N-{i}') for i in range(30)]
    run = collector(app, noise)
    app.config['RADAR1_QUERY_OBSERVATION_LIMIT'] = 3
    run.provider.search.side_effect = [SearchResponse(noise), SearchResponse([SearchHit(url=LIVE_URL, reference='CA11/2026/APDN')])]
    assert len(run.collect(RADAR)) == 1
    assert run.provider.search.call_count == 2
    assert run.report.query_metrics[0]['candidates_created'] == 3
    assert run.report.query_metrics[0]['rejected_by_relevance'] == 3
    assert run.report.query_metrics[1]['candidates_created'] == 1


def test_zero_relevant_is_healthy_and_not_parser_failure(app):
    run = collector(app, [SearchHit(title='Gardiennage', reference='REF-1', url=LIVE_URL)])
    assert run.collect(RADAR) == []
    assert run.report.health == 'DEGRADED' and run.report.metrics['cost_warning']
    assert run.report.metrics['candidates_created'] == 1
    assert run.report.metrics['query_scope_filtered'] == 0
    run.pages.reader.get.assert_not_called()


def test_unparseable_pages_stop_with_precise_reason(app):
    run = collector(app, [SearchHit(url=LIVE_URL, kind='discovery_page')], Page('JavaScript required'))
    assert run.collect(RADAR) == []
    assert run.provider.search.call_count == 8
    assert run.report.metrics['raw_results'] == 8 and run.report.metrics['usable_results'] == 0
    assert run.report.metrics['rejected_by_parser'] > 0
    assert 'zero_usable_observations' in run.report.health_reasons


def test_final_strictness_missing_buyer_and_expired(app):
    run = collector(app, [SearchHit(url=LIVE_URL, reference='CA11/2026/APDN')],
                    Page('<p>Référence :</p><p>CA11/2026/APDN</p><p>Objet :</p><p>Etude architecturale patrimoniale</p>'))
    assert run.collect(RADAR) == [] and run.report.metrics['candidates_created'] > 0
    assert run.report.metrics['unresolved'] > 0
    expired = official_page(deadline=(today_in_morocco()-timedelta(days=1)).strftime('%d/%m/%Y'))
    run = collector(app, [SearchHit(url=LIVE_URL, reference='CA11/2026/APDN')], expired)
    assert run.collect(RADAR) == [] and run.report.metrics['rejected_by_freshness'] > 0


def test_query_metrics_persist_without_classification(app):
    run = collector(app, [])
    analyzer = Mock()
    with patch('app.core.orchestrator.build_collector', return_value=run):
        summary = AgentOrchestrator(app, dry_run=True, analyzer=analyzer).run_radar(CODE)
    assert summary.run_metadata['collector_health'] == 'DEGRADED'
    assert len(summary.run_metadata['collection_queries']) == 8
    assert summary.run_metadata['collection_queries'][0]['query_text'].startswith('site:marchespublics.gov.ma')
    analyzer.analyze_candidate.assert_not_called()


@pytest.mark.parametrize('health,expected', [('DEGRADED', 'terminé partiellement'),
                                          ('HEALTHY', 'aucun résultat pertinent')])
async def test_health_notice_changes_only_completion_text(health, expected):
    future = Future()
    future.set_result(RunSummary(id=1, radar_code=CODE, status=RunStatus.COMPLETED, current_stage=Stage.COMPLETED,
                                 run_metadata={'collector_health': health}))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(1, future), message, CODE, 1)
    assert expected in message.reply_text.call_args.args[0]
    keyboard = message.reply_text.call_args.kwargs['reply_markup']
    assert [button.text for row in keyboard.inline_keyboard for button in row] == ['⬅️ Retour']
