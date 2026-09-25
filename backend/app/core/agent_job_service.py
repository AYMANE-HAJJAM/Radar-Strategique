import logging
from dataclasses import dataclass
from concurrent.futures import Future

from app.core.orchestrator import AgentOrchestrator
from app.core.logging import log_failure

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobTicket:
    run_id: int
    future: Future


def launch_radar(app, runner, code, user_id):
    agent = AgentOrchestrator(app)
    run_id = agent.reserve(code, triggered_by=user_id, trigger_type='web', launched_by_user_id=user_id)
    try:
        future = runner.submit(agent.execute, run_id)
    except Exception as error:
        log_failure(logger, f'job_submission run_id={run_id} radar={code}', error)
        with app.app_context():
            agent.runs.safe_fail(run_id, 'job_submission')
        future = Future()
        from app.core.agent_schemas import RunSummary, RunStatus, Stage
        future.set_result(RunSummary(id=run_id, radar_code=code, status=RunStatus.FAILED,
                                    current_stage=Stage.FAILED, error_kind='job_submission'))
    return JobTicket(run_id, future)
