"""Operational acceptance against isolated databases and simulated Telegram transport."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from time import perf_counter
from unittest.mock import Mock, patch

import pytest

from backend.app import create_app
from backend.app.core.agent_errors import ActiveRunError
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.bot.handlers.common import on_callback, start
from backend.app.db.extensions import db
from backend.app.db.models import Result, SearchRun, MarketReview, ResultAuditEvent, utcnow
from backend.app.core.review import page, detail, decide, run_page
from backend.app.db.repositories.radars import seed_radars
from backend.app.db.repositories.source_state import SourceStateService
from backend.app.integrations.http.adapters import SourceDefinition, SourceFetch
from test_bot import fixture_update
from test_market_usability import review_rows
from backend.tests.integration.test_agent import candidate

CODE = 'RADAR_1_MARKETS'
EVIDENCE = {}


@pytest.mark.parametrize('action', ['search', 'pending', 'details', 'next', 'approve'])
async def test_ten_clicks_execute_once(app, action):
    item = review_rows(app, 11)[0]
    payload = {'search': 'search:'+CODE, 'pending': 'pending:'+CODE,
        'details': f'm:details:pending:{item["id"]}:0', 'next': 'm:pending:1',
        'approve': f'm:approve:{item["id"]}:{item["version"]}:0'}[action]
    update, context = fixture_update(app, data=payload)
    if action == 'search':
        runner = Mock(); runner.submit.return_value = Future()
        context.application.bot_data['job_runner'] = runner
        tasks = []
        context.application.create_task = tasks.append
    with app.app_context():
        before = db.session.scalar(db.select(db.func.count()).select_from(SearchRun))
    await asyncio.gather(*(on_callback(update, context) for _ in range(10)))
    with app.app_context():
        new_runs = db.session.scalar(db.select(db.func.count()).select_from(SearchRun)) - before
        decisions = db.session.scalar(db.select(db.func.count()).select_from(MarketReview))
    assert new_runs == int(action == 'search')
    assert decisions == int(action == 'approve')
    if action == 'search':
        assert runner.submit.call_count == 1 and len(tasks) == 1
        for coroutine in tasks: coroutine.close()
    elif action == 'details':
        assert context.application.bot.edit_message_text.await_count >= 1
        assert update.effective_message.reply_text.await_count == 0
    elif action in {'pending', 'next'}:
        assert update.effective_message.reply_text.await_count == 6
    else:
        # approve refreshes pending page in place (first open creates slots).
        assert update.effective_message.reply_text.await_count == 6
    EVIDENCE[action] = {'callbacks':10, 'effective_actions':1, 'new_search_runs':new_runs,
        'review_decisions':decisions, 'paid_calls':0, 'transport':'mock; search worker held pending'}


def test_two_users_concurrent_database_lock_and_crash_recovery(tmp_path):
    application = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'lock.db'),
        'SQLALCHEMY_ENGINE_OPTIONS':{}, 'ALLOWED_TELEGRAM_USER_IDS':frozenset({123,456})})
    with application.app_context(): db.create_all(); seed_radars()
    barrier = Barrier(10)
    def reserve(n):
        barrier.wait()
        try: return AgentOrchestrator(application).reserve(CODE, [123,456][n%2])
        except ActiveRunError: return None
    with ThreadPoolExecutor(max_workers=10) as pool:
        ids = list(pool.map(reserve, range(10)))
    assert sum(value is not None for value in ids) == 1
    with application.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(SearchRun)) == 1
        old = db.session.scalar(db.select(SearchRun)); old.started_at = utcnow()-timedelta(days=1)
        db.session.commit()
    new_id = AgentOrchestrator(application).reserve(CODE,456)
    with application.app_context():
        old = db.session.scalar(db.select(SearchRun).where(SearchRun.id != new_id))
        assert old.error_kind == 'stale_run_recovered'
        db.session.remove(); db.engine.dispose()
    EVIDENCE['concurrent_search']={'attempts':10,'users':2,'created_runs':1,'stale_recovery':True}


def test_shared_queue_stale_decision_and_transaction_rollback(app):
    app.config['ALLOWED_TELEGRAM_USER_IDS']=frozenset({123,456})
    item=review_rows(app)[0]
    with patch.object(db.session,'commit',side_effect=RuntimeError('simulated database failure')):
        with pytest.raises(RuntimeError): decide(app,item['id'],item['version'],'approved',123)
    assert len(page(app,'pending',0)[0]) == 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(MarketReview)) == 0
    decide(app,item['id'],item['version'],'approved',123)
    assert not page(app,'pending',0)[0] and len(page(app,'approved',0)[0]) == 1
    with pytest.raises(ValueError): decide(app,item['id'],item['version'],'rejected',456)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(MarketReview)) == 1
        event=db.session.scalar(db.select(ResultAuditEvent).where(ResultAuditEvent.event_type=='APPROVED'))
        assert event.performed_by==123 and event.created_at
        assert event.event_metadata['previous_status']=='PENDING' and event.event_metadata['new_status']=='APPROVED'
    EVIDENCE['shared_review']={'rollback':True,'stale_second_user_rejected':True,'decision_audit_events':1}


def test_source_state_second_run_handles_sqlite_timestamp(app):
    with app.app_context():
        service=SourceStateService()
        service.record(SourceFetch(SourceDefinition('Test','https://example.gov.ma/index'),'https://example.gov.ma/index',
            'CHANGED',content_hash='a'*64,etag='abc',http_requests=1))
        db.session.commit(); db.session.remove()
        assert not service.refresh_due('https://example.gov.ma/index',7)
        other = SourceStateService('RADAR_3_INSTITUTIONS')
        assert other.refresh_due('https://example.gov.ma/index',7)
        other.record(SourceFetch(SourceDefinition('Test','https://example.gov.ma/index'),
            'https://example.gov.ma/index','CHANGED',content_hash='b'*64))
        db.session.commit()
        assert service.get('https://example.gov.ma/index')['content_hash']=='a'*64
        assert other.get('https://example.gov.ma/index')['content_hash']=='b'*64


async def test_local_action_timings(app):
    item=review_rows(app,11)[0]
    timings={}
    for name,payload in [('start',None),('radar_menu','radar:'+CODE),('pending','pending:'+CODE),
        ('approved','approved:'+CODE),('rejected','rejected:'+CODE),
        ('details',f'm:details:pending:{item["id"]}:0'),('pagination','m:pending:1'),('history','runs:'+CODE)]:
        values=[]
        for _ in range(5):
            update,context=fixture_update(app,data=payload)
            begin=perf_counter()
            await (start(update,context) if payload is None else on_callback(update,context))
            values.append((perf_counter()-begin)*1000)
        timings[name]={'median_ms':round(sorted(values)[2],3),'max_ms':round(max(values),3)}
    begin=perf_counter(); decide(app,item['id'],item['version'],'approved',123)
    timings['approve_db_ms']=round((perf_counter()-begin)*1000,3)
    item=page(app,'pending',0)[0][0]
    begin=perf_counter(); decide(app,item['id'],item['version'],'rejected',123)
    timings['reject_db_ms']=round((perf_counter()-begin)*1000,3)
    from backend.app.bot.handlers.jobs import launch_search
    from backend.app.core.agent_job_service import JobTicket
    update,context=fixture_update(app,data='search:'+CODE)
    context.application.bot_data['job_runner']=Mock()
    tasks=[]; context.application.create_task=tasks.append
    pending=Future()
    with patch('app.bot.handlers.jobs.launch_radar',return_value=JobTicket(999,pending)):
        begin=perf_counter(); await launch_search(update,context,CODE,1)
        timings['search_ack_ms']=round((perf_counter()-begin)*1000,3)
    assert not pending.done()
    for coroutine in tasks: coroutine.close()
    EVIDENCE['performance']=timings


def test_write_acceptance_evidence():
    # Local artifact only; tests above prohibit all real HTTP via conftest.
    Path('docs/historical/audits/production-acceptance.json').write_text(json.dumps(EVIDENCE,indent=2),encoding='utf-8')


@pytest.mark.parametrize('number',[1,2,3,4,5])
def test_all_radar_second_snapshot_preserves_human_review(app,number):
    from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
    from backend.app.core.collector_registry import COLLECTORS
    from backend.app.core.validation import today_in_morocco
    code=list(RADAR_AGENT_REGISTRY.catalog())[number-1]
    collector=COLLECTORS[code](Mock(),app.config)
    today=today_in_morocco()
    if number==1: item=candidate(source_conflict=True)
    elif number==2:
        item=collector._candidate(title='Convention signee pour rehabilitation medina',url='https://maroc.ma/project',
            evidence='Signature d une convention pour la rehabilitation du patrimoine',institution='Commune',publication_date=today)
    elif number==3:
        item=collector._candidate('Programme patrimoine','https://maroc.ma/institution',
            'Lancement du programme de rehabilitation de medina','Agence urbaine',today)
    elif number==4:
        item=collector._candidate('Projet de loi urbanisme','https://sgg.gov.ma/draft',
            'Projet de loi relatif au patrimoine et urbanisme','SGG',today)
    else:
        item=collector._candidate('Morocco urban development','https://worldbank.org/project',
            'Active Morocco urban development financing procurement plan','Commune',today)
    assert item is not None
    engine=AgentOrchestrator(app,collector=lambda _: [item],no_ai=True)
    first=engine.run_radar(code)
    assert first.new_results_count==1
    card=page(app,'pending',0,code=code)[0][0]
    decide(app,card['id'],card['version'],'approved',123,code)
    with app.app_context(): old_seen=db.session.get(Result,card['id']).last_seen_at
    second=engine.run_radar(code)
    assert second.new_results_count==0 and second.duplicate_count==1 and second.ai_calls==0 and second.search_calls==0
    assert not page(app,'pending',0,code=code)[0]
    assert len(page(app,'approved',0,code=code)[0])==1
    with app.app_context():
        row=db.session.get(Result,card['id'])
        assert row.last_seen_at>=old_seen and row.review_status=='APPROVED'
        assert db.session.scalar(db.select(db.func.count()).select_from(Result))==1
    EVIDENCE[f'memory_radar{number}']={'first_new':1,'second_new':0,'second_duplicates':1,
        'rows':1,'second_paid_calls':0,'review_preserved':True}


@pytest.mark.parametrize('prefix,code,module',[('p','RADAR_2_PROJECTS','projects'),
    ('i','RADAR_3_INSTITUTIONS','institutions'),('l','RADAR_4_POLICIES','policies'),('f','RADAR_5_FUNDING','funding')])
async def test_nonmarket_queue_replacement_and_details_back(app,prefix,code,module):
    from backend.app.bot.handlers import compact_review
    item={'id':1,'title':'Public project','url':'https://example.com/item','version':'a'*12}
    update,context=fixture_update(app,data='pending:'+code)
    with patch.object(compact_review,'page',return_value=([item],False,1)),\
         patch.object(compact_review,'detail',return_value=item):
        for payload in ['pending:'+code,f'{prefix}:details:pending:1:0',f'{prefix}:pending:0',
                        f'{prefix}:details:pending:1:0',f'{prefix}:pending:0']:
            context.application.bot_data['callback_debounce']={}
            update.callback_query.data=payload
            await on_callback(update,context)
    view=context.user_data['queue_view']
    assert view['view_key']=='app.bot.handlers.'+module
    assert len(view['result_message_ids'])==1
    assert view['navigation_message_id'] is not None
    assert context.application.bot.edit_message_text.await_count >= 2


@pytest.mark.parametrize('value,expected',[('123',{123}),('123, 456, ,789,',{123,456,789})])
def test_multiuser_config_spaces_and_empty_entries(monkeypatch,value,expected):
    from backend.app.config import load_config
    monkeypatch.setenv('ALLOWED_TELEGRAM_USER_IDS',value)
    assert load_config()['ALLOWED_TELEGRAM_USER_IDS']==frozenset(expected)


def test_missing_startup_settings_fail_clearly(app):
    from backend.app.bot import build_application
    app.config['TELEGRAM_BOT_TOKEN']=''
    with pytest.raises(ValueError,match='TELEGRAM_BOT_TOKEN'): build_application(app)
    with pytest.raises(ValueError,match='DATABASE_URL'):
        create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':''})


async def test_inflight_callback_stays_deduplicated_after_debounce(app):
    update,context=fixture_update(app,data='search:'+CODE)
    entered,release=asyncio.Event(),asyncio.Event()
    async def slow(*args): entered.set(); await release.wait()
    with patch('app.bot.handlers.common.launch_search',side_effect=slow) as launch:
        task=asyncio.create_task(on_callback(update,context)); await entered.wait()
        # Simulate elapsed debounce TTL while the original action remains in flight.
        context.application.bot_data['callback_debounce']={}
        await on_callback(update,context)
        release.set(); await task
        assert launch.call_count==1


@pytest.mark.parametrize('code',[403,429,500,None])
def test_source_failures_are_isolated(app,code):
    from urllib.error import HTTPError
    from backend.app.integrations.http.adapters import BaseSourceAdapter
    opener=Mock()
    opener.open.side_effect=TimeoutError() if code is None else HTTPError('https://example.gov.ma/index',code,'failure',{},None)
    result=BaseSourceAdapter(SourceDefinition('Failure','https://example.gov.ma/index'),
        ('example.gov.ma',),opener=opener).fetch()
    assert result.status == ('BLOCKED' if code in {403,429} else 'FAILED')
    assert opener.open.call_count==1


def test_cached_source_does_not_trigger_paid_gap_search(app):
    from backend.app.core.collector_registry import COLLECTORS
    from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
    for code in list(COLLECTORS)[1:]:
        provider=Mock()
        collector=COLLECTORS[code](provider,app.config)
        adapter=Mock(); adapter.fetch.return_value=SourceFetch(
            SourceDefinition('Cached','https://maroc.ma/index'),'https://maroc.ma/index','UNCHANGED')
        collector.source_adapters=[adapter]
        collector.collect(RADAR_AGENT_REGISTRY.resolve(code))
        provider.search.assert_not_called()


def test_production_low_cost_budget_is_preserved(app):
    from backend.app.core.collector_registry import build_collector
    config=dict(app.config,SEARCH_PROVIDER='openai',OPENAI_API_KEY='offline-placeholder')
    market=build_collector(CODE,config)
    assert market.config['RADAR1_DISCOVERY_MAX_CALLS']==2
    assert market.config['RADAR1_RESOLUTION_MAX_CALLS']==2
    assert [config[f'RADAR{n}_NORMAL_SEARCH_BUDGET'] for n in range(2,6)]==[2,1,1,2]


@pytest.mark.parametrize('code',['RADAR_1_MARKETS','RADAR_2_PROJECTS','RADAR_3_INSTITUTIONS','RADAR_4_POLICIES','RADAR_5_FUNDING'])
def test_five_unique_ids_per_page_for_each_team_queue(app,code):
    from backend.app.db.models import Radar
    review_rows(app,12)
    with app.app_context():
        radar_id=db.session.scalar(db.select(Radar.id).where(Radar.code==code))
        db.session.execute(db.update(Result).values(radar_id=radar_id)); db.session.commit()
    pages=[page(app,'pending',i,code=code)[0] for i in range(3)]
    assert [len(items) for items in pages]==[5,5,2]
    assert len({item['id'] for items in pages for item in items})==12
    assert pages[0]==page(app,'pending',0,code=code)[0]


@pytest.fixture(scope='module',autouse=True)
def save_final_evidence():
    yield
    Path('docs/historical/audits/production-acceptance.json').write_text(json.dumps(EVIDENCE,indent=2),encoding='utf-8')
