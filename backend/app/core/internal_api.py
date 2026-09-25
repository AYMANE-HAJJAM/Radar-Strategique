import hmac
import logging
from functools import wraps

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.extensions import db
from app.db.models import Radar, SearchRun
from app.core.logging import log_failure

api = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


def database_available():
    try:
        db.session.execute(text('SELECT 1'))
        return True
    except SQLAlchemyError as error:
        db.session.rollback()
        log_failure(logger, 'Database health', error)
        return False


@api.get('/health')
def health():
    available = database_available()
    return jsonify(status='ok' if available else 'degraded', application='ok', phase=2,
                   database='ok' if available else 'unavailable',
                   openai_configured=bool(current_app.config['OPENAI_API_KEY']),
                   telegram_configured=bool(current_app.config['TELEGRAM_BOT_TOKEN'])), 200 if available else 503


@api.get('/ready')
def ready():
    available = database_available()
    return jsonify(status='ready' if available else 'unavailable'), 200 if available else 503


def internal_only(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        expected = current_app.config['INTERNAL_API_TOKEN']
        supplied = request.headers.get('Authorization', '')
        if not expected or not hmac.compare_digest(supplied.encode(), ('Bearer ' + expected).encode()):
            return jsonify(error='Unauthorized'), 401
        return handler(*args, **kwargs)
    return wrapped


@api.errorhandler(SQLAlchemyError)
def database_error(error):
    db.session.rollback()
    log_failure(logger, 'Internal API database operation', error)
    return jsonify(error='Database temporarily unavailable'), 503


def run_json(run):
    fields = ('id', 'radar_id', 'agent_name', 'status', 'current_stage', 'trigger_type', 'triggered_by',
              'candidates_count', 'duplicate_count', 'analyzed_count', 'new_results_count',
              'updated_results_count', 'rejected_count', 'candidate_errors_count',
              'input_tokens', 'output_tokens', 'cached_tokens', 'ai_calls', 'error_kind', 'error_message')
    fields += ('direct_fetches', 'search_calls', 'resolution_search_calls', 'queries_executed',
               'candidates_after_rules', 'manual_review_count', 'accepted_count', 'run_metadata')
    result = {field: getattr(run, field) for field in fields}
    for field in ('started_at', 'finished_at'):
        value = getattr(run, field)
        result[field] = value.isoformat() if value else None
    result['estimated_ai_cost'] = str(run.estimated_ai_cost) if run.estimated_ai_cost is not None else None
    result['stage_history'] = run.stage_history
    launcher = run.launcher
    result['launched_by'] = None if launcher is None else {'id': launcher.id, 'name': launcher.display_name}
    return result


@api.get('/radars')
@internal_only
def radars():
    rows = db.session.scalars(db.select(Radar).order_by(Radar.id)).all()
    return jsonify(radars=[{key: getattr(row, key) for key in ('id', 'code', 'name', 'description', 'is_active')} for row in rows])


@api.get('/runs')
@internal_only
def runs():
    try:
        limit = max(1, min(100, int(request.args.get('limit', 20))))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        return jsonify(error='limit and offset must be integers'), 400
    rows = db.session.scalars(db.select(SearchRun).order_by(SearchRun.id.desc()).limit(limit).offset(offset)).all()
    return jsonify(runs=[run_json(row) for row in rows], limit=limit, offset=offset)


@api.get('/runs/<int:run_id>')
@internal_only
def run_detail(run_id):
    row = db.session.get(SearchRun, run_id)
    if row is None:
        return jsonify(error='Run not found'), 404
    return jsonify(run_json(row))
