from flask import current_app, jsonify

from app.api.auth import current_user, current_user_id, require_auth
from app.api.common import error, paginated, pagination_args, run_json
from app.core.agent_job_service import launch_radar
from app.core.agent_errors import ActiveRunError
from app.db.extensions import db
from app.db.models import Radar, Result, SearchRun
from app.modules.auth import AccessService


def _radar(row):
    counts = dict(db.session.execute(db.select(Result.review_status, db.func.count(Result.id)).where(
        Result.radar_id == row.id).group_by(Result.review_status)).all())
    last = db.session.scalar(db.select(SearchRun).where(SearchRun.radar_id == row.id).order_by(SearchRun.id.desc()).limit(1))
    return {'id': row.id, 'code': row.code, 'name': row.name, 'description': row.description,
            'is_active': row.is_active, 'pending_count': counts.get('PENDING', 0),
            'last_run': run_json(last) if last else None}


def register(bp):
    @bp.get('/radars')
    @require_auth
    def radars():
        rows = db.session.scalars(db.select(Radar).order_by(Radar.id)).all()
        return jsonify(items=[_radar(row) for row in rows])

    @bp.post('/radars/<int:radar_id>/runs')
    @require_auth
    def launch(radar_id):
        radar = db.session.get(Radar, radar_id)
        if not radar or not radar.is_active:
            return error('RADAR_NOT_FOUND', 'Radar introuvable.', 404)
        user = current_user()
        try:
            ticket = launch_radar(current_app._get_current_object(), current_app.extensions['radar_job_runner'],
                                  radar.code, user.id)
        except ActiveRunError:
            return error('RUN_ALREADY_ACTIVE', 'Une recherche est déjà en cours.', 409)
        AccessService.audit('RADAR_LAUNCHED', user.id, user.id, {
            'radar_id': radar.id, 'run_id': ticket.run_id,
            'launched_by_user_id': user.id, 'launched_by_name': user.display_name})
        db.session.commit()
        return jsonify(run_id=ticket.run_id, status='running', launched_by={'id': user.id, 'name': user.display_name}), 201

    @bp.get('/radars/<int:radar_id>/runs')
    @require_auth
    def radar_runs(radar_id):
        if not db.session.get(Radar, radar_id):
            return error('RADAR_NOT_FOUND', 'Radar introuvable.', 404)
        try:
            page, page_size = pagination_args()
        except ValueError as exc:
            return error('INVALID_PAGINATION', str(exc), 400)
        query = db.select(SearchRun).where(SearchRun.radar_id == radar_id)
        total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery())) or 0
        rows = db.session.scalars(query.order_by(SearchRun.id.desc()).offset((page-1)*page_size).limit(page_size)).all()
        return jsonify(paginated([run_json(row) for row in rows], page, page_size, total))
