"""Exercise ledger DDL only on isolated SQLite / PostgreSQL offline SQL."""
import importlib.util
import io
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def migration(name):
    path = Path(__file__).resolve().parents[3] / 'migrations' / 'versions' / name
    spec = importlib.util.spec_from_file_location(name.split('.')[0], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ledger_migration_preserves_legacy_rows_and_downgrades():
    engine = create_engine('sqlite://')
    ledger = migration('e7c91b2486af_pmmp_processing_ledger.py')
    with engine.begin() as connection:
        # A minimal old table is enough to exercise batch copying with a legacy row.
        connection.execute(text('CREATE TABLE pmmp_listing_index (id INTEGER PRIMARY KEY, fingerprint VARCHAR(64))'))
        connection.execute(text("INSERT INTO pmmp_listing_index VALUES (1, 'fixture-original')"))
        ledger.op = Operations(MigrationContext.configure(connection))
        ledger.upgrade()
        row = connection.execute(text('SELECT * FROM pmmp_listing_index')).mappings().one()
        assert row['fingerprint'] == 'fixture-original'
        assert row['processing_state'] is None
        assert row['processing_attempts'] == 0
        ledger.downgrade()
        assert connection.execute(text('SELECT fingerprint FROM pmmp_listing_index')).scalar() == 'fixture-original'
        assert 'processing_state' not in {col['name'] for col in inspect(connection).get_columns('pmmp_listing_index')}
    engine.dispose()


def test_postgresql_migration_sql_does_not_consume_legacy_work():
    ledger = migration('e7c91b2486af_pmmp_processing_ledger.py')
    output = io.StringIO()
    context = MigrationContext.configure(dialect_name='postgresql',
                                        opts={'as_sql': True, 'output_buffer': output})
    ledger.op = Operations(context)
    ledger.upgrade()
    sql = output.getvalue()
    assert 'ADD COLUMN processing_state' in sql
    assert 'UPDATE ' not in sql
    assert 'INSERT ' not in sql
    assert 'DELETE ' not in sql


def test_refresh_checkpoint_migration_sqlite_inserts_singleton():
    engine = create_engine('sqlite://')
    refresh = migration('f8a3c1d92e07_pmmp_refresh_checkpoint.py')
    with engine.begin() as connection:
        refresh.op = Operations(MigrationContext.configure(connection))
        refresh.upgrade()
        row = connection.execute(text(
            'SELECT id, status, cursor_page, cycle_complete, last_new FROM pmmp_refresh_checkpoint'
        )).mappings().one()
        assert row['id'] == 1
        assert row['status'] == 'idle'
        assert row['cursor_page'] == 0
        assert row['cycle_complete'] in (0, False)
        assert row['last_new'] == 0
        refresh.downgrade()
        assert 'pmmp_refresh_checkpoint' not in inspect(connection).get_table_names()
    engine.dispose()


def test_refresh_checkpoint_postgresql_sql_uses_boolean_false():
    """Offline PostgreSQL SQL must not cast integer 0 into boolean cycle_complete."""
    refresh = migration('f8a3c1d92e07_pmmp_refresh_checkpoint.py')
    output = io.StringIO()
    context = MigrationContext.configure(
        dialect_name='postgresql', opts={'as_sql': True, 'output_buffer': output})
    refresh.op = Operations(context)
    refresh.upgrade()
    sql = output.getvalue()
    assert 'CREATE TABLE pmmp_refresh_checkpoint' in sql
    assert 'cycle_complete' in sql
    assert 'BOOLEAN' in sql.upper() or 'boolean' in sql
    # Seed INSERT must use SQL FALSE for the boolean column, not integer 0.
    assert 'FALSE' in sql.upper()
    assert "VALUES (1, 'idle', 0, FALSE," in sql.replace('false', 'FALSE').replace('False', 'FALSE')
    # Boolean server default must not be the integer literal used for counters.
    create = sql.split('INSERT INTO pmmp_refresh_checkpoint')[0]
    assert 'cycle_complete' in create
    assert "cycle_complete BOOLEAN DEFAULT '0'" not in create
    assert 'cycle_complete BOOLEAN DEFAULT 0' not in create
