from flask import jsonify


def register(bp):
    @bp.get('/health')
    def health():
        return jsonify(status='ok')
