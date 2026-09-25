"""Backup, apply, and verify the additive targeted-search migration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from sqlalchemy import MetaData, inspect, select, func, text

from backend.app import create_app
from backend.app.db.extensions import db
from backend.scripts.reset_radar_data import snapshot_rows, decode

HEAD = 'f19a7c4d2e61'
EXPECTED_BEFORE = 'c83d2e5f9a31'
NEW_TABLES = {
    'targeted_search_sessions', 'targeted_search_brief_versions',
    'targeted_search_result_links', 'targeted_search_feedback',
}
CRITICAL = ('results','result_observations','search_runs','market_reviews',
            'result_audit_events','radars','source_states')


def schema_report(conn, names):
    inspector=inspect(conn)
    return {name:{
        'columns':[column['name'] for column in inspector.get_columns(name)],
        'indexes':[index['name'] for index in inspector.get_indexes(name)],
        'foreign_keys':[foreign.get('name') for foreign in inspector.get_foreign_keys(name)],
        'unique_constraints':[constraint.get('name') for constraint in inspector.get_unique_constraints(name)],
    } for name in names}


def write_backup(rows, revision):
    directory=Path('backups');directory.mkdir(exist_ok=True)
    payload={'format':'targeted-search-migration-preflight-v1','revision':revision,
             'created_at':datetime.now(timezone.utc).isoformat(),'rows':rows}
    raw=json.dumps(payload,ensure_ascii=True,sort_keys=True).encode('utf-8')
    path=directory/('targeted-search-migration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
    with path.open('xb') as handle:
        handle.write(raw);handle.flush();os.fsync(handle.fileno())
    digest=hashlib.sha256(raw).hexdigest()
    path.with_suffix('.sha256').write_text(digest,encoding='ascii')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise RuntimeError('Backup checksum verification failed.')
    for entries in json.loads(raw)['rows'].values():
        for row in entries:
            for value in row.values():decode(value)
    return path,digest


def active_runs(conn, tables):
    active=conn.scalar(select(func.count()).select_from(tables['search_runs']).where(
        tables['search_runs'].c.status.in_(('initialized','running')))) or 0
    if 'targeted_search_sessions' in tables:
        active+=conn.scalar(select(func.count()).select_from(tables['targeted_search_sessions']).where(
            tables['targeted_search_sessions'].c.status=='RUNNING')) or 0
    return active


def orm_transaction_check(conn, tables):
    transaction=conn.begin()
    try:
        now=datetime.now(timezone.utc)
        conn.execute(tables['targeted_search_sessions'].insert().values(
            id=-2147480000,title='migration validation',original_prompt='rollback only',
            creator_user_id=-1,current_version=1,status='DRAFT',run_summary={},
            created_at=now,updated_at=now))
        conn.execute(tables['targeted_search_brief_versions'].insert().values(
            id=-2147480000,session_id=-2147480000,version=1,brief={'validation':True},
            created_by_user_id=-1,created_at=now))
        result_id=conn.scalar(select(tables['results'].c.id).limit(1))
        if result_id is not None:
            conn.execute(tables['targeted_search_result_links'].insert().values(
                id=-2147480000,session_id=-2147480000,brief_version=1,result_id=result_id,
                match_status='KNOWN',review_status='PENDING',relevance_score=50,
                content_fingerprint='0'*64,first_matched_at=now,last_matched_at=now))
        conn.execute(tables['targeted_search_feedback'].insert().values(
            id=-2147480000,session_id=-2147480000,brief_version=1,result_id=None,
            decision='TOO_BROAD',user_id=-1,created_at=now))
    finally:
        transaction.rollback()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    app=create_app()
    report={'expected_head':HEAD,'applied':False,
            'command':'.venv\\Scripts\\python.exe -m flask --app app:create_app db upgrade'}
    with app.app_context():
        if db.engine.dialect.name!='postgresql':
            raise RuntimeError('Production migration guard requires PostgreSQL.')
        with db.engine.connect() as conn:
            meta=MetaData();meta.reflect(bind=conn);tables=dict(meta.tables)
            revision=conn.scalar(text('SELECT version_num FROM alembic_version'))
            if revision not in {EXPECTED_BEFORE,HEAD}:
                raise RuntimeError('Unexpected production revision: '+str(revision))
            active=active_runs(conn,tables)
            if active:raise RuntimeError('Active initialized/running search exists.')
            rows=snapshot_rows(conn,tables)
            before={name:len(entries) for name,entries in rows.items()}
        path,digest=write_backup(rows,revision)
        report.update(revision_before=revision,active_runs=active,backup=str(path),
                      backup_sha256=digest,before={name:before.get(name) for name in CRITICAL})
        if args.apply and revision!=HEAD:
            completed=subprocess.run([sys.executable,'-m','flask','--app','run','db','upgrade'],
                capture_output=True,text=True,timeout=120)
            if completed.returncode:
                Path('audit-output/targeted-migration-command-error.log').write_text(
                    completed.stderr,encoding='utf-8')
                raise RuntimeError('Flask migration command failed.')
            report['applied']=True
        with db.engine.connect() as conn:
            after_meta=MetaData();after_meta.reflect(bind=conn);after_tables=dict(after_meta.tables)
            revision_after=conn.scalar(text('SELECT version_num FROM alembic_version'))
            if args.apply and revision_after!=HEAD:raise RuntimeError('Target revision not reached.')
            missing=NEW_TABLES-set(after_tables)
            if args.apply and missing:raise RuntimeError('Targeted tables missing: '+','.join(sorted(missing)))
            after={name:conn.scalar(select(func.count()).select_from(table))
                   for name,table in after_tables.items()}
            for name in tables:
                if after[name]!=before[name]:
                    raise RuntimeError('Existing row count changed: '+name)
            if args.apply:
                conn.rollback()
                orm_transaction_check(conn,after_tables)
                schema=schema_report(conn,NEW_TABLES)
            else:schema={}
        report.update(revision_after=revision_after,
            after={name:after.get(name) for name in CRITICAL},
            existing_row_counts_identical=all(after.get(name)==before[name] for name in tables),
            targeted_schema=schema,transaction_rollback_validated=bool(args.apply))
        Path('audit-output').mkdir(exist_ok=True)
        Path('audit-output/targeted-search-migration.json').write_text(
            json.dumps(report,indent=2,default=str),encoding='utf-8')
        print(json.dumps(report,indent=2,default=str))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Targeted migration guard stopped: '+type(error).__name__+' — '+str(error))
        raise SystemExit(1) from None
