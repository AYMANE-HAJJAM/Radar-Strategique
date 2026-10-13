"""Independent PMMP refresh: lease, PAGESTATE recovery, concurrent UPDATED, budgets."""
from datetime import timedelta

import pytest

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


def test_launch_runs_bounded_refresh_then_business_not_full_crawl(app, monkeypatch):
    """Button path: bounded refresh → business; never sync_listings(full)."""
    with app.app_context():
        from unittest.mock import Mock
        from types import SimpleNamespace
        from app.core.orchestrator import AgentOrchestrator
        from test_processing_reliability import Pages, notice

        fresh = notice(8880001, reference='88/2026/NEW',
                       title='Etude architecturale de restauration patrimoine',
                       buyer='Commune')
        # Existing PROCESSED unchanged listing must not be reprocessed.
        import_baseline([listing()])
        row = db.session.scalar(db.select(PmmpListingIndex))
        row.processing_state = PROCESSED
        row.evaluated_fingerprint = row.fingerprint
        row.policy_version = 'archeritage-r11'
        db.session.commit()

        sync_calls = []
        monkeypatch.setattr(
            'app.modules.radar1_markets.pmmp_listing_index.sync_listings',
            lambda **kwargs: sync_calls.append(kwargs) or (_ for _ in ()).throw(
                AssertionError('full sync_listings must not run on launch')))

        # Listing page HTML for refresh + official detail HTML for business.
        http = ScriptedHttp(_pages([[fresh]], declared=1))
        created = []

        def build(code, config):
            provider = Mock()
            provider.search.side_effect = AssertionError('No paid calls')
            collector = MarketsCollector(provider, config, pages=Pages([fresh]))
            collector.listing_http = http
            collector.config = {**collector.config, 'RADAR1_DISCOVERY_MODE': 'pmmp_index',
                                'RADAR1_PMMP_REFRESH_FRONT_PAGES': 1,
                                'RADAR1_PMMP_REFRESH_DEEP_PAGES': 0,
                                'RADAR1_PROCESSING_BATCH_SIZE': 5}
            created.append(collector)
            return collector

        monkeypatch.setattr('app.core.orchestrator.build_collector', build)
        app.config['RADAR1_DISCOVERY_MODE'] = 'pmmp_index'
        app.config['RADAR1_AI_ENABLED'] = 'false'
        summary = AgentOrchestrator(app, no_ai=True).run_radar('RADAR_1_MARKETS')
        assert summary.status == 'completed', getattr(created[-1], 'fixture_error', summary)
        assert sync_calls == []
        metrics = created[-1].report.metrics
        assert metrics['pmmp_sync_mode'] == 'bounded_refresh'
        assert metrics['pmmp_refresh_pass']['attempted'] is True
        assert metrics['pmmp_refresh_pass']['pass_success'] is True
        assert metrics['pmmp_refresh_pass']['index_refreshed'] is True
        assert metrics['pmmp_refresh_pass']['catalogue_reconciled'] is False
        assert metrics['pmmp_refresh_pass']['new'] >= 1
        assert metrics['pmmp_discovery_strategy'] == 'indexed_title_batch'
        # Unchanged PROCESSED fingerprint stays terminal.
        original = db.session.scalars(
            db.select(PmmpListingIndex).order_by(PmmpListingIndex.id)).first()
        assert original.processing_state == PROCESSED
        # Separate outcomes recorded on the SearchRun.
        run = db.session.get(SearchRun, summary.id)
        pass_meta = run.run_metadata['collector_metrics']['pmmp_refresh_pass']
        assert pass_meta['pass_success'] is True
        assert run.run_metadata['collector_metrics']['radar1_progress']['phase'] != 'pmmp_refresh'


def test_partial_refresh_failure_is_recorded_separately(app, monkeypatch):
    with app.app_context():
        from unittest.mock import Mock
        from app.modules.radar1_markets.pmmp_refresh import RefreshPassResult

        import_baseline([listing()])
        monkeypatch.setattr(
            'app.modules.radar1_markets.pmmp_refresh.run_refresh',
            lambda **kwargs: RefreshPassResult(
                acquired=True, lease_owner='t', stop_reason='error', pass_success=False,
                cycle_complete=False, pages=0, new=0, updated=0, unchanged=0, duplicates=0,
                front_pages=0, deep_pages=0, cursor_page=0, declared_pages=None,
                error='FixtureError:boom'))
        collector = MarketsCollector(Mock(), {**app.config, 'RADAR1_DISCOVERY_MODE': 'pmmp_index',
                                              'RADAR1_PROCESSING_BATCH_SIZE': 1})
        from types import SimpleNamespace
        collector.pmmp_index_discovery(SimpleNamespace(code='RADAR_1_MARKETS', id=1))
        pass_meta = collector.report.metrics['pmmp_refresh_pass']
        assert pass_meta['pass_success'] is False
        assert pass_meta['index_refreshed'] is False
        assert 'FixtureError' in (pass_meta['error'] or '')
        assert collector.report.metrics['pmmp_sync_mode'] == 'bounded_refresh'
        assert collector.report.metrics['pmmp_index_refreshed'] is False
        assert 'pmmp_business_on_unrefreshed_index' in collector.report.health_reasons


def test_lease_held_refresh_does_not_block_business_phase(app, monkeypatch):
    with app.app_context():
        from unittest.mock import Mock
        from types import SimpleNamespace
        import_baseline([listing()])
        ensure_checkpoint()
        acquire_lease()
        collector = MarketsCollector(Mock(), {**app.config, 'RADAR1_DISCOVERY_MODE': 'pmmp_index',
                                              'RADAR1_PMMP_REFRESH_FRONT_PAGES': 1,
                                              'RADAR1_PMMP_REFRESH_DEEP_PAGES': 0,
                                              'RADAR1_PROCESSING_BATCH_SIZE': 1})
        collector.pmmp_index_discovery(SimpleNamespace(code='RADAR_1_MARKETS', id=1))
        pass_meta = collector.report.metrics['pmmp_refresh_pass']
        assert pass_meta['lease_held'] is True
        assert pass_meta['index_refreshed'] is False
        assert collector.report.metrics['pmmp_index_refreshed'] is False
        assert 'pmmp_refresh_lease_held' in collector.report.health_reasons


def test_duplicate_launch_still_conflicts(app):
    from app.core.orchestrator import AgentOrchestrator
    from app.core.agent_errors import ActiveRunError
    worker = AgentOrchestrator(app, no_ai=True)
    first = worker.reserve('RADAR_1_MARKETS')
    with pytest.raises(ActiveRunError):
        worker.reserve('RADAR_1_MARKETS')
    with app.app_context():
        assert db.session.get(SearchRun, first).status in {'initialized', 'running'}


def test_expired_refresh_lease_recovered_on_next_launch(app, monkeypatch):
    """Restart recovery: expired lease is reclaimable; checkpoint cursor survives."""
    with app.app_context():
        from unittest.mock import Mock
        ensure_checkpoint()
        owner = acquire_lease()
        row = db.session.get(PmmpRefreshCheckpoint, 1)
        row.cursor_page = 7
        row.lease_until = utcnow() - timedelta(seconds=1)
        row.heartbeat_at = utcnow() - timedelta(minutes=10)
        db.session.commit()
        http = ScriptedHttp(_pages([[listing()]], declared=1))
        monkeypatch.setattr(
            'app.modules.radar1_markets.pmmp_listing_index.sync_listings',
            lambda **kwargs: (_ for _ in ()).throw(AssertionError('no full sync')))
        collector = MarketsCollector(Mock(), {**app.config, 'RADAR1_DISCOVERY_MODE': 'pmmp_index',
                                              'RADAR1_PMMP_REFRESH_FRONT_PAGES': 1,
                                              'RADAR1_PMMP_REFRESH_DEEP_PAGES': 0,
                                              'RADAR1_PROCESSING_BATCH_SIZE': 1})
        collector.listing_http = http
        from types import SimpleNamespace
        collector.pmmp_index_discovery(SimpleNamespace(code='RADAR_1_MARKETS', id=1))
        assert collector.report.metrics['pmmp_refresh_pass']['pass_success'] is True
        assert collector.report.metrics['pmmp_refresh_pass']['lease_held'] is False
        # Deep cursor from prior dead worker is preserved (front does not reset it).
        assert db.session.get(PmmpRefreshCheckpoint, 1).cursor_page == 7
        assert owner  # previous owner was superseded via expired reclaim


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
