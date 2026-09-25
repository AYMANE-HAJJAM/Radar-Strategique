from flask import Flask
from datetime import timedelta

from app.config import load_config
from app.db.extensions import db, migrate
from app.core.logging import configure_logging
from app.core.job_runner import LocalJobRunner


def create_app(test_config=None):
    configure_logging()
    app = Flask(__name__)
    app.config.from_mapping(load_config())
    if test_config:
        app.config.update(test_config)
    app.permanent_session_lifetime = timedelta(days=30)
    if not app.config['SQLALCHEMY_DATABASE_URI']:
        raise ValueError('DATABASE_URL is required. Copy .env.example to .env and configure PostgreSQL.')
    if not app.testing and not app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg://'):
        raise ValueError('DATABASE_URL must use PostgreSQL with psycopg.')
    if app.config['FLASK_ENV'] == 'production' and app.config['SECRET_KEY'] in (None, '', 'replace-with-a-random-secret'):
        raise ValueError('Set a random SECRET_KEY for production.')
    db.init_app(app)
    from app.db import models  # noqa: F401
    migrate.init_app(app, db)
    from app.api import api
    from app.cli import register_commands
    app.register_blueprint(api, url_prefix='/api')
    app.extensions['radar_job_runner'] = LocalJobRunner(max_workers=2, capacity=5)
    register_commands(app)
    return app
