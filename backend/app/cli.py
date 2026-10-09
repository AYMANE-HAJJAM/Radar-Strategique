"""Safe cleanup of Radars 2–5 development/test business data. Never touches Radar 1."""
from __future__ import annotations

import click

RADAR_CODES = {
    2: 'RADAR_2_PROJECTS',
    3: 'RADAR_3_INSTITUTIONS',
    4: 'RADAR_4_POLICIES',
    5: 'RADAR_5_FUNDING',
}


def _parse_radars(value):
    numbers = []
    for part in str(value).split(','):
        part = part.strip()
        if not part:
            continue
        number = int(part)
        if number not in RADAR_CODES:
            raise click.BadParameter('Only radars 2,3,4,5 are allowed (Radar 1 is preserved).')
        numbers.append(number)
    if not numbers:
        raise click.BadParameter('Provide at least one radar number among 2,3,4,5.')
    return sorted(set(numbers))


def register_cleanup_command(app):
    @app.cli.command('cleanup-test-radar-data')
    @click.option('--radars', default='2,3,4,5', show_default=True,
                  help='Comma-separated radar numbers (2–5 only).')
    @click.option('--dry-run', is_flag=True, help='Show counts only; do not delete.')
    @click.option('--confirm', is_flag=True,
                  help='Required to delete. Backup is written before deletion.')
    @click.option('--backup-dir', default='backups', show_default=True)
    def cleanup_test_radar_data(radars, dry_run, confirm, backup_dir):
        """Delete business rows for selected Radars 2–5 after an explicit backup.

        Preserves: schema, migrations, Radar definitions, configuration, Radar 1 data.
        """
        from datetime import datetime, timezone
        import json
        import os
        from pathlib import Path
        from sqlalchemy import delete, func, select

        from app.db.extensions import db
        from app.db.models import (MarketReview, Radar, Result, ResultAuditEvent,
                                ResultObservation, SearchRun)

        selected = _parse_radars(radars)
        codes = [RADAR_CODES[n] for n in selected]
        if confirm and dry_run:
            raise click.ClickException('Use either --dry-run or --confirm, not both.')
        if not confirm and not dry_run:
            raise click.ClickException('Pass --dry-run to preview, or --confirm to delete after backup.')

        radar_ids = db.session.scalars(select(Radar.id).where(Radar.code.in_(codes))).all()
        if len(radar_ids) != len(codes):
            raise click.ClickException('One or more radar definitions are missing; refuse cleanup.')

        result_ids = db.session.scalars(select(Result.id).where(Result.radar_id.in_(radar_ids))).all()
        run_ids = db.session.scalars(select(SearchRun.id).where(SearchRun.radar_id.in_(radar_ids))).all()
        counts = {
            'radars': codes,
            'search_runs': len(run_ids),
            'results': len(result_ids),
            'result_observations': db.session.scalar(
                select(func.count()).select_from(ResultObservation).where(
                    ResultObservation.result_id.in_(result_ids))) if result_ids else 0,
            'market_reviews': db.session.scalar(
                select(func.count()).select_from(MarketReview).where(
                    MarketReview.result_id.in_(result_ids))) if result_ids else 0,
            'result_audit_events': db.session.scalar(
                select(func.count()).select_from(ResultAuditEvent).where(
                    ResultAuditEvent.result_id.in_(result_ids))) if result_ids else 0,
            'radar_1_results_preserved': db.session.scalar(
                select(func.count()).select_from(Result).join(Radar).where(
                    Radar.code == 'RADAR_1_MARKETS')) or 0,
        }
        click.echo(json.dumps({'mode': 'dry-run' if dry_run else 'confirm', 'counts': counts},
                              ensure_ascii=False, indent=2))
        if dry_run:
            click.echo('Dry-run complete. No rows deleted.')
            return

        directory = Path(backup_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup_path = directory / f'radar2345-cleanup-{stamp}.json'
        payload = {
            'format': 1,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'radars': codes,
            'counts': counts,
            'note': 'Count-level backup before R2–5 cleanup; restore via DB snapshot if needed.',
        }
        backup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        click.echo(f'Backup written: {backup_path}')

        try:
            if result_ids:
                db.session.execute(delete(MarketReview).where(MarketReview.result_id.in_(result_ids)))
                db.session.execute(delete(ResultAuditEvent).where(ResultAuditEvent.result_id.in_(result_ids)))
                db.session.execute(delete(ResultObservation).where(ResultObservation.result_id.in_(result_ids)))
                db.session.execute(delete(Result).where(Result.id.in_(result_ids)))
            if run_ids:
                db.session.execute(delete(SearchRun).where(SearchRun.id.in_(run_ids)))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        click.echo('Cleanup completed for radars: ' + ', '.join(codes))
        click.echo(f"Radar 1 results still present: {counts['radar_1_results_preserved']}")


import json
import time
from pathlib import Path

import click

from app.integrations.openai.client import OpenAIService, OpenAIServiceError
from app.db.repositories.radars import RadarServiceError, seed_radars


def register_radar1_pmmp_commands(app):
    @app.cli.command('radar1-pmmp-baseline')
    @click.option('--max-pages', type=int, default=None,
                  help='Optional page cap for a partial index import; writes index rows (omit for full board).')
    def radar1_pmmp_baseline(max_pages):
        """Full PMMP crawl into pmmp_listing_index only. No Radar business results."""
        from app.db.extensions import db
        from app.db.models import Result
        from app.db.models.pmmp_listing_index import PmmpListingIndex
        from app.modules.radar1_markets.pmmp_listing_collector import (
            DUPLICATE, NEW, UNCHANGED, UPDATED)
        from app.modules.radar1_markets.pmmp_listing_index import sync_listings

        before_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        before_index = db.session.scalar(
            db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        started = time.perf_counter()
        click.echo(f'Baseline import starting (index rows before={before_index}).')
        db.session.commit()  # End count reads before long public HTTP.
        result = sync_listings(mode='full', max_pages=max_pages, commit=False, independent=True)
        elapsed = time.perf_counter() - started
        after_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        after_index = db.session.scalar(
            db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        collected = len(result.observations)
        unique = collected - result.counts.get(DUPLICATE, 0)
        payload = {
            'mode': result.mode,
            'stop_reason': result.stop_reason,
            'pages_fetched': result.pages_fetched,
            'declared_pages': result.declared_pages,
            'declared_results': result.declared_results,
            'listings_collected': collected,
            'unique': unique,
            'new_inserted': result.counts.get(NEW, 0),
            'updated': result.counts.get(UPDATED, 0),
            'unchanged': result.counts.get(UNCHANGED, 0),
            'duplicates': result.counts.get(DUPLICATE, 0),
            'errors': 0,
            'elapsed_seconds': round(elapsed, 1),
            'index_rows_before': before_index,
            'index_rows_after': after_index,
            'business_results_before': before_results,
            'business_results_after': after_results,
        }
        if after_results != before_results:
            raise click.ClickException(
                'Baseline wrote business Result rows; refusing success. '
                f'before={before_results} after={after_results}')
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))

    @app.cli.command('radar1-pmmp-backfill')
    @click.option('--limit', type=int, default=None,
                  help='Optional cap on index rows considered (for smoke tests).')
    @click.option('--user-id', type=int, default=1, show_default=True,
                  help='launched_by_user_id for the dedicated SearchRun.')
    @click.option('--json-out', type=click.Path(), default=None,
                  help='Optional path to write the backfill report JSON.')
    def radar1_pmmp_backfill(limit, user_id, json_out):
        """One-time business backfill from pmmp_listing_index (no recrawl)."""
        from app.core.collector_registry import build_collector
        from app.core.orchestrator import AgentOrchestrator
        from app.core.radar_registry import RADAR_AGENT_REGISTRY
        from app.db.extensions import db
        from app.db.models import Result, ResultObservation, SearchRun, User
        from app.db.models.pmmp_listing_index import PmmpListingIndex
        from app.modules.radar1_markets.pmmp_index_backfill import (
            backfill_from_index, classify_trace_outcomes)
        from app.modules.radar1_markets.shadow_compare import PaidSearchForbidden, _GuardedProvider

        # In-process only — do not change env discovery mode permanently.
        app.config['RADAR1_DISCOVERY_MODE'] = app.config.get('RADAR1_DISCOVERY_MODE', 'legacy')
        app.config['RADAR1_MAX_CANDIDATES'] = max(
            int(app.config.get('RADAR1_MAX_CANDIDATES', 100)), 5000)
        app.config['AGENT_MAX_CANDIDATES'] = max(
            int(app.config.get('AGENT_MAX_CANDIDATES', 200)), 5000)
        app.config['RADAR1_DISCOVERY_MAX_CALLS'] = 0
        app.config['RADAR1_RESOLUTION_MAX_CALLS'] = 0
        app.config['RADAR1_NORMAL_SEARCH_BUDGET'] = 0
        app.config['RADAR1_NORMAL_RESOLUTION_BUDGET'] = 0

        indexed = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        if indexed == 0:
            raise click.ClickException('pmmp_listing_index is empty; run baseline first.')
        launcher = db.session.get(User, user_id)
        if launcher is None:
            raise click.ClickException(f'User id {user_id} not found.')

        before_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        before_obs = db.session.scalar(db.select(db.func.count()).select_from(ResultObservation)) or 0
        before_index = indexed

        paid_attempts = []

        def blocked(*args, **kwargs):
            paid_attempts.append(True)
            raise PaidSearchForbidden('Backfill forbids paid search.')

        collector = build_collector('RADAR_1_MARKETS', app.config)
        if collector is None:
            raise click.ClickException('Radar 1 collector unavailable.')
        collector.provider = _GuardedProvider(collector.provider, blocked)
        radar = RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS')
        holder = {'stats': None, 'collector': collector}

        def collect(_radar):
            candidates, stats = backfill_from_index(collector, radar, limit=limit)
            holder['stats'] = stats
            return candidates

        started = time.perf_counter()
        agent = AgentOrchestrator(app, collector=collect, no_ai=True)
        run_id = agent.reserve(
            'RADAR_1_MARKETS', triggered_by=launcher.id,
            trigger_type='pmmp_index_backfill', launched_by_user_id=launcher.id)
        summary = agent.execute(run_id)
        elapsed = time.perf_counter() - started

        # Fresh session — long HTTP collect can invalidate the previous connection.
        db.session.remove()
        run = db.session.get(SearchRun, run_id)
        if run is None:
            raise click.ClickException(f'SearchRun {run_id} missing after execute.')
        stats = holder['stats']
        trace = collector.report.trace
        outcomes = classify_trace_outcomes(trace)
        metadata = dict(run.run_metadata or {})
        metadata.update({
            'backfill': stats.as_dict() if stats else {},
            'backfill_outcomes': {
                'accepted': len(outcomes['accepted']),
                'review': len(outcomes['review']),
                'rejected_after_detail': len(outcomes['rejected']),
            },
            'discovery_mode': 'pmmp_index_backfill',
            'paid_search_attempts': len(paid_attempts),
            'collector_metrics': collector.report.metrics,
            'collector_health': collector.report.health,
            'collector_health_reasons': collector.report.health_reasons,
            'collection_queries': collector.report.query_metrics,
            # Trace can be large; store compact outcomes + sample only.
            'collector_trace_sample': (collector.report.trace or [])[:50],
            'collector_trace_count': len(collector.report.trace or []),
        })
        run.run_metadata = metadata
        db.session.commit()

        after_results = db.session.scalar(db.select(db.func.count()).select_from(Result)) or 0
        after_obs = db.session.scalar(db.select(db.func.count()).select_from(ResultObservation)) or 0
        after_index = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) or 0
        payload = {
            'search_run': {
                'id': run.id,
                'status': run.status,
                'trigger_type': run.trigger_type,
                'launched_by_user_id': run.launched_by_user_id,
                'launched_by_name': launcher.display_name,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'finished_at': run.finished_at.isoformat() if run.finished_at else None,
                'new_results_count': run.new_results_count,
                'updated_results_count': run.updated_results_count,
                'duplicate_count': run.duplicate_count,
                'rejected_count': run.rejected_count,
                'candidates_count': run.candidates_count,
                'search_calls': run.search_calls,
                'ai_calls': run.ai_calls,
                'error_message': run.error_message,
            },
            'backfill': stats.as_dict() if stats else {},
            'downstream': {
                'accepted': len(outcomes['accepted']),
                'review': len(outcomes['review']),
                'rejected_after_detail': len(outcomes['rejected']),
                'accepted_sample': outcomes['accepted'][:30],
                'review_sample': outcomes['review'][:30],
            },
            'persistence': {
                'business_new': run.new_results_count,
                'business_updated': run.updated_results_count,
                'business_unchanged': run.duplicate_count,
                'results_before': before_results,
                'results_after': after_results,
                'results_delta': after_results - before_results,
                'observations_before': before_obs,
                'observations_after': after_obs,
                'index_before': before_index,
                'index_after': after_index,
                'index_rows_deleted': before_index - after_index if after_index < before_index else 0,
            },
            'cost': {
                'paid_search_attempts': len(paid_attempts),
                'search_calls': run.search_calls,
                'ai_calls': run.ai_calls,
            },
            'elapsed_seconds': round(elapsed, 1),
            'summary_status': getattr(summary, 'status', str(summary)),
            'default_discovery_mode_unchanged': True,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        click.echo(text)
        if json_out:
            Path(json_out).write_text(text, encoding='utf-8')
            click.echo(f'Wrote {json_out}', err=True)
        if after_index < before_index:
            raise click.ClickException('Index row count decreased; refusing success.')
        if run.status != 'completed':
            raise click.ClickException(f'Backfill SearchRun ended as {run.status}.')
    @click.option('--reference', default='04/2026/AUS', show_default=True,
                  help='Known notice reference to check for presence.')
    @click.option('--allow-paid', is_flag=True, default=False,
                  help='Permit paid search/AI. Default forbids all paid provider calls.')
    @click.option('--json-out', type=click.Path(), default=None,
                  help='Optional path to write the full JSON report.')
    def radar1_pmmp_shadow_compare(reference, allow_paid, json_out):
        """Compare legacy vs pmmp_index discovery without writing business results.

        Default forbids paid search. Legacy then uses direct HTTP discovery only.
        Index changes are rolled back.
        """
        from app.core.collector_registry import build_collector
        from app.core.radar_registry import RADAR_AGENT_REGISTRY
        from app.modules.radar1_markets.shadow_compare import PaidSearchForbidden, shadow_compare

        if allow_paid:
            click.echo('WARNING: --allow-paid enables billable search calls.', err=True)
        collector = build_collector('RADAR_1_MARKETS', app.config)
        if collector is None:
            raise click.ClickException('Radar 1 collector unavailable (search provider disabled?).')
        radar = RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS')
        try:
            result = shadow_compare(
                collector, radar, commit_index=False, reference=reference,
                allow_paid=allow_paid)
        except PaidSearchForbidden as error:
            raise click.ClickException(str(error)) from None
        payload = result.as_dict()
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        click.echo(text)
        if json_out:
            Path(json_out).write_text(text, encoding='utf-8')
            click.echo(f'Wrote {json_out}', err=True)


def register_commands(app):
    from app.modules.radar1_markets.preview import register_preview_command
    register_preview_command(app)
    register_cleanup_command(app)
    register_radar1_pmmp_commands(app)
    @app.cli.command('create-admin')
    @click.option('--name', required=True, help='Display name for the initial administrator.')
    def create_admin(name):
        """Create an administrator and print their access code once."""
        from app.db.extensions import db
        from app.db.models import User
        from app.modules.auth import AccessService
        if db.session.scalar(db.select(db.func.count(User.id)).where(
                User.role == 'ADMIN', User.active.is_(True))):
            raise click.ClickException('An active administrator already exists. Use the admin interface.')
        try:
            user, code = AccessService().create(name, 'ADMIN')
        except ValueError as error:
            raise click.ClickException(str(error)) from None
        click.echo(f'Administrateur créé : {user.display_name}')
        click.echo(f'Code d’accès : {code}')
        click.echo('Copiez ce code maintenant : il ne sera plus affiché.')

    @app.cli.command('regenerate-access')
    @click.option('--user-id', required=True, type=int, help='Database ID of the internal user.')
    def regenerate_access(user_id):
        """Recover access by replacing one user's code and revoking their sessions."""
        from app.db.extensions import db
        from app.db.models import User
        from app.modules.auth import AccessService
        user = db.session.get(User, user_id)
        if user is None:
            raise click.ClickException('Utilisateur introuvable.')
        code = AccessService().regenerate(user, actor_id=None)
        click.echo(f'Accès régénéré : {user.display_name} (ID {user.id})')
        click.echo(f'Code d’accès : {code}')
        click.echo('Copiez ce code maintenant : il ne sera plus affiché.')

    @app.cli.command('fail-orphan-run')
    @click.argument('run_id', type=int)
    @click.option('--worker-stopped', is_flag=True, required=True,
                  help='Confirm the process owning this run has stopped; never unlock a live worker.')
    def fail_orphan_run(run_id, worker_stopped):
        """Release a run left active after process death. Stop the owning worker first."""
        from app.db.extensions import db
        from app.db.models import SearchRun
        from app.db.repositories.search_runs import SearchRunService
        if db.session.get(SearchRun, run_id) is None:
            raise click.ClickException('Run not found.')
        SearchRunService().fail(run_id, 'worker_interrupted')
        click.echo(f'Run {run_id}: recovery applied if still active.')

    @app.cli.command('seed-radars')
    def seed():
        """Insert/update the five radar definitions without running research."""
        try:
            seed_radars()
        except RadarServiceError as error:
            raise click.ClickException(str(error)) from None
        click.echo('Five radars configured.')

    @app.cli.command('test-openai')
    @click.option('--text', default='Une institution marocaine annonce un programme de financement pour les PME.')
    def test_openai(text):
        """Make one real, billable connectivity/classification request."""
        try:
            result = OpenAIService(app.config['OPENAI_API_KEY'], app.config['OPENAI_MODEL']).analyze_text(text)
        except (OpenAIServiceError, ValueError) as error:
            raise click.ClickException(str(error)) from None
        click.echo(json.dumps(result, ensure_ascii=False, indent=2))
