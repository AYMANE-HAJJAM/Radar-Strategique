"""Offline Al Hoceima regression dry-run; no network, AI, or production DB writes."""
import json
from datetime import timedelta

from backend.app import create_app
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.integrations.http.html import Page
from backend.app.db.extensions import db
from backend.app.integrations.openai.base import SearchHit, SearchResponse
from backend.app.db.repositories.radars import seed_radars

CODE = 'RADAR_1_MARKETS'
LIST = 'https://marchesfaciles.ma/services/al-hoceima'
DETAIL = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=123'


def main():
    today = today_in_morocco()
    offer = SearchHit(title='Etude architecturale et suivi des travaux', url=DETAIL,
        reference='CA11/2026/APDN', institution='APDN', evidence='Avis de consultation au Maroc',
        publication_date=today.isoformat(), deadline=(today + timedelta(days=20)).isoformat(),
        execution_country='MA', location='Al Hoceima, Maroc', status='open',
        procedure_type='architectural_consultation', official_notice=True)

    class Provider:
        def search(self, query, **kwargs):
            if offer.reference in query:
                return SearchResponse([offer])
            if kwargs['domains'] == ('marchesfaciles.ma',):
                return SearchResponse([SearchHit(title="10 appels d'offres de services à Al Hoceima", url=LIST)])
            return SearchResponse([])

    class Pages:
        def get(self, url):
            if url == LIST:
                return url, Page('<table><tr><td>CA11/2026/APDN</td><td>' + offer.title + '</td></tr>'
                                 '<tr><td>12/2026/APDN</td><td>Gardiennage</td></tr></table>')
            assert url == DETAIL
            return url, Page(f'<h1>{offer.title}</h1>{offer.reference} APDN {offer.deadline}'
                             '<form>DCE identification 4 Mo</form>')

    app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
        'SQLALCHEMY_ENGINE_OPTIONS': {}, 'SEARCH_PROVIDER': 'disabled', 'OPENAI_API_KEY': '',
        'RADAR1_MAX_QUERIES_PER_RUN': 12,
        'RADAR1_SOURCE_WHITELIST': ('marchespublics.gov.ma', 'marchesfaciles.ma', 'culture.gov.ma')})
    with app.app_context():
        db.create_all()
        seed_radars()
        collector = MarketsCollector(Provider(), app.config, pages=Pages())
        candidates = collector.collect(RADAR_AGENT_REGISTRY.resolve(CODE))
        summary = AgentOrchestrator(app, collector=lambda _: candidates, dry_run=True).run_radar(CODE)
        print(json.dumps({'mode': 'offline_fixture_dry_run', 'status': summary.status,
                          'queries': collector.report.queries_executed, **collector.report.metrics,
                          'result_writes': 0, 'classification_calls': summary.analyzed_count}, indent=2))
        db.session.remove()
        db.engine.dispose()


if __name__ == '__main__':
    main()
