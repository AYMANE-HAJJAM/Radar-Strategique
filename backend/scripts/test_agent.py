"""Run a deterministic demo. Real AI is opt-in; --isolated avoids the configured DB."""
import argparse
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import timedelta

from backend.app import create_app
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.agent_schemas import AgentAnalysis, AnalysisResponse, Candidate, TokenUsage
from backend.app.db.extensions import db
from backend.app.core.radar_registry import RADARS
from backend.app.db.repositories.radars import seed_radars
from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar1_markets.schemas import MarketCandidate


class MockAnalyzer:
    def analyze_candidate(self, candidate, radar_context, *, analysis_schema=AgentAnalysis, instructions=None):
        return AnalysisResponse(
            analysis=analysis_schema(relevant=True, priority=3, score=80, category='other',
                                   summary='Candidat de démonstration.', reason='Données fictives de test.',
                                   confidence=0.9, needs_manual_review=False),
            usage=TokenUsage(), model='mock')


def mock_candidates(radar):
    if radar.code == 'RADAR_1_MARKETS':
        candidate = MarketCandidate(
            title='DEMO: restauration du patrimoine au Maroc',
            url='https://example.invalid/demo/markets', source='FICTIONAL DEMO ONLY',
            institution='Institution fictive', reference='DEMO-MARKETS',
            publication_date=today_in_morocco(), deadline=today_in_morocco() + timedelta(days=30),
            source_status='open', procedure_type='consultation', morocco_related=True,
            location_evidence='Rabat, Maroc (fictional)', source_quality='OFFICIAL_PRIMARY',
            official_url='https://example.invalid/demo/markets', official_confirmation=True,
            access_mode='DIRECT_OFFICIAL', raw_text='Fictional heritage restoration consultation.',
            metadata={'demo': True})
        return [candidate, candidate]
    candidate = Candidate(title=f'DÉMO Phase 2 — {radar.name}',
                          url=f'https://example.invalid/demo/{radar.code}', source='DEMO ONLY',
                          reference=f'DEMO-{radar.code}', institution='Institution fictive',
                          raw_text='Exemple fictif de programme pour PME marocaines.', metadata={'demo': True})
    return [candidate, candidate]  # Deliberate duplicate exercises pre-AI filtering.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('radar_code', choices=RADARS)
    parser.add_argument('--real-ai', action='store_true', help='Explicitly send demo data to OpenAI (billable).')
    parser.add_argument('--isolated', action='store_true', help='Use a disposable SQLite database instead of configured PostgreSQL.')
    args = parser.parse_args()
    with TemporaryDirectory(prefix='radar-demo-') as directory:
        config = None
        if args.isolated:
            config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'demo.db').as_posix(),
                      'SQLALCHEMY_ENGINE_OPTIONS': {}}
        app = create_app(config)
        with app.app_context():
            if args.isolated:
                db.create_all()
            seed_radars()
        agent = AgentOrchestrator(app, collector=mock_candidates, analyzer=None if args.real_ai else MockAnalyzer())
        summary = agent.run_radar(args.radar_code, trigger_type='demo')
        print(summary.model_dump_json(indent=2))
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        return 0 if summary.status == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
