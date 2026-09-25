from flask import jsonify

from app.api.auth import require_auth
from app.api.common import error, run_json
from app.db.extensions import db
from app.db.models import SearchRun


def register(bp):
    @bp.get('/runs/<int:run_id>')
    @require_auth
    def run_detail(run_id):
        row = db.session.get(SearchRun, run_id)
        return jsonify(run_json(row)) if row else error('RUN_NOT_FOUND', 'Recherche introuvable.', 404)
