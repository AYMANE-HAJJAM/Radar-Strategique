"""One-shot staging SearchRun for Radar 1 with RADAR1_DISCOVERY_MODE=pmmp_index.

Does not modify .env or Render. Overrides mode only in-process. Writes real
SearchRun / Result rows to the configured local PostgreSQL database.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.core.orchestrator import AgentOrchestrator
from app.core.collector_registry import build_collector
from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.db.extensions import db
from app.db.models import Radar, Result, ResultObservation, SearchRun, User
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.api.results import _actionable_states
from app.modules.radar1_markets.pmmp_listing_collector import PmmpHttp
from app.modules.radar1_markets.shadow_compare import PaidSearchForbidden, _CountingHttp, _GuardedProvider


CODE = 'RADAR_1_MARKETS'
OUT = Path(__file__).resolve().parents[1] / 'docs' / '_staging_run_raw.json'


def main():
    # In-process override only — does not write .env or Render.
    app = create_app({
        'RADAR1_DISCOVERY_MODE': 'pmmp_index',
        'RADAR1_DISCOVERY_MAX_CALLS': 0,
        'RADAR1_RESOLUTION_MAX_CALLS': 0,
        'RADAR1_NORMAL_SEARCH_BUDGET': 0,
        'RADAR1_NORMAL_RESOLUTION_BUDGET': 0,
        'RADAR1_MIN_SEARCH_QUERIES': 0,
    })
    assert app.config['RADAR1_DISCOVERY_MODE'] == 'pmmp_index'

    # Confirm default load without override remains legacy (separate app).
    default_mode = create_app().config['RADAR1_DISCOVERY_MODE']

    paid_attempts = []
    counting = _CountingHttp(PmmpHttp(delay_seconds=0.35))

    with app.app_context():
        before_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        before_index = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        before_obs = db.session.scalar(db.select(db.func.count()).select_from(ResultObservation)) or 0
        launcher = db.session.get(User, 1)
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        pending_before = db.session.scalar(db.select(db.func.count()).select_from(Result).where(
            Result.radar_id == radar.id, Result.review_status == 'PENDING')) or 0

        def blocked(*args, **kwargs):
            paid_attempts.append({'args': [str(a)[:120] for a in args], 'kwargs': {k: str(v)[:80] for k, v in kwargs.items()}})
            raise PaidSearchForbidden('Staging run forbids paid search during discovery/resolution.')

        # Build collector once; orchestrator path uses build_collector internally —
        # so patch build_collector for this process.
        real_build = build_collector

        def staging_build(code, config):
            collector = real_build(code, config)
            if collector is None:
                return None
            if code == CODE:
                collector.provider = _GuardedProvider(collector.provider, blocked)
                collector.listing_http = counting
                collector.config['RADAR1_DISCOVERY_MODE'] = 'pmmp_index'
                collector.config['RADAR1_DISCOVERY_MAX_CALLS'] = 0
                collector.config['RADAR1_RESOLUTION_MAX_CALLS'] = 0
            return collector

        import app.core.orchestrator as orch_mod
        import app.core.collector_registry as reg_mod
        orch_mod.build_collector = staging_build
        reg_mod.build_collector = staging_build

        agent = AgentOrchestrator(app, no_ai=True)
        started = time.perf_counter()
        run_id = agent.reserve(
            CODE, triggered_by=launcher.id if launcher else None,
            trigger_type='staging_pmmp_index',
            launched_by_user_id=launcher.id if launcher else None)
        summary = agent.execute(run_id)
        elapsed = time.perf_counter() - started

        run = db.session.get(SearchRun, run_id)
        db.session.refresh(run)
        metrics = dict((run.run_metadata or {}).get('collector_metrics') or {})
        trace = list((run.run_metadata or {}).get('collector_trace') or [])

        after_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        after_index = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        after_obs = db.session.scalar(db.select(db.func.count()).select_from(ResultObservation)) or 0
        obs_for_run = db.session.scalars(db.select(ResultObservation).where(
            ResultObservation.run_id == run_id).order_by(ResultObservation.id)).all()
        obs_states = {}
        for row in obs_for_run:
            obs_states[row.state] = obs_states.get(row.state, 0) + 1

        result_ids = [row.result_id for row in obs_for_run]
        actionable = _actionable_states(run_id, result_ids) if result_ids else {}
        # Run-scoped pending count (Cette recherche)
        pending_run = []
        if result_ids:
            pending_run = db.session.scalars(db.select(Result).where(
                Result.id.in_(list(actionable)), Result.review_status == 'PENDING')).all()
        pending_all = db.session.scalar(db.select(db.func.count()).select_from(Result).where(
            Result.radar_id == radar.id, Result.review_status == 'PENDING')) or 0

        # Fingerprint uniqueness among results touched this run
        fingerprints = [r.fingerprint for r in db.session.scalars(db.select(Result).where(
            Result.id.in_(result_ids))).all()] if result_ids else []
        duplicate_fps = len(fingerprints) - len(set(fingerprints))

        # Index rows must not equal Result rows by consultation identity
        index_as_results = 0
        if result_ids:
            urls = [r.url for r in db.session.scalars(db.select(Result).where(Result.id.in_(result_ids))).all()]
            for url in urls:
                if url and 'pmmp_listing_index' in (url or ''):
                    index_as_results += 1

        # Policy outcomes from collector trace for actionable path
        policy_rows = []
        for event in trace:
            policy_rows.append({
                'reference': event.get('reference'),
                'title': (event.get('title') or '')[:180],
                'reason': event.get('reason'),
                'decision': (event.get('business_relevance') or {}).get('decision'),
                'classification': (event.get('business_relevance') or {}).get('business_category'),
                'reason_code': (event.get('business_relevance') or {}).get('reason_code'),
                'rejection_reason': (event.get('business_relevance') or {}).get('rejection_reason'),
                'resolution_state': event.get('resolution_state'),
            })

        kept = [p for p in policy_rows if p['reason'] in {'verified_offer', 'credible_fallback'}]
        rejected = [p for p in policy_rows if p['reason'] not in {'verified_offer', 'credible_fallback', 'known_unchanged_or_duplicate'}]

        payload = {
            'search_run': {
                'id': run.id,
                'launched_by_user_id': run.launched_by_user_id,
                'launched_by_name': launcher.display_name if launcher else None,
                'trigger_type': run.trigger_type,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'finished_at': run.finished_at.isoformat() if run.finished_at else None,
                'status': run.status,
                'current_stage': run.current_stage,
                'candidates_count': run.candidates_count,
                'new_results_count': run.new_results_count,
                'updated_results_count': run.updated_results_count,
                'duplicate_count': run.duplicate_count,
                'rejected_count': run.rejected_count,
                'search_calls': run.search_calls,
                'resolution_search_calls': run.resolution_search_calls,
                'ai_calls': run.ai_calls,
                'direct_fetches': run.direct_fetches,
                'elapsed_seconds_wall': round(elapsed, 1),
                'error_message': run.error_message,
                'error_kind': run.error_kind,
            },
            'incremental_sync': {
                'discovery_mode': metrics.get('discovery_mode'),
                'pages_visited': metrics.get('pmmp_sync_pages'),
                'http_requests': counting.requests,
                'http_get': counting.gets,
                'http_post': counting.posts,
                'stop_reason': metrics.get('pmmp_sync_stop_reason'),
                'new': metrics.get('pmmp_sync_new'),
                'updated': metrics.get('pmmp_sync_updated'),
                'unchanged': metrics.get('pmmp_sync_unchanged'),
                'duplicates': metrics.get('pmmp_sync_duplicate'),
                'actionable': metrics.get('pmmp_actionable'),
                'declared_pages': metrics.get('pmmp_sync_declared_pages'),
                'declared_results': metrics.get('pmmp_sync_declared_results'),
                'index_size_before': metrics.get('pmmp_index_size_before'),
            },
            'downstream': {
                'kept_or_review': kept,
                'rejected': rejected,
                'trace_count': len(trace),
                'collector_health': (run.run_metadata or {}).get('collector_health'),
                'collector_health_reasons': (run.run_metadata or {}).get('collector_health_reasons'),
            },
            'persistence': {
                'business_new': run.new_results_count,
                'business_updated': run.updated_results_count,
                'business_unchanged_duplicates': run.duplicate_count,
                'result_observations_created': len(obs_for_run),
                'observation_states': obs_states,
                'results_before': before_results,
                'results_after': after_results,
                'results_delta': after_results - before_results,
                'observations_before': before_obs,
                'observations_after': after_obs,
                'index_before': before_index,
                'index_after': after_index,
                'duplicate_fingerprints_in_run': duplicate_fps,
            },
            'ui': {
                'cette_recherche_actionable_count': len(actionable),
                'cette_recherche_pending_rows': len(pending_run),
                'cette_recherche_matches_rows': len(actionable) == len(pending_run) or (
                    len(actionable) == len(pending_run) == 0),
                'tous_a_traiter_pending_before': pending_before,
                'tous_a_traiter_pending_after': pending_all,
                'index_rows_exposed_as_results': index_as_results,
                'actionable_states': {str(k): v for k, v in actionable.items()},
            },
            'cost': {
                'paid_search_attempts': len(paid_attempts),
                'paid_search_attempts_detail': paid_attempts,
                'run_search_calls': run.search_calls,
                'run_resolution_search_calls': run.resolution_search_calls,
                'run_ai_calls': run.ai_calls,
                'discovery_mode': metrics.get('discovery_mode'),
                'billable_search_in_query_metrics': any(
                    q.get('billable_search') for q in (run.run_metadata or {}).get('collection_queries') or []),
            },
            'safety': {
                'process_override_mode': 'pmmp_index',
                'default_app_mode_without_override': default_mode,
                'render_env_changed': False,
                'env_file_changed': False,
                'legacy_discovery_deleted': False,
                'marche_facile_removed': False,
                'policy_changed': False,
            },
            'summary_status': summary.status if hasattr(summary, 'status') else str(summary),
        }

        # Verdict
        blockers = []
        if run.status != 'completed':
            blockers.append(f"run_status={run.status}")
        if metrics.get('discovery_mode') != 'pmmp_index':
            blockers.append(f"discovery_mode={metrics.get('discovery_mode')}")
        if paid_attempts or run.search_calls or run.ai_calls:
            blockers.append('paid_or_ai_calls_occurred')
        pages = metrics.get('pmmp_sync_pages') or 0
        declared = metrics.get('pmmp_sync_declared_pages') or 0
        if declared and pages > max(12, int(0.1 * declared)):
            blockers.append(f'incremental_too_deep pages={pages}/{declared}')
        if metrics.get('pmmp_sync_stop_reason') not in {'incremental_overlap', 'final_page', 'empty_page'}:
            blockers.append(f"stop_reason={metrics.get('pmmp_sync_stop_reason')}")
        if default_mode != 'legacy':
            blockers.append(f'default_mode_not_legacy={default_mode}')
        if index_as_results:
            blockers.append('index_rows_in_ui')
        if duplicate_fps:
            blockers.append('duplicate_fingerprints')

        payload['verdict'] = {
            'code': 'B' if blockers else 'A',
            'label': ('STAGING FAIL — ' + '; '.join(blockers)) if blockers else
                     'STAGING PASS — safe to enable pmmp_index on Render',
            'blockers': blockers,
        }

        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0 if not blockers else 2


if __name__ == '__main__':
    raise SystemExit(main())
