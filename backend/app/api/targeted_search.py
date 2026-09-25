from flask import current_app, jsonify, request

from app.api.auth import current_user_id, require_auth
from app.api.common import error
from app.db.extensions import db
from app.db.models import TargetedSearchSession
from app.modules.targeted_search.service import ActiveTargetedRunError, StaleBriefError, TargetedSearchService

service = TargetedSearchService()


def register(bp):
    @bp.get('/targeted-search/sessions')
    @require_auth
    def sessions():
        limit = min(100, max(1, request.args.get('limit', 20, type=int)))
        return jsonify(items=service.history(current_app._get_current_object(), limit))

    @bp.post('/targeted-search/sessions')
    @require_auth
    def create_session():
        prompt = str((request.get_json(silent=True) or {}).get('prompt', '')).strip()
        if not prompt or len(prompt) > 4000:
            return error('INVALID_PROMPT', 'Décrivez la recherche en 1 à 4000 caractères.', 400)
        try:
            session_id, brief = service.create(current_app._get_current_object(), prompt, current_user_id())
        except ValueError as exc:
            return error('INVALID_BRIEF', str(exc), 400)
        return jsonify(id=session_id, version=1, status='DRAFT', brief=brief), 201

    @bp.get('/targeted-search/sessions/<int:session_id>')
    @require_auth
    def session_detail(session_id):
        payload = service.get(current_app._get_current_object(), session_id)
        if not payload:
            return error('SESSION_NOT_FOUND', 'Recherche ciblée introuvable.', 404)
        mode = request.args.get('status', 'PENDING').upper()
        try:
            results, _, pages, page = service.result_page(current_app._get_current_object(), session_id,
                max(0, request.args.get('page', 1, type=int) - 1), mode)
        except ValueError as exc:
            return error('INVALID_STATUS', str(exc), 400)
        payload['results'] = {'items': results, 'page': page + 1, 'page_size': 5,
                              'pages': pages, 'total': None}
        return jsonify(payload)

    @bp.post('/targeted-search/sessions/<int:session_id>/refine')
    @require_auth
    def refine(session_id):
        text = str((request.get_json(silent=True) or {}).get('text', '')).strip()
        if not text or len(text) > 4000:
            return error('INVALID_REFINEMENT', 'La modification est requise.', 400)
        try:
            version, brief = service.refine(current_app._get_current_object(), session_id, text, current_user_id())
        except ValueError as exc:
            return error('SESSION_CONFLICT', str(exc), 409)
        return jsonify(id=session_id, version=version, status='DRAFT', brief=brief)

    @bp.post('/targeted-search/sessions/<int:session_id>/run')
    @require_auth
    def run(session_id):
        payload = request.get_json(silent=True) or {}
        try:
            version = int(payload.get('version'))
        except (TypeError, ValueError):
            return error('VERSION_REQUIRED', 'La version du brief est requise.', 400)
        try:
            service.reserve(current_app._get_current_object(), session_id, version)
            current_app.extensions['radar_job_runner'].submit(
                service.execute, current_app._get_current_object(), session_id, version)
        except ActiveTargetedRunError as exc:
            return error('RUN_ALREADY_ACTIVE', str(exc), 409)
        except StaleBriefError as exc:
            return error('STALE_BRIEF', str(exc), 409)
        except RuntimeError:
            row = db.session.get(TargetedSearchSession, session_id)
            if row:
                row.status = 'FAILED'
                db.session.commit()
            return error('JOB_QUEUE_FULL', 'Le serveur est occupé. Réessayez dans un instant.', 503)
        return jsonify(id=session_id, version=version, status='RUNNING'), 202

    @bp.post('/targeted-search/sessions/<int:session_id>/results/<int:result_id>/<decision>')
    @require_auth
    def targeted_review(session_id, result_id, decision):
        mapped = {'approve': 'PERTINENT', 'reject': 'REJECTED'}.get(decision)
        if not mapped:
            return error('INVALID_DECISION', 'Décision invalide.', 400)
        try:
            service.feedback(current_app._get_current_object(), session_id, result_id, mapped, current_user_id())
        except ValueError as exc:
            return error('RESULT_CONFLICT', str(exc), 409)
        return jsonify(review_status=mapped)
