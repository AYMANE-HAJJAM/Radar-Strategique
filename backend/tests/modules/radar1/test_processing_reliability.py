"""All notices/runs here are synthetic; source databases and network are forbidden."""
from dataclasses import asdict
from datetime import timedelta
import json
from unittest.mock import Mock

import pytest

from app.core.orchestrator import AgentOrchestrator
from app.core.validation import today_in_morocco
from app.db.extensions import db
from app.db.models import Radar, Result, ResultObservation, SearchRun
from app.db.models.pmmp_listing_index import PmmpListingIndex as Listing
from app.modules.radar1_markets.collector import MarketsCollector, listing_to_search_hit
from app.modules.radar1_markets.pmmp_listing_index import import_baseline, sync_listings
from app.modules.radar1_markets.preview import preview, source_snapshot
from app.modules.radar1_markets import processing as queue
from test_pmmp_listing_index import listing, result_page, ScriptedHttp

CODE = 'RADAR_1_MARKETS'


def notice(number=1, **changes):
    values = dict(consultation_id=str(number), organization='aaa', reference=f'FIXTURE-{number}/2026',
                  title=f'Etude architecturale de restauration et valorisation du patrimoine de la medina secteur {number}',
                  buyer='Agence du patrimoine', category='Services', location='FES',
                  publication_date=today_in_morocco().strftime('%d/%m/%Y'),
                  deadline=(today_in_morocco() + timedelta(days=30)).strftime('%d/%m/%Y') + ' 11:00',
                  detail_url='https://www.marchespublics.gov.ma/index.php?'
                             f'page=entreprise.EntrepriseDetailsConsultation&refConsultation={number}&orgAcronyme=aaa')
    values.update(changes)
    return listing(**values)


def detail(row):
    fields = {'Reference': row.reference, 'Objet': row.title, 'Acheteur public': row.buyer,
              'Date limite de remise des plis': row.deadline,
              'Date de publication': row.publication_date, "Lieu d'execution": row.location,
              'Procedure': row.procedure, 'Categorie principale': row.category}
    return '<h1>Consultation</h1><dl>' + ''.join(
        f'<dt>{key} :</dt><dd>{value}</dd>' for key, value in fields.items()) + '</dl>'


class Pages:
    def __init__(self, rows, fail=False):
        from app.integrations.http.html import Page
        self.pages = {row.detail_url: Page(detail(row)) for row in rows}
        self.fail = fail

    def get(self, url):
        if self.fail:
            raise OSError('fixture unavailable')
        return url, self.pages[url]


def configure(app, monkeypatch, rows, *, pages=None, fail=False):
    app.config.update(RADAR1_DISCOVERY_MODE='pmmp_index', RADAR1_DISCOVERY_MAX_CALLS=0,
                      RADAR1_RESOLUTION_MAX_CALLS=0, RADAR1_AI_ENABLED='false')
    created = []
    def build(code, config):
        provider = Mock()
        provider.search.side_effect = AssertionError('No paid calls in fixture tests')
        collector = MarketsCollector(provider, config, pages=Pages(rows, fail=fail))
        collector.listing_http = ScriptedHttp(pages or [result_page(rows, state='fixture', pages=1)])
        created.append(collector)
        original_collect = collector.collect
        def collect_with_cause(radar):
            try:
                return original_collect(radar)
            except Exception as error:
                collector.fixture_error = repr(error)
                raise AssertionError(f'Fixture collector cause: {type(error).__name__}: {error}') from error
        collector.collect = collect_with_cause
        return collector
    monkeypatch.setattr('app.core.orchestrator.build_collector', build)
    return created


def seed(app, rows):
    with app.app_context():
        import_baseline(rows)


def count(model):
    return db.session.scalar(db.select(db.func.count()).select_from(model))


def test_unchanged_unprocessed_is_persisted_once_on_repeated_launches(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    created = configure(app, monkeypatch, rows)
    first = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    assert first.status == 'completed', getattr(created[-1], 'fixture_error', '')
    with app.app_context():
        row = db.session.scalar(db.select(Listing))
        assert row.processing_state == queue.PROCESSED
        assert row.evaluated_fingerprint == row.fingerprint
        assert count(Result) == 1
        assert count(ResultObservation) == 1
    second = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    assert second.status == 'completed'
    assert created[-1].report.metrics['pmmp_sync_unchanged'] == 1
    assert created[-1].report.metrics['pmmp_evaluated'] == 0
    with app.app_context():
        assert count(Result) == 1
        assert count(ResultObservation) == 1


def test_processing_cap_leaves_overflow_pending_and_resumes(app, monkeypatch):
    rows = [notice(i) for i in range(1, 4)]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    app.config['RADAR1_MAX_CANDIDATES'] = 1
    for expected in (1, 2, 3):
        run = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
        assert run.status == 'completed'
        with app.app_context():
            assert count(Result) == expected
            states = db.session.scalars(db.select(Listing.processing_state)).all()
            assert states.count(queue.PROCESSED) == expected
            assert states.count(queue.PENDING) == 3 - expected


def test_failed_persistence_remains_retryable_then_succeeds(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    worker = AgentOrchestrator(app, no_ai=True)
    monkeypatch.setattr(worker.results, 'save', Mock(side_effect=RuntimeError('fixture interrupted save')))
    worker.run_radar(CODE)
    with app.app_context():
        assert count(Result) == 0
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.RETRY
    run = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    assert run.status == 'completed'
    with app.app_context():
        assert count(Result) == 1
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.PROCESSED


def test_run_interruption_after_collection_releases_claims(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    worker = AgentOrchestrator(app, no_ai=True)
    monkeypatch.setattr(worker, '_save', Mock(side_effect=RuntimeError('fixture interruption before persistence')))
    assert worker.run_radar(CODE).status == 'failed'
    with app.app_context():
        assert count(Result) == 0
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.RETRY
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert count(Result) == 1


def test_unavailable_official_detail_remains_retryable_then_persists_once(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    created = configure(app, monkeypatch, rows, fail=True)
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.RETRY
        assert count(Result) == 0, created[-1].report.trace
    configure(app, monkeypatch, rows)
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert count(Result) == 1
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.PROCESSED


def test_abandoned_claim_recovered_but_live_owner_not_stolen(app):
    seed(app, [notice(1), notice(2)])
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        old = SearchRun(radar_id=radar.id, status='running')
        db.session.add(old); db.session.commit()
        rows = db.session.scalars(db.select(Listing).order_by(Listing.id)).all()
        assert queue.claim(rows[0].id, rows[0].fingerprint, old.id)
        old.status = 'failed'; db.session.commit()
        live = SearchRun(radar_id=radar.id, status='running')
        db.session.add(live); db.session.commit()
        assert queue.claim(rows[1].id, rows[1].fingerprint, live.id)
        queue.release_abandoned()
        assert db.session.get(Listing, rows[0].id).processing_state == queue.RETRY
        assert db.session.get(Listing, rows[1].id).processing_state == queue.PROCESSING


def test_partial_sync_keeps_discovered_work_pending(app):
    seed(app, [notice(1)])
    class BrokenHttp(ScriptedHttp):
        def post(self, *args, **kwargs):
            raise OSError('fixture page two interruption')
    with app.app_context():
        with pytest.raises(OSError):
            sync_listings(http=BrokenHttp([result_page([notice(2)], state='p1', pages=2, nxt=True)]),
                          independent=True, commit=False, delay_seconds=0)
        db.session.rollback()
        rows = db.session.scalars(db.select(Listing).order_by(Listing.id)).all()
        assert len(rows) == 2
        assert all(row.processing_state == queue.PENDING for row in rows)
        assert count(Result) == 0


def test_old_worker_cannot_ack_new_fingerprint(app):
    seed(app, [notice()])
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        run = SearchRun(radar_id=radar.id, status='running')
        db.session.add(run); db.session.commit()
        row = db.session.scalar(db.select(Listing))
        old = row.fingerprint
        assert queue.claim(row.id, old, run.id)
        import_baseline([notice(deadline='31/12/2027 11:00')])
        assert not queue.finish(row.id, old, run.id, queue.PROCESSED, 'stale worker')
        assert row.processing_state == queue.PENDING


def test_legacy_recovery_uses_business_proof_and_prefilter(app, monkeypatch):
    rows = [notice(1)]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        import_baseline([notice(2), notice(3, title='Travaux de construction de route rurale', category='Travaux')])
        db.session.execute(db.update(Listing).values(processing_state=None))
        db.session.commit()
        collector = MarketsCollector(Mock(), app.config, pages=Pages(rows))
        stats = queue.recover_legacy(lambda row: collector._normalize(listing_to_search_hit(row), row.detail_url))
        assert stats == dict(restored=1, queued=1, rejected=1)
        assert count(Result) == 1
        # A proven persisted policy rejection restores REJECTED, not an acceptance.
        result = db.session.scalar(db.select(Result))
        result.analysis = {**result.analysis, 'relevant': False}
        result.review_status = 'REJECTED'
        restored = db.session.scalar(db.select(Listing).where(Listing.consultation_id == '1'))
        restored.processing_state = None
        db.session.commit()
        queue.recover_legacy(lambda row: collector._normalize(listing_to_search_hit(row), row.detail_url))
        assert restored.processing_state == queue.REJECTED
        assert result.review_status == 'REJECTED'


def test_approved_review_preserved_on_nonmaterial_reprocessing(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        result = db.session.scalar(db.select(Result))
        result.review_status = 'APPROVED'
        row = db.session.scalar(db.select(Listing)); row.processing_state = queue.PENDING
        db.session.commit()
    AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        assert count(Result) == 1
        assert db.session.scalar(db.select(Result.review_status)) == 'APPROVED'
        assert db.session.scalars(db.select(ResultObservation.state).order_by(ResultObservation.id)).all()[-1] == 'unchanged'


@pytest.mark.parametrize('mode', ['incremental', 'reconciliation'])
def test_deeper_notice_after_three_unchanged_pages_is_discovered(app, mode):
    known = [notice(i) for i in range(1, 4)]
    seed(app, known)
    pages = [result_page([row], state=str(i), pages=4, nxt=True) for i, row in enumerate(known)]
    pages.append(result_page([notice(4)], state='deep', pages=4))
    with app.app_context():
        sync = sync_listings(mode=mode, http=ScriptedHttp(pages), delay_seconds=0)
        assert sync.pages_fetched == 4
        assert sync.counts['NEW'] == 1
        assert count(Listing) == 4


def test_manual_review_run_membership_uses_observation_snapshot(app):
    from app.api.results import _actionable_states
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        run = SearchRun(radar_id=radar.id, status='completed')
        result = Result(radar_id=radar.id, title='fixture', fingerprint='fixture', review_status='PENDING')
        db.session.add_all([run, result]); db.session.flush()
        db.session.add(ResultObservation(run_id=run.id, result_id=result.id,
                                       state='manual_review', snapshot={'discovery_status': 'NEW'}))
        db.session.commit()
        assert _actionable_states(run.id, [result.id]) == {result.id: 'new'}
        db.session.add(ResultObservation(run_id=run.id, result_id=result.id,
                                       state='manual_review', snapshot={'discovery_status': 'UNCHANGED'}))
        db.session.commit()
        # Earlier actionable production still belongs to this run.
        assert _actionable_states(run.id, [result.id]) == {result.id: 'new'}


def test_manual_review_is_visible_in_authenticated_exact_run_web_view(app, monkeypatch):
    from test_api import make_user, login
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    run = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    _, access = make_user(app)
    client = app.test_client(); login(client, access)
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        result = db.session.scalar(db.select(Result))
        assert db.session.scalar(db.select(ResultObservation.state)) == 'manual_review'
        path = f'/api/radars/{radar.id}/results?status=pending&run_id={run.id}'
        response = client.get(path)
        assert response.status_code == 200
        assert response.get_json()['total'] == 1
        result.review_status = 'APPROVED'; db.session.commit()
        assert client.get(path).get_json()['total'] == 0
        assert client.get(f'/api/radars/{radar.id}/results?status=approved').get_json()['total'] == 1


def test_preview_fixture_and_database_have_no_source_writes(app, monkeypatch, tmp_path):
    from sqlalchemy import event
    from app.modules.radar1_markets.feedback import get_feedback_service
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        before = source_snapshot()
        feedback_profile = get_feedback_service()._profile
        statements = []
        def capture(conn, cursor, statement, *args):
            statements.append(statement)
        event.listen(db.engine, 'before_cursor_execute', capture)
        try:
            output = preview(dict(app.config), snapshot=source_snapshot())
            assert output['mode'] == 'database_snapshot_offline_prediction'
            fixture = dict(listings=[asdict(notice(8))], detail_pages={notice(8).detail_url: detail(notice(8))})
            path = tmp_path / 'fixture.json'; path.write_text(json.dumps(fixture), encoding='utf-8')
            response = app.test_cli_runner().invoke(args=['radar1-preview', '--fixture', str(path)])
            assert response.exit_code == 0, response.output
            result = json.loads(response.output)
            assert result['accepted_or_review'] == 1
            assert result['search_runs_created'] == 0
            assert result['paid_calls'] == 0
            assert source_snapshot() == before
            assert get_feedback_service()._profile is feedback_profile
            assert not any(s.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER')) for s in statements)
        finally:
            event.remove(db.engine, 'before_cursor_execute', capture)


def test_runtime_mode_and_strategy_reported(app, monkeypatch):
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    result = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        run = db.session.get(SearchRun, result.id)
        metrics = run.run_metadata['collector_metrics']
        assert metrics['discovery_mode'] == 'pmmp_index'
        assert metrics['pmmp_sync_mode'] == 'reconciliation'
        assert metrics['pmmp_sync_complete'] is True
        assert metrics['pmmp_discovery_strategy'] == 'complete_board_comparison'
        assert metrics['pmmp_index_size_before'] == metrics['pmmp_index_size_after'] == 1
        assert metrics['pmmp_evaluated'] == 1


def test_expired_backlog_does_not_consume_active_processing_cap(app, monkeypatch):
    rows = [notice(1, deadline=(today_in_morocco() - timedelta(days=1)).strftime('%d/%m/%Y')),
            notice(2)]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    app.config['RADAR1_MAX_CANDIDATES'] = 1
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert db.session.scalars(db.select(Listing.processing_state).order_by(Listing.id)).all() == [queue.REJECTED, queue.PROCESSED]
        assert count(Result) == 1
        assert db.session.scalar(db.select(Result.reference)) == notice(2).reference


def test_periodic_reconciliation_refresh_preserves_approved_decision(app, monkeypatch):
    from app.db.models import utcnow
    rows = [notice()]
    seed(app, rows)
    created = configure(app, monkeypatch, rows)
    first = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        row = db.session.scalar(db.select(Listing))
        row.evaluated_at = utcnow() - timedelta(days=2)
        result = db.session.scalar(db.select(Result)); result.review_status = 'APPROVED'
        run = db.session.get(SearchRun, first.id)
        run.started_at = run.finished_at = utcnow() - timedelta(days=2)
        db.session.commit()
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    assert created[-1].report.metrics['pmmp_reconciliation_refresh_queued'] == 1
    assert created[-1].report.metrics['pmmp_evaluated'] == 1
    with app.app_context():
        assert db.session.scalar(db.select(Result.review_status)) == 'APPROVED'
        assert count(Result) == 1
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.PROCESSED


def test_older_business_save_cannot_certify_a_later_legacy_index_version(app, monkeypatch):
    from app.db.models import utcnow
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    with app.app_context():
        row = db.session.scalar(db.select(Listing))
        row.processing_state = None
        row.last_changed_at = utcnow() + timedelta(minutes=1)
        db.session.commit()
        collector = MarketsCollector(Mock(), app.config, pages=Pages(rows))
        result = queue.recover_legacy(lambda listing: collector._normalize(
            listing_to_search_hit(listing), listing.detail_url))
        assert result['queued'] == 1
        assert result['restored'] == 0
        assert count(Result) == 1


def test_preview_cap_predictions_leave_source_queue_untouched(app):
    rows = [notice(i) for i in range(1, 4)]
    seed(app, rows)
    with app.app_context():
        before = source_snapshot()
        fixture = dict(listings=[asdict(row) for row in rows],
                       detail_pages={row.detail_url: detail(row) for row in rows})
        output = preview(dict(app.config), fixture=fixture, limit=1)
        assert output['queued'] == 3
        assert output['evaluated'] == 1
        assert output['accepted_or_review'] == 1
        assert output['queued_after_cap_prediction'] == 2
        assert source_snapshot() == before
        assert count(SearchRun) == 0
        assert count(Result) == 0
        assert db.session.scalars(db.select(Listing.processing_state)).all() == [queue.PENDING] * 3


def test_dashboard_pending_count_matches_visible_radar1_queue(app, monkeypatch):
    from test_api import make_user, login
    rows = [notice()]
    seed(app, rows)
    configure(app, monkeypatch, rows)
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        radar_id = radar.id
        db.session.add(Result(radar_id=radar_id, title='Travaux de construction de route rurale',
                              fingerprint='fixture-noise', review_status='PENDING', discovery_status='NEW'))
        db.session.commit()
        assert count(Result) == 2
    _, access = make_user(app)
    client = app.test_client(); login(client, access)
    visible = client.get(f'/api/radars/{radar_id}/results?status=pending').get_json()['total']
    dashboard = next(row for row in client.get('/api/radars').get_json()['items'] if row['id'] == radar_id)
    assert dashboard['pending_count'] == visible == 1
