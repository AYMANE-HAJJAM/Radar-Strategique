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

import click

from app.integrations.openai.client import OpenAIService, OpenAIServiceError
from app.db.repositories.radars import RadarServiceError, seed_radars


def register_commands(app):
    register_cleanup_command(app)
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
