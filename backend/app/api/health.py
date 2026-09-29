from flask import jsonify

from app.core.internal_api import database_available


def register(bp):
    @bp.get('/health')
    def health():
        return jsonify(status='ok')

    @bp.get('/ready')
    def ready():
        available = database_available()
        return jsonify(status='ready' if available else 'unavailable'), 200 if available else 503
