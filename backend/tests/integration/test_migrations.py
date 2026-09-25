from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from flask_migrate import downgrade, upgrade
from sqlalchemy import inspect
from sqlalchemy import text

from backend.app import create_app
from backend.app.db.extensions import db
from backend.app.db.models import Radar
from backend.app.db.repositories.radars import seed_radars


def test_migration_round_trip(tmp_path):
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path / 'migration.db').as_posix(),
        'SQLALCHEMY_ENGINE_OPTIONS': {},
    })
    with app.app_context():
        upgrade()
        assert {'radars', 'results', 'search_runs', 'targeted_search_sessions',
                'targeted_search_brief_versions', 'targeted_search_result_links',
                'targeted_search_feedback'} <= set(inspect(db.engine).get_table_names())
        with db.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), db.metadata) == []
        seed_radars()
        assert db.session.scalar(db.select(db.func.count()).select_from(Radar)) == 5
        db.session.remove()
        downgrade(revision='base')
        assert 'radars' not in inspect(db.engine).get_table_names()
        upgrade()
        db.engine.dispose()


def test_postgresql_migration_compiles_without_connection(capsys):
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'postgresql+psycopg://test:test@localhost/test',
    })
    with app.app_context():
        upgrade(sql=True)
    output = capsys.readouterr().out
    assert 'CREATE TABLE radars' in output
    assert 'TIMESTAMP WITH TIME ZONE' in output
    assert 'UNIQUE (radar_id, fingerprint)' in output
    assert 'CREATE UNIQUE INDEX uq_search_runs_active_radar' in output
    assert 'CREATE TABLE targeted_search_sessions' in output


def test_phase1_history_survives_upgrade(tmp_path):
    app = create_app({'TESTING': True,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path / 'legacy.db').as_posix(),
                      'SQLALCHEMY_ENGINE_OPTIONS': {}})
    with app.app_context():
        upgrade(revision='fc4d21f65ae0')
        db.session.execute(text("INSERT INTO radars (id, code, name, description, is_active, created_at) "
                                "VALUES (1, 'RADAR_1_MARKETS', 'Markets', 'Legacy', true, CURRENT_TIMESTAMP)"))
        for run_id in (1, 2):
            db.session.execute(text("INSERT INTO search_runs (id, radar_id, status, started_at, new_results_count) "
                                    "VALUES (:id, 1, 'initialized', CURRENT_TIMESTAMP, 0)"), {'id': run_id})
        db.session.commit()
        upgrade()
        rows = db.session.execute(text('SELECT id, status, current_stage, error_kind FROM search_runs ORDER BY id')).all()
        assert len(rows) == 2
        assert all(row.status == 'failed' and row.error_kind == 'legacy_placeholder' for row in rows)
        db.session.remove()
        db.engine.dispose()


def test_workflow_migration_maps_existing_human_decisions(tmp_path):
    app = create_app({'TESTING': True,
                      'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path / 'workflow.db').as_posix(),
                      'SQLALCHEMY_ENGINE_OPTIONS': {}})
    with app.app_context():
        upgrade(revision='d91eac4206b1')
        db.session.execute(text("INSERT INTO radars (id,code,name,description,is_active,created_at) "
                                "VALUES (1,'RADAR_1_MARKETS','Markets','Legacy',true,CURRENT_TIMESTAMP)"))
        for result_id, status in ((1, 'new'), (2, 'manual_review'), (3, 'rejected')):
            db.session.execute(text("INSERT INTO results (id,radar_id,title,status,priority,fingerprint,source_metadata,radar_metadata,first_seen_at,last_seen_at,created_at,updated_at) "
                "VALUES (:id,1,:title,:status,'3',:fingerprint,'{}','{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),
                {'id': result_id, 'title': f'Legacy {result_id}', 'status': status, 'fingerprint': str(result_id) * 64})
        db.session.execute(text("INSERT INTO market_reviews (result_id,content_hash,decision,reviewed_by,reviewed_at,previous_review_reason,snapshot) "
            "VALUES (1,'hash1','approved',123,CURRENT_TIMESTAMP,'reason','{}'),"
            "(3,'hash3','rejected',456,CURRENT_TIMESTAMP,'reason','{}')"))
        db.session.commit()
        upgrade()
        rows = db.session.execute(text('SELECT id,discovery_status,review_status,reviewed_by FROM results ORDER BY id')).all()
        assert [(row.discovery_status, row.review_status, row.reviewed_by) for row in rows] == [
            ('NEW', 'APPROVED', 123), ('UNCHANGED', 'PENDING', None), ('UNCHANGED', 'REJECTED', 456)]
        events = db.session.execute(text('SELECT event_type FROM result_audit_events ORDER BY id')).scalars().all()
        assert events.count('DISCOVERED') == 3 and 'APPROVED' in events and 'REJECTED' in events
        db.session.remove()
        db.engine.dispose()
