from flask import current_app, jsonify, request

from app.api.auth import current_user_id, require_auth
from app.api.common import error, paginated, pagination_args
from app.core.review import card, decide, _official_domains, _unique_eligible
from app.db.extensions import db
from app.db.models import Radar, Result, ResultObservation
from app.modules.auth import AccessService


def _find(result_id):
    return db.session.execute(db.select(Result, Radar).join(Radar, Result.radar_id == Radar.id).where(
        Result.id == result_id)).first()


def register(bp):
    @bp.get('/radars/<int:radar_id>/results')
    @require_auth
    def results(radar_id):
        radar = db.session.get(Radar, radar_id)
        if not radar:
            return error('RADAR_NOT_FOUND', 'Radar introuvable.', 404)
        status = request.args.get('status', 'pending').lower()
        if status not in {'pending', 'approved', 'rejected'}:
            return error('INVALID_STATUS', 'Statut de résultat invalide.', 400)
        try:
            page, page_size = pagination_args()
            run_id = int(request.args['run_id']) if request.args.get('run_id') else None
        except ValueError as exc:
            return error('INVALID_PAGINATION', str(exc), 400)
        query = db.select(Result).where(Result.radar_id == radar_id, Result.review_status == status.upper())
        if run_id is not None:
            query = query.join(ResultObservation, ResultObservation.result_id == Result.id).where(
                ResultObservation.run_id == run_id)
        rows = db.session.scalars(query.order_by(Result.last_seen_at.desc(), Result.id.desc())).all()
        rows = list(_unique_eligible(rows, status, radar.code))
        total = len(rows)
        selected = rows[(page-1)*page_size:page*page_size]
        domains = _official_domains(current_app) if radar.code == 'RADAR_1_MARKETS' else ()
        return jsonify(paginated([card(row, domains, radar.code) for row in selected], page, page_size, total))

    @bp.get('/results/<int:result_id>')
    @require_auth
    def result_detail(result_id):
        pair = _find(result_id)
        if not pair:
            return error('RESULT_NOT_FOUND', 'Résultat introuvable.', 404)
        row, radar = pair
        domains = _official_domains(current_app) if radar.code == 'RADAR_1_MARKETS' else ()
        return jsonify(card(row, domains, radar.code))

    def review(result_id, decision):
        pair = _find(result_id)
        if not pair:
            return error('RESULT_NOT_FOUND', 'Résultat introuvable.', 404)
        row, radar = pair
        payload = request.get_json(silent=True) or {}
        version = str(payload.get('version') or '')
        if not version:
            return error('VERSION_REQUIRED', 'La version du résultat est requise.', 400)
        try:
            message = decide(current_app._get_current_object(), result_id, version, decision,
                             current_user_id(), code=radar.code)
        except ValueError as exc:
            return error('STALE_RESULT', str(exc), 409)
        AccessService.audit('RESULT_APPROVED' if decision == 'approved' else 'RESULT_REJECTED',
                            current_user_id(), current_user_id(), {'result_id': result_id})
        db.session.commit()
        return jsonify(message=message, review_status=decision.upper())

    bp.add_url_rule('/results/<int:result_id>/approve', 'approve_result',
                    require_auth(lambda result_id: review(result_id, 'approved')), methods=['POST'])
    bp.add_url_rule('/results/<int:result_id>/reject', 'reject_result',
                    require_auth(lambda result_id: review(result_id, 'rejected')), methods=['POST'])
