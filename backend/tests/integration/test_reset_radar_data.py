from pathlib import Path
from unittest.mock import Mock
import pytest
from sqlalchemy import inspect, text
from backend.app.db.extensions import db
from backend.app.db.models import Radar, Result, SearchRun, MarketReview, ResultAuditEvent, ResultObservation
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.review import page, decide
from backend.app.bot.handlers.common import start
from backend.scripts.reset_radar_data import reset, restore, TARGETS
from backend.scripts.test_agent import MockAnalyzer
from backend.tests.integration.test_agent import candidate
from backend.tests.integration.test_phase3 import execute
from test_bot import fixture_update


def populated(app):
    execute(app,[candidate()])
    item=page(app,'pending',0)[0][0]
    decide(app,item['id'],item['version'],'approved',123)


def test_reset_backup_restore_and_rollback(app,tmp_path):
    populated(app)
    with app.app_context():
        db.session.remove()
        with db.engine.connect() as c: c.execute(text('PRAGMA foreign_keys=ON'));c.commit()
        tables=inspect(db.engine).get_table_names()
        report=reset(db.engine,tmp_path)
        assert not report['confirmed'] and not list(tmp_path.iterdir())
        assert report['before']['results']==1
        def fail(name):
            if name=='results':raise RuntimeError('Injected transaction failure')
        with pytest.raises(RuntimeError,match='Injected'):
            reset(db.engine,tmp_path,confirm=True,after_delete=fail)
        assert reset(db.engine,tmp_path)['before']==report['before']
        done=reset(db.engine,tmp_path,confirm=True)
        assert all(done['after'][name]==0 for name in TARGETS)
        assert done['after']['radars']==5 and inspect(db.engine).get_table_names()==tables
        assert db.session.execute(text('PRAGMA foreign_key_check')).all()==[]
        db.session.remove()
        restored=restore(db.engine,done['backup'],confirm=True)
        assert restored['counts']==report['before']
        assert reset(db.engine,tmp_path)['before']==report['before']
        with pytest.raises(RuntimeError,match='empty business'):
            restore(db.engine,done['backup'],confirm=True)


def test_active_run_blocks_reset(app,tmp_path):
    with app.app_context():
        radar=db.session.scalar(db.select(Radar))
        db.session.add(SearchRun(radar_id=radar.id));db.session.commit();db.session.remove()
        with pytest.raises(RuntimeError,match='Active'):
            reset(db.engine,tmp_path,confirm=True)
        assert reset(db.engine,tmp_path)['before']['search_runs']==1
        assert not list(tmp_path.iterdir())


def test_unknown_dependent_table_blocks_reset(app,tmp_path):
    with app.app_context():
        with db.engine.begin() as c:
            c.execute(text('CREATE TABLE external_notes (id INTEGER PRIMARY KEY, result_id INTEGER REFERENCES results(id) ON DELETE CASCADE)'))
        with pytest.raises(RuntimeError,match='Unreviewed'):
            reset(db.engine,tmp_path,confirm=True)
        with db.engine.begin() as c:c.execute(text('DROP TABLE external_notes'))


def fresh_candidates(app):
    codes=list(app.config['RADAR_MODELS'])
    data=[candidate(),
          {'title':'Future heritage project','officially_announced':True},
          {'title':'Agence patrimoine','institution':'Agence','institution_relevant':True,'recent_activity':'Lancement du programme de rehabilitation du patrimoine'},
          {'title':'Draft urban heritage law','document_type':'draft_law','reported_status':'preparation','reliable_status_evidence':True,'official_source':'https://example.com/draft','status_evidence':'Officially in preparation.'},
          {'title':'Heritage Morocco program','morocco_related':True,'reported_funding_status':'active','strategically_relevant':True}]
    return [(code,RADAR_AGENT_REGISTRY.resolve(code).normalize_candidate(value)) for code,value in zip(codes,data)]


async def test_all_five_clean_discovery_then_unchanged_and_authorization(app,tmp_path):
    populated(app)
    allowed=app.config['ALLOWED_TELEGRAM_USER_IDS']
    with app.app_context():
        db.session.remove();report=reset(db.engine,tmp_path,confirm=True)
    assert report['after']['search_runs']==0
    for code,item in fresh_candidates(app):
        for mode in ('pending','approved','rejected'):assert not page(app,mode,0,code=code)[0]
        agent=AgentOrchestrator(app,collector=lambda _,item=item:[item],analyzer=MockAnalyzer())
        first=agent.run_radar(code)
        assert first.status=='completed' and first.new_results_count==1
        analyzer=Mock()
        again=AgentOrchestrator(app,collector=lambda _,item=item:[item],analyzer=analyzer).run_radar(code)
        assert again.status=='completed' and again.new_results_count==0 and again.duplicate_count==1
        analyzer.analyze_candidate.assert_not_called()
    assert app.config['ALLOWED_TELEGRAM_USER_IDS']==allowed
    u,c=fixture_update(app);await start(u,c)
    assert len(u.effective_message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard)==6


def test_stale_incomplete_run_is_cleared(app,tmp_path):
    from datetime import datetime,timedelta,timezone
    with app.app_context():
        radar=db.session.scalar(db.select(Radar))
        db.session.add(SearchRun(radar_id=radar.id,status='running',started_at=datetime.now(timezone.utc)-timedelta(days=2)))
        db.session.commit();db.session.remove()
        report=reset(db.engine,tmp_path,confirm=True)
        assert report['before']['search_runs']==1 and report['after']['search_runs']==0
