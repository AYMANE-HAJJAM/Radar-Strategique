"""Explicit, transactional business-data reset with a restorable data snapshot."""
import argparse
import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import MetaData, inspect, select, func, text
from backend.app import create_app
from backend.app.db.extensions import db

TARGETS = ('targeted_search_feedback', 'targeted_search_result_links', 'targeted_search_brief_versions',
           'targeted_search_sessions', 'result_observations', 'market_reviews', 'result_audit_events',
           'results', 'search_runs')

def encode(value):
    if isinstance(value, datetime): return {'kind': 'datetime', 'value': value.isoformat()}
    if isinstance(value, date): return {'kind': 'date', 'value': value.isoformat()}
    if isinstance(value, Decimal): return {'kind': 'decimal', 'value': str(value)}
    if isinstance(value, bytes): return {'kind': 'bytes', 'value': base64.b64encode(value).decode()}
    return {'kind': 'json', 'value': value}

def decode(value):
    converters = {'datetime': datetime.fromisoformat, 'date': date.fromisoformat,
                  'decimal': Decimal, 'bytes': base64.b64decode, 'json': lambda x: x}
    return converters[value['kind']](value['value'])

def snapshot_rows(conn, tables):
    return {name: [{key: encode(value) for key, value in row.items()}
                   for row in conn.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
            for name, table in tables.items()}

def reset(engine, backup_dir, *, confirm=False, stale_minutes=120, emit=print, after_delete=None):
    with engine.begin() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
        meta = MetaData(); meta.reflect(bind=conn)
        tables = dict(meta.tables)
        if not set(TARGETS).issubset(tables):
            raise RuntimeError('Expected business tables missing; reset refused.')
        if engine.dialect.name == 'postgresql' and confirm:
            names = ', '.join(conn.dialect.identifier_preparer.quote(name) for name in sorted(tables))
            conn.execute(text('LOCK TABLE ' + names + ' IN SHARE ROW EXCLUSIVE MODE'))
        # Fail closed if a new table depends on any reset target, even with CASCADE.
        for name, table in tables.items():
            if name not in TARGETS and any(fk.column.table.name in TARGETS for fk in table.foreign_keys):
                raise RuntimeError(f'Unreviewed dependent table: {name}')
        before = {name: conn.scalar(select(func.count()).select_from(table)) for name, table in tables.items()}
        emit(json.dumps({'delete': {name: before[name] for name in TARGETS},
                         'preserve': {name: count for name, count in before.items() if name not in TARGETS}}))
        if not confirm: return {'confirmed': False, 'before': before}
        runs = tables['search_runs']
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_minutes)
        active = conn.scalar(select(func.count()).select_from(runs).where(
            runs.c.status.in_(('initialized', 'running')), runs.c.started_at >= cutoff))
        targeted = tables['targeted_search_sessions']
        active += conn.scalar(select(func.count()).select_from(targeted).where(targeted.c.status == 'RUNNING'))
        if active: raise RuntimeError('Active non-stale searches exist; wait for them to finish before resetting.')
        rows = snapshot_rows(conn, tables)
        schema = {name: {'columns': [c.name for c in table.columns],
                         'foreign_keys': inspect(conn).get_foreign_keys(name)} for name, table in tables.items()}
        payload = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                   'targets': list(TARGETS), 'before': before, 'schema': schema, 'rows': rows}
        directory = Path(backup_dir); directory.mkdir(parents=True, exist_ok=True)
        path = directory / ('radar-data-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode('utf-8')
        with path.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        digest = hashlib.sha256(raw).hexdigest()
        path.with_suffix('.sha256').write_text(digest, encoding='ascii')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest: raise RuntimeError('Backup verification failed')
        emit('Verified backup: ' + str(path))
        for name in TARGETS:
            conn.execute(tables[name].delete())
            if after_delete: after_delete(name)
        after = {name: conn.scalar(select(func.count()).select_from(table)) for name, table in tables.items()}
        if any(after[name] for name in TARGETS): raise RuntimeError('Reset left business rows')
        kept = {name: table for name, table in tables.items() if name not in TARGETS}
        if snapshot_rows(conn, kept) != {name: rows[name] for name in kept}:
            raise RuntimeError('Preserved data changed')
        if set(inspect(conn).get_table_names()) != set(tables): raise RuntimeError('Schema changed')
        report = {'confirmed': True, 'backup': str(path), 'sha256': digest, 'before': before, 'after': after}
    emit(json.dumps(report))
    return report

def restore(engine, snapshot, *, confirm=False):
    if not confirm: raise ValueError('Restore requires --confirm')
    path = Path(snapshot); raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != path.with_suffix('.sha256').read_text().strip():
        raise RuntimeError('Snapshot checksum mismatch')
    data = json.loads(raw)
    if data['format'] != 1 or data['targets'] != list(TARGETS): raise RuntimeError('Unknown snapshot format')
    with engine.begin() as conn:
        meta = MetaData(); meta.reflect(bind=conn)
        if engine.dialect.name == 'postgresql':
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            names = ', '.join(conn.dialect.identifier_preparer.quote(t) for t in sorted(meta.tables))
            conn.execute(text('LOCK TABLE ' + names + ' IN SHARE ROW EXCLUSIVE MODE'))
        kept = {n:t for n,t in meta.tables.items() if n not in TARGETS}
        if snapshot_rows(conn, kept) != {n:data['rows'][n] for n in kept}: raise RuntimeError('Preserved data differs; restore refused')
        for name in TARGETS:
            if conn.scalar(select(func.count()).select_from(meta.tables[name])):
                raise RuntimeError('Restore requires empty business tables; never overwrites new discoveries')
        for name in reversed(TARGETS):
            table = meta.tables[name]
            if [c.name for c in table.columns] != data['schema'][name]['columns']: raise RuntimeError('Schema mismatch')
            rows = [{key: decode(value) for key, value in row.items()} for row in data['rows'][name]]
            if rows: conn.execute(table.insert(), rows)
        if snapshot_rows(conn, meta.tables) != data['rows']: raise RuntimeError('Restored data differs')
    return {'restored': str(path), 'counts': data['before']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--backup-dir', default='backups')
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--report-json', type=Path)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        try:
            report = (restore(db.engine, args.restore, confirm=args.confirm) if args.restore else
                      reset(db.engine, args.backup_dir, confirm=args.confirm,
                            stale_minutes=app.config['SEARCH_RUN_STALE_MINUTES']))
        except Exception as error:
            print('Reset/restore failed; transaction rolled back: ' + (str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__))
            raise SystemExit(1) from None
        if args.report_json:
            try:
                args.report_json.write_text(json.dumps(report, indent=2), encoding='utf-8')
            except OSError:
                print('Database operation completed, but the requested report file could not be written.')
                raise SystemExit(2) from None

if __name__ == '__main__': main()
