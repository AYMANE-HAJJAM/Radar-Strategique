"""Run any radar in explicit live mode; isolated dry-run never writes production data."""
import argparse
import logging
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import create_app
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.db.extensions import db
from backend.app.db.repositories.radars import seed_radars


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('radar_code', choices=[
        'RADAR_1_MARKETS', 'RADAR_2_PROJECTS', 'RADAR_3_INSTITUTIONS',
        'RADAR_4_POLICIES', 'RADAR_5_FUNDING'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-ai', action='store_true', help='Diagnostic deterministic-only run; requires --isolated.')
    parser.add_argument('--direct-only', action='store_true', help='Disable paid search and AI; requires --isolated.')
    parser.add_argument('--deep-search', action='store_true', help='CLI-only diagnostic search escalation; requires --isolated --dry-run.')
    parser.add_argument('--isolated', action='store_true', help='Use a temporary local database, without modifying configured PostgreSQL.')
    parser.add_argument('--max-queries', type=int, help='Optional smaller query budget for a smoke test.')
    parser.add_argument('--max-candidates', type=int, help='Optional smaller observation budget for a smoke test.')
    parser.add_argument('--control-reference', help='Development-only exact reference lookup; requires --dry-run.')
    parser.add_argument('--search-mode', choices=['normal_coverage', 'architecture_focused', 'general', 'architecture'],
                        default='normal_coverage', help='Discovery coverage mode; does not alter relevance.')
    parser.add_argument('--report-json', type=Path, help='Write a structured report including per-query diagnostics.')
    args = parser.parse_args()
    if args.control_reference and not args.dry_run:
        parser.error('--control-reference requires --dry-run')
    if args.no_ai and not args.isolated:
        parser.error('--no-ai requires --isolated')
    if args.direct_only and not args.isolated:
        parser.error('--direct-only requires --isolated')
    if args.deep_search and (not args.isolated or not args.dry_run):
        parser.error('--deep-search requires --isolated --dry-run')
    print('API USAGE: live search is billable. ' + ('No classification calls or Result writes.' if args.dry_run else 'Classification may also consume API credit.'))
    logging.disable(logging.CRITICAL)
    with TemporaryDirectory(prefix='radar-live-') as directory:
        config = {'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (Path(directory) / 'live.db').as_posix(),
                  'SQLALCHEMY_ENGINE_OPTIONS': {}} if args.isolated else None
        try:
            app = create_app(config)
            if args.control_reference:
                app.config['RADAR1_CONTROL_REFERENCE'] = args.control_reference
            if args.radar_code == 'RADAR_1_MARKETS':
                app.config['RADAR1_SEARCH_MODE'] = args.search_mode
            if args.deep_search:
                app.config.update(RADAR1_DISCOVERY_MAX_CALLS=10, RADAR1_RESOLUTION_MAX_CALLS=5,
                    RADAR2_NORMAL_SEARCH_BUDGET=app.config['RADAR2_DISCOVERY_MAX_SEARCHES'],
                    RADAR3_NORMAL_SEARCH_BUDGET=app.config['RADAR3_SEARCH_MAX_CALLS'],
                    RADAR4_NORMAL_SEARCH_BUDGET=app.config['RADAR4_SEARCH_MAX_CALLS'],
                    RADAR5_NORMAL_SEARCH_BUDGET=app.config['RADAR5_SEARCH_MAX_CALLS'])
            if args.direct_only:
                app.config.update(RADAR1_NORMAL_SEARCH_BUDGET=0, RADAR1_NORMAL_RESOLUTION_BUDGET=0,
                    RADAR2_NORMAL_SEARCH_BUDGET=0, RADAR3_NORMAL_SEARCH_BUDGET=0,
                    RADAR4_NORMAL_SEARCH_BUDGET=0, RADAR5_NORMAL_SEARCH_BUDGET=0)
            if args.max_queries is not None:
                limit_key = {
                    'RADAR_1_MARKETS': 'RADAR1_MAX_QUERIES_PER_RUN',
                    'RADAR_2_PROJECTS': 'RADAR2_DISCOVERY_MAX_SEARCHES',
                    'RADAR_3_INSTITUTIONS': 'RADAR3_SEARCH_MAX_CALLS',
                    'RADAR_4_POLICIES': 'RADAR4_SEARCH_MAX_CALLS',
                    'RADAR_5_FUNDING': 'RADAR5_SEARCH_MAX_CALLS',
                }[args.radar_code]
                if not 1 <= args.max_queries <= app.config[limit_key]:
                    raise ValueError('Query budget must be positive and not exceed configured limit.')
                app.config[limit_key] = args.max_queries
                if args.radar_code == 'RADAR_1_MARKETS':
                    app.config['RADAR1_DISCOVERY_MAX_CALLS'] = args.max_queries
            if args.max_candidates is not None:
                if not 1 <= args.max_candidates <= app.config['RADAR1_MAX_CANDIDATES']:
                    raise ValueError('Candidate budget must be positive and not exceed configured limit.')
                app.config['RADAR1_MAX_CANDIDATES'] = args.max_candidates
            if app.config['SEARCH_PROVIDER'] == 'disabled':
                raise ValueError('Live mode requires a search provider.')
            with app.app_context():
                if args.isolated:
                    db.create_all()
                seed_radars()
            summary = AgentOrchestrator(app, dry_run=args.dry_run, no_ai=args.no_ai or args.direct_only).run_radar(
                args.radar_code, trigger_type='direct_only' if args.direct_only else 'no_ai' if args.no_ai else 'live_dry_run' if args.dry_run else 'live_cli')
            # Write the report before console output; Windows console encodings
            # must not turn a completed run into a failure or lose diagnostics.
            if args.report_json:
                args.report_json.write_text(summary.model_dump_json(indent=2), encoding='utf-8')
            print(json.dumps(summary.model_dump(mode='json'), ensure_ascii=True, indent=2))
            metrics = summary.run_metadata.get('collector_metrics', summary.run_metadata.get('procurement_metrics', {}))
            for label, key in (('Search calls', 'search_calls'), ('Raw results', 'raw_results'),
                    ('Allowed-source pages', 'allowed_domain_results'), ('Tender observations', 'individual_tenders_extracted'),
                    ('Candidates created', 'candidates_created'), ('Official pages resolved', 'official_urls_resolved'),
                    ('Rejected by freshness', 'rejected_by_freshness'), ('Rejected by relevance', 'rejected_by_relevance')):
                print(f'{label}: {metrics.get(key, 0)}')
            for label, key in (('Relevant observations', 'relevant_candidates'),
                    ('Verified official', 'verified_official'), ('Unverified credible', 'unverified_credible'),
                    ('Unresolved', 'unresolved'), ('HTTP 403', 'http_403'), ('HTTP 429', 'http_429'),
                    ('P1 kept', 'kept_p1'), ('P2 kept', 'kept_p2'), ('P3 kept', 'kept_p3')):
                print(f'{label}: {metrics.get(key, 0)}')
            for label, key in (('Queries with results', 'queries_with_results'),
                    ('Queries with zero results', 'queries_with_zero_results'), ('PMMP raw', 'pmmp_raw'),
                    ('Aggregator raw', 'aggregator_raw'), ('Institutional raw', 'institutional_raw'),
                    ('Deduped before enrichment', 'deduped_before_enrichment'),
                    ('Discovery search calls', 'discovery_search_calls'),
                    ('Resolution search calls', 'resolution_search_calls'),
                    ('Unique identities', 'unique_identities'),
                    ('PMMP observations', 'pmmp_observations'),
                    ('Marche Facile observations', 'marchefacile_observations'),
                    ('Institutional observations', 'institutional_observations'),
                    ('Architecture kept', 'architecture_kept'),
                    ('Topography rejected', 'topography_rejected'),
                    ('Technical-only rejected', 'technical_only_rejected'),
                    ('Heritage kept', 'heritage_kept'),
                    ('Consultation architecturale kept', 'consultation_architecturale_kept'),
                    ('Concours architectural kept', 'concours_architectural_kept'),
                    ('Outside query family', 'query_scope_filtered'),
                    ('Relevant/search call', 'relevant_observations_per_search_call'),
                    ('Final/search call', 'final_kept_per_search_call')):
                print(f'{label}: {metrics.get(key, 0)}')
            print(f'Final kept: {summary.candidates_count}')
            print('Collector health: ' + summary.run_metadata.get('collector_health', 'UNKNOWN'))
            if summary.run_metadata.get('collector_health') == 'DEGRADED':
                return 2
            return 0 if summary.status == 'completed' else 1
        except Exception as error:
            print('Run failed: ' + type(error).__name__ + '. Check configuration and migrations.')
            return 1
        finally:
            if 'app' in locals():
                with app.app_context():
                    db.session.remove()
                    db.engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
