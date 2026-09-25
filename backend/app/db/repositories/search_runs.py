import logging
from decimal import Decimal
from datetime import timedelta

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.agent_errors import ActiveRunError, AgentError
from app.core.agent_schemas import RunStatus, RunSummary, Stage
from app.db.extensions import db
from app.db.models import Radar, SearchRun, utcnow
from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.core.logging import log_failure

logger = logging.getLogger(__name__)
ACTIVE = (RunStatus.INITIALIZED, RunStatus.RUNNING)


class SearchRunService:
    def _recover_stale(self, radar_id):
        """Release process-safe run locks left behind by a dead worker."""
        from flask import current_app
        cutoff = utcnow() - timedelta(minutes=current_app.config['SEARCH_RUN_STALE_MINUTES'])
        rows = db.session.scalars(db.select(SearchRun).where(
            SearchRun.radar_id == radar_id, SearchRun.status.in_(ACTIVE),
            SearchRun.started_at < cutoff).with_for_update()).all()
        for row in rows:
            row.status = RunStatus.FAILED
            row.current_stage = Stage.FAILED
            row.error_kind = 'stale_run_recovered'
            row.error_message = 'Interrupted run recovered automatically before a new launch.'
            row.finished_at = utcnow()
            row.stage_history = [*(row.stage_history or []), {
                'stage': Stage.FAILED, 'at': row.finished_at.isoformat(), 'reason': 'stale_run_recovered'}]
        if rows:
            db.session.commit()
            logger.warning('Recovered %s stale active run(s) for radar_id=%s', len(rows), radar_id)

    def _enforce_daily_caps(self):
        from flask import current_app
        today = utcnow().date()
        totals = db.session.execute(db.select(
            db.func.coalesce(db.func.sum(SearchRun.search_calls), 0),
            db.func.coalesce(db.func.sum(SearchRun.ai_calls), 0),
        ).where(db.func.date(SearchRun.started_at) == today)).one()
        search_cap = current_app.config['MAX_DAILY_SEARCH_CALLS']
        ai_cap = current_app.config['MAX_DAILY_AI_CALLS']
        if (search_cap and totals[0] >= search_cap) or (ai_cap and totals[1] >= ai_cap):
            raise AgentError('Limite d\u2019utilisation quotidienne atteinte. R\u00e9essayez demain.')

    def reserve(self, radar_code, triggered_by=None, trigger_type='manual', launched_by_user_id=None):
        agent = RADAR_AGENT_REGISTRY.resolve(radar_code)
        radar = db.session.scalar(db.select(Radar).where(Radar.code == radar_code))
        if radar is None or not radar.is_active:
            raise AgentError('Radar non configuré ou désactivé.')
        radar_id = radar.id
        self._recover_stale(radar_id)
        self._enforce_daily_caps()
        if db.session.scalar(db.select(SearchRun.id).where(SearchRun.radar_id == radar_id, SearchRun.status.in_(ACTIVE))):
            db.session.rollback()
            raise ActiveRunError('Une recherche est déjà en cours pour ce radar.')
        run = SearchRun(radar_id=radar_id, agent_name=type(agent).__name__, status=RunStatus.INITIALIZED, current_stage=Stage.INITIALIZING,
                        trigger_type=trigger_type, triggered_by=triggered_by, launched_by_user_id=launched_by_user_id, estimated_ai_cost=Decimal(0),
                        stage_history=[{'stage': Stage.INITIALIZING, 'at': utcnow().isoformat()}])
        db.session.add(run)
        try:
            db.session.flush()
            run_id = run.id
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # The unique partial index closes the race between independent processes.
            active = db.session.scalar(db.select(SearchRun.id).where(
                SearchRun.radar_id == radar_id, SearchRun.status.in_(ACTIVE)))
            db.session.rollback()
            if active:
                raise ActiveRunError('Une recherche est déjà en cours pour ce radar.') from None
            raise
        logger.info('run_id=%s radar=%s agent=%s stage=INITIALIZING', run_id, radar_code, type(agent).__name__)
        return run_id

    def claim(self, run_id):
        changed = db.session.execute(db.update(SearchRun).where(
            SearchRun.id == run_id, SearchRun.status == RunStatus.INITIALIZED).values(status=RunStatus.RUNNING))
        if changed.rowcount != 1:
            db.session.rollback()
            raise ActiveRunError('Run already claimed or finished.')
        db.session.commit()
        return db.session.get(SearchRun, run_id)

    def stage(self, run, stage):
        run.current_stage = stage
        run.stage_history = [*run.stage_history, {'stage': stage, 'at': utcnow().isoformat()}]
        db.session.commit()
        logger.info('run_id=%s radar_id=%s agent=%s stage=%s candidates=%s duplicates=%s ai_calls=%s',
                    run.id, run.radar_id, run.agent_name, stage, run.candidates_count, run.duplicate_count, run.ai_calls)

    def complete(self, run):
        run.status = RunStatus.COMPLETED
        run.finished_at = utcnow()
        self.stage(run, Stage.COMPLETED)

    def fail(self, run_id, kind):
        db.session.rollback()
        run = db.session.get(SearchRun, run_id)
        if run is None or run.status not in ACTIVE:
            return
        run.status, run.error_kind = RunStatus.FAILED, kind
        run.error_message = f'Execution failed ({kind}). Consult operational logs with run_id={run_id}.'
        run.finished_at = utcnow()
        self.stage(run, Stage.FAILED)

    def summary(self, run_id, radar_code):
        run = db.session.get(SearchRun, run_id)
        values = {field: getattr(run, field) for field in RunSummary.model_fields if field != 'radar_code'}
        return RunSummary(radar_code=radar_code, **values)

    def safe_fail(self, run_id, kind):
        try:
            self.fail(run_id, kind)
        except SQLAlchemyError as error:
            db.session.rollback()
            log_failure(logger, f'run_id={run_id} failure persistence', error)
