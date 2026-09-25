import logging

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from app.db.extensions import db
from app.core.logging import log_failure

api = Blueprint('api', __name__)

from app.api import admin_users, auth, health, radars, results, runs, targeted_search

for module in (auth, admin_users, health, radars, results, runs, targeted_search):
    module.register(api)


@api.after_request
def cors(response):
    origin = request.headers.get('Origin')
    allowed = current_app.config.get('FRONTEND_URL')
    if origin and origin == allowed:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-CSRF-Token'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Vary'] = 'Origin'
    return response


@api.route('/<path:path>', methods=['OPTIONS'])
def options(path):
    return '', 204


@api.errorhandler(SQLAlchemyError)
def database_error(exc):
    db.session.rollback()
    log_failure(logging.getLogger(__name__), 'API database operation', exc)
    return jsonify(error={'code': 'DATABASE_UNAVAILABLE', 'message': 'Base de données temporairement indisponible.'}), 503


@api.errorhandler(404)
def not_found(exc):
    return jsonify(error={'code': 'NOT_FOUND', 'message': 'Ressource introuvable.'}), 404


@api.errorhandler(Exception)
def unexpected(exc):
    log_failure(logging.getLogger(__name__), 'Unexpected API error', exc)
    return jsonify(error={'code': 'INTERNAL_ERROR', 'message': 'Une erreur inattendue est survenue.'}), 500
