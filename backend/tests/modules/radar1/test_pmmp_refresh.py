"""Independent PMMP refresh: lease, PAGESTATE recovery, concurrent UPDATED, budgets."""
from datetime import timedelta

from app.db.extensions import db
from app.db.models import Radar, SearchRun, utcnow
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.db.models.pmmp_refresh_checkpoint import PmmpRefreshCheckpoint
from app.modules.radar1_markets.collector import MarketsCollector
from app.modules.radar1_markets.pmmp_listing_collector import NEW, UNCHANGED, UPDATED
from app.modules.radar1_markets.pmmp_listing_index import DurableListingIndex, import_baseline
from app.modules.radar1_markets.pmmp_refresh import (
    RefreshLeaseHeld, acquire_lease, ensure_checkpoint, refresh_status,
    release_expired_lease, run_refresh,
)
from app.modules.radar1_markets.processing import PENDING, PROCESSED, PROCESSING, REJECTED
from test_pmmp_listing_index import ScriptedHttp, listing, result_page


def _pages(items_per_page, *, declared=None, states=None):
    declared = declared or len(items_per_page)
    states = states or [f'p{i}' for i in range(1, len(items_per_page) + 1)]
    pages = []
    for index, items in enumerate(items_per_page):
        nxt = index < len(items_per_page) - 1
        pages.append(result_page(items, state=states[index], pages=declared, nxt=nxt))
    return pages


def test_lease_blocks_second_acquire(app):
    with app.app_context():
        ensure_checkpoint()
        owner = acquire_lease()
        assert owner
        assert acquire_lease() is None
        status = refresh_status()
        assert status['lease_held'] is True
        assert status['lease_owner'] == owner


def test_expired_lease_can_be_reclaimed_not_by_start_age(app):
    with app.app_context():
        ensure_checkpoint()
        owner = acquire_lease()
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        # Started long ago but lease+heartbeat still valid → must not reclaim.
        row.last_started_at = utcnow() - timedelta(hours=5)
        row.lease_until = utcnow() + timedelta(minutes=2)
        row.heartbeat_at = utcnow()
        db.session.commit()
        assert acquire_lease() is None
        # Expire lease and heartbeat → reclaim allowed.
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        row.lease_until = utcnow() - timedelta(seconds=1)
        row.heartbeat_at = utcnow() - timedelta(minutes=10)
        db.session.commit()
        assert acquire_lease() is not None
        assert release_expired_lease() is False  # already taken / running with fresh lease


def test_force_release_expired_only(app):
    with app.app_context():
        ensure_checkpoint()
        acquire_lease()
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        row.lease_until = utcnow() + timedelta(minutes=5)
        row.heartbeat_at = utcnow()
        db.session.commit()
        assert release_expired_lease() is False
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        row.lease_until = utcnow() - timedelta(seconds=1)
        row.heartbeat_at = utcnow() - timedelta(minutes=10)
        db.session.commit()
        assert release_expired_lease() is True
        assert db.session.get(PmmpRefreshCheckpoint, 1).status == 'idle'


def test_unchanged_processed_not_requeued(app):
    with app.app_context():
        import_baseline([listing()])
        row = db.session.scalar(db.select(PmmpListingIndex))
        row.processing_state = PROCESSED
        row.evaluated_fingerprint = row.fingerprint
        row.policy_version = 'archeritage-r11'
        db.session.commit()
        http = ScriptedHttp(_pages([[listing()]], declared=1))
        result = run_refresh(http=http, front_pages=1, deep_pages=0, delay_seconds=0)
        assert result.pass_success
        db.session.refresh(row)
        assert row.processing_state == PROCESSED
        assert result.unchanged >= 1


def test_pending_preserved_and_new_queued(app):
    with app.app_context():
        import_baseline([listing()])
        pending = db.session.scalar(db.select(PmmpListingIndex))
        pending.processing_state = PENDING
        db.session.commit()
        fresh = listing(consultation_id='9990001', organization='zzz', reference='99/2026',
                        title='Nouvelle notice patrimoine', buyer='Commune',
                        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                                    'page=entreprise.EntrepriseDetailsConsultation'
                                    '&refConsultation=9990001&orgAcronyme=zzz'))
        http = ScriptedHttp(_pages([[fresh, listing()]], declared=1))
        result = run_refresh(http=http, front_pages=1, deep_pages=0, delay_seconds=0)
        assert result.new == 1
        db.session.refresh(pending)
        assert pending.processing_state == PENDING
        created = db.session.scalar(db.select(PmmpListingIndex).where(
            PmmpListingIndex.consultation_id == '9990001'))
        assert created.processing_state == PENDING


def test_updated_idle_requeues_active_processing_keeps_owner(app):
    with app.app_context():
        import_baseline([listing()])
        row = db.session.scalar(db.select(PmmpListingIndex))
        radar = db.session.scalar(db.select(Radar).where(Radar.code == 'RADAR_1_MARKETS'))
        run = SearchRun(radar_id=radar.id, status='running', agent_name='MarketsRadarAgent')
        db.session.add(run)
        db.session.flush()
        row.processing_state = PROCESSING
        row.processing_run_id = run.id
        row.processing_started_at = utcnow()
        db.session.commit()
        index = DurableListingIndex()
        assert index.classify(listing(deadline='15/11/2026 18:00')) == UPDATED
        db.session.refresh(row)
        assert row.processing_state == PROCESSING
        assert row.processing_run_id == run.id
        assert row.processing_reason == 'listing_changed_while_processing'
        # Idle row requeues.
        row.processing_state = REJECTED
        row.processing_run_id = None
        row.fingerprint = listing().fingerprint
        db.session.commit()
        assert index.classify(listing(deadline='20/11/2026 18:00')) == UPDATED
        db.session.refresh(row)
        assert row.processing_state == PENDING


def test_deep_resume_across_passes_and_pass_vs_cycle(app):
    with app.app_context():
        known = listing()
        import_baseline([known])
        p1 = listing(consultation_id='10', organization='aaa', reference='10/2026',
                     title='Page1', buyer='A', detail_url=None)
        p2 = listing(consultation_id='11', organization='bbb', reference='11/2026',
                     title='Page2', buyer='B', detail_url=None)
        p3 = listing(consultation_id='12', organization='ccc', reference='12/2026',
                     title='Page3', buyer='C', detail_url=None)
        # Pass 1: front 0, deep 2 of 3
        http = ScriptedHttp(_pages([[p1], [p2], [p3]], declared=3, states=['s1', 's2', 's3']))
        first = run_refresh(http=http, front_pages=0, deep_pages=2, delay_seconds=0)
        assert first.pass_success
        assert first.cycle_complete is False
        assert first.deep_pages == 2
        assert db.session.get(PmmpRefreshCheckpoint, 1).cursor_page == 2
        # Pass 2: resume deep for remaining page
        http2 = ScriptedHttp([
            result_page([p3], state='s3', pages=3, nxt=False),
        ])
        # Seed soft PAGESTATE from checkpoint; collector try_resume posts next from s2.
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        row.page_state = 's2'
        db.session.commit()
        second = run_refresh(http=http2, front_pages=0, deep_pages=2, delay_seconds=0)
        assert second.pass_success
        assert second.cycle_complete is True
        assert refresh_status()['cycle_complete'] is True
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 4


def test_invalid_pagestate_renavigates_without_skipping(app):
    with app.app_context():
        ensure_checkpoint()
        rows = [
            listing(consultation_id=str(100 + i), organization='aaa', reference=f'{i}/2026',
                    title=f'T{i}', buyer='B', detail_url=None)
            for i in range(4)
        ]
        import_baseline(rows[:2])
        checkpoint = db.session.get(PmmpRefreshCheckpoint, 1)
        checkpoint.cursor_page = 2
        checkpoint.page_state = 'expired-token'
        checkpoint.cycle_complete = False
        db.session.commit()
        # Invalid resume HTML, then renavigate pages 1..2 and classify page 3 only.
        http = ScriptedHttp(
            ['<html>not a result</html>']
            + _pages([[rows[0]], [rows[1]], [rows[2]], [rows[3]]],
                     declared=4, states=['a', 'b', 'c', 'd'])
        )
        result = run_refresh(http=http, front_pages=0, deep_pages=1, delay_seconds=0)
        assert result.pass_success
        assert result.cycle_complete is False
        assert result.new >= 1
        assert db.session.get(PmmpRefreshCheckpoint, 1).cursor_page == 3


def test_business_collect_does_not_refresh(app, monkeypatch):
    with app.app_context():
        from unittest.mock import Mock
        import_baseline([listing()])
        called = []

        def boom(*args, **kwargs):
            called.append(True)
            raise AssertionError('refresh must not run')

        monkeypatch.setattr('app.modules.radar1_markets.pmmp_listing_index.sync_listings', boom)
        monkeypatch.setattr('app.modules.radar1_markets.pmmp_refresh.run_refresh', boom)
        collector = MarketsCollector(Mock(), app.config)
        collector.config = {**collector.config, 'RADAR1_DISCOVERY_MODE': 'pmmp_index',
                            'RADAR1_PROCESSING_BATCH_SIZE': 1,
                            'RADAR1_PROCESSING_MAX_SECONDS': 30}
        from types import SimpleNamespace
        radar = SimpleNamespace(code='RADAR_1_MARKETS', id=1)
        collector.pmmp_index_discovery(radar)
        assert collector.report.metrics['pmmp_sync_mode'] == 'not_requested'
        assert collector.report.metrics['pmmp_discovery_strategy'] == 'indexed_title_batch'
        assert called == []


def test_http_bounded_by_front_budget(app):
    with app.app_context():
        items = [
            listing(consultation_id=str(200 + i), organization='x', reference=f'{i}/x',
                    title=f'N{i}', buyer='B', detail_url=None)
            for i in range(6)
        ]
        http = ScriptedHttp(_pages([[x] for x in items], declared=6))
        result = run_refresh(http=http, front_pages=2, deep_pages=0, delay_seconds=0)
        assert result.front_pages == 2
        assert result.pages == 2
        # One GET-equivalent per page via ScriptedHttp pop; 2 pages consumed (+ maybe form)
        assert len(http.calls) <= 3
        assert result.cycle_complete is False
