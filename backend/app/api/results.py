from flask import current_app, jsonify, request

from app.api.auth import current_user_id, require_auth
from app.api.common import error, paginated, pagination_args
from app.core.review import card, decide, _official_domains, _unique_eligible
from app.core.review_changes import review_contexts
from app.db.extensions import db
from app.db.models import Radar, Result, ResultObservation, SearchRun, User
from app.modules.auth import AccessService

# Observations that wrote the canonical card. A later unchanged rediscovery
# does not replace the run that produced the row shown in the open queue.
_PRODUCING_OBSERVATION = ('new', 'updated', 'manual_review', 'rejected')


def _launcher_payload(user_id, name):
    if user_id is None or not name:
        return None
    return {'id': user_id, 'name': name}


def _launchers_for(result_ids, run_id):
    """Launcher of the observation in the current list context.

    A run-scoped list is tied to that SearchRun. The open queue uses the latest
    observation that produced the canonical result. Missing tracking stays null.
    """
    if not result_ids:
        return {}
    if run_id is not None:
        row = db.session.execute(db.select(User.id, User.display_name).select_from(SearchRun).outerjoin(
            User, SearchRun.launched_by_user_id == User.id).where(SearchRun.id == run_id)).first()
        payload = _launcher_payload(row[0], row[1]) if row else None
        return {result_id: payload for result_id in result_ids}
    rows = db.session.execute(db.select(
        ResultObservation.result_id, User.id, User.display_name).join(
        SearchRun, ResultObservation.run_id == SearchRun.id).outerjoin(
        User, SearchRun.launched_by_user_id == User.id).where(
        ResultObservation.result_id.in_(result_ids),
        ResultObservation.state.in_(_PRODUCING_OBSERVATION)).order_by(
        ResultObservation.id.desc())).all()
    found = {}
    for result_id, user_id, name in rows:
        if result_id not in found:
            found[result_id] = _launcher_payload(user_id, name)
    return found


# Web run view: an observation belongs to the selected search only when that run
# recorded it as new or updated and the result is still pending. Unchanged
# rediscoveries stay in the global backlog.
_RUN_MEMBERSHIP = ('new', 'updated')


def _actionable_states(run_id, result_ids):
    """Latest NEW/UPDATED observation state for each result in one SearchRun."""
    states = {}
    if not result_ids:
        return states
    rows = db.session.execute(db.select(ResultObservation.result_id, ResultObservation.state).where(
        ResultObservation.run_id == run_id, ResultObservation.result_id.in_(result_ids),
        ResultObservation.state.in_(_RUN_MEMBERSHIP)).order_by(ResultObservation.id.desc())).all()
    for result_id, state in rows:
        if result_id not in states:
            states[result_id] = state
    return states


def _status_rows(radar_id, status, code):
    rows = db.session.scalars(db.select(Result).where(
        Result.radar_id == radar_id, Result.review_status == status.upper()).order_by(
        Result.last_seen_at.desc(), Result.id.desc())).all()
    return list(_unique_eligible(rows, status, code))


def _same_list_page(rows, page, page_size):
    """Total and items are slices of one list, so a zero count cannot carry rows."""
    total = len(rows)
    if total == 0:
        return [], 0
    return rows[(page-1)*page_size:page*page_size], total


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
        domains = _official_domains(current_app) if radar.code == 'RADAR_1_MARKETS' else ()
        rows = _status_rows(radar_id, status, radar.code)
        if status == 'pending' and run_id is not None:
            states = _actionable_states(run_id, [row.id for row in rows])
            chosen = [row for row in rows if row.id in states]
            selected, total = _same_list_page(chosen, page, page_size)
            contexts = review_contexts(selected)
            cards = [card(row, domains, radar.code, review_data=contexts[row.id]) for row in selected]
            launchers = _launchers_for([row.id for row in selected], run_id)
            for item in cards:
                item['launched_by'] = launchers.get(item['id'])
                item['run_observation'] = states.get(item['id'])
            payload = paginated(cards, page, page_size, total)
            payload['pending_total'] = len(rows)
            payload['run_total'] = total
            return jsonify(payload)
        selected, total = _same_list_page(rows, page, page_size)
        contexts = review_contexts(selected)
        cards = [card(row, domains, radar.code, review_data=contexts[row.id]) for row in selected]
        launchers = _launchers_for([row.id for row in selected], None)
        for item in cards:
            item['launched_by'] = launchers.get(item['id'])
        payload = paginated(cards, page, page_size, total)
        if status == 'pending':
            payload['pending_total'] = total
        return jsonify(payload)

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
