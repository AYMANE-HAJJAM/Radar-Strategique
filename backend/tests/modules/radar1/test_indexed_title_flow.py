"""Offline experiment corpus and isolated SQLite end-to-end regressions."""
import json
from pathlib import Path
from datetime import timedelta
from unittest.mock import Mock

import pytest

from app.core.orchestrator import AgentOrchestrator
from app.core.agent_errors import ActiveRunError
from app.db.extensions import db
from app.db.models import SearchRun, Result, utcnow
from app.modules.radar1_markets import processing as queue
from app.modules.radar1_markets.title_filter import select_title
from test_processing_reliability import notice, seed, configure, Pages, Listing, CODE, count


CORPUS = json.loads((Path(__file__).parents[2] / 'fixtures/pmmp_title_shortlist.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('row', CORPUS, ids=lambda row: row['reference'])
def test_experiment_shortlist_is_not_silently_lost(row):
    assert select_title(row['full_title_stored'], row['procedure'], row['category'])['decision'] == 'continue'


@pytest.mark.parametrize('title,procedure', [
    ('Études architecturales de construction du lycée à la médina', 'Concours architectural'),
    ('Études et suivi de construction du bâtiment OFPPT', 'Concours architectural'),
    ('Études techniques de voirie et assainissement', ''),
    ('Travaux de restauration des remparts', ''),
    ('Travaux de restauration des remparts ...', ''),
    ('Travaux de réhabilitation du musée', ''),
    ('Maintenance informatique du patrimoine foncier', ''),
    ('Sauvegarde des données et logiciels', ''),
    ('Sauvegarde des données ...', ''),
    ('Études topographiques de lotissement', ''),
    ('Études topographiques de lotissement ...', ''),
    ('Études de logements de fonction', ''),
    ('أشغال ترميم الاسوار', ''),
    ('دراسة بناء مدرسة', ''),
])
def test_clear_noise_rejected(title, procedure):
    assert select_title(title, procedure)['decision'] == 'reject'


@pytest.mark.parametrize('title', [
    'Études et suivi des travaux de restauration des remparts',
    'Études et suivi de restauration ...',
    'Consultation PMMP',
    'دراسة تقنية وتتبع أشغال مشروع تأهيل لقصر حنابو',
])
def test_services_and_incomplete_objects_reach_official_detail(title):
    assert select_title(title)['decision'] == 'continue'


def test_null_unchanged_listing_and_truncated_title_use_full_official_object(app, monkeypatch):
    indexed = notice(title='Études techniques et suivi ...')
    official = notice()
    seed(app, [indexed])
    with app.app_context():
        assert db.engine.dialect.name == 'sqlite'
        row = db.session.scalar(db.select(Listing)); row.processing_state = None; db.session.commit()
    created = configure(app, monkeypatch, [official])
    monkeypatch.setattr('app.modules.radar1_markets.pmmp_listing_index.sync_listings', Mock(side_effect=AssertionError('No crawl')))
    monkeypatch.setattr(queue, 'recover_legacy', Mock(side_effect=AssertionError('No recovery scan')))
    monkeypatch.setattr(queue, 'queue_reconciliation_refresh', Mock(side_effect=AssertionError('No reconciliation')))
    # Force the paid-analysis configuration on: index mode still uses the policy.
    app.config['RADAR1_AI_ENABLED'] = 'true'
    run = AgentOrchestrator(app, analyzer=Mock(side_effect=AssertionError('No AI'))).run_radar(CODE)
    assert run.status == 'completed'
    with app.app_context():
        saved = db.session.scalar(db.select(Result))
        assert saved.title == official.title
        progress = db.session.get(SearchRun, run.id).run_metadata['collector_metrics']['radar1_progress']
        assert (progress['indexed'], progress['selected'], progress['processed'], progress['relevant'], progress['pending']) == (1, 1, 1, 1, 0)
        assert db.session.get(SearchRun, run.id).ai_calls == 0
    created[-1].provider.search.assert_not_called()


@pytest.mark.parametrize('failure', ['missing_deadline', 'incomplete_object', 'mismatch', 'http'])
def test_official_failure_remains_retryable_and_resumes(app, monkeypatch, failure):
    indexed = notice()
    seed(app, [indexed])
    official = notice(deadline='' if failure == 'missing_deadline' else indexed.deadline,
                      title='Études et suivi ...' if failure == 'incomplete_object' else indexed.title,
                      reference='WRONG/2026' if failure == 'mismatch' else indexed.reference)
    configure(app, monkeypatch, [official], fail=failure == 'http')
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert count(Result) == 0
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.RETRY
    configure(app, monkeypatch, [indexed])
    assert AgentOrchestrator(app, no_ai=True).run_radar(CODE).status == 'completed'
    with app.app_context():
        assert count(Result) == 1
        assert db.session.scalar(db.select(Listing.processing_state)) == queue.PROCESSED


def test_arabic_heritage_service_reaches_visible_business_result(app, monkeypatch):
    rows = [notice(title='دراسة تقنية وتتبع أشغال مشروع تأهيل لقصر حنابو، إقليم الرشيدية', buyer='وكالة حماية التراث')]
    seed(app, rows); configure(app, monkeypatch, rows)
    run = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    assert run.status == 'completed'
    with app.app_context():
        assert count(Result) == 1
        assert db.session.scalar(db.select(Result.title)) == rows[0].title


def test_arabic_policy_normalization_preserves_identity_and_is_idempotent():
    from app.modules.radar1_markets.policy import folded
    text = folded('دراسة تقنية وتتبع أشغال تأهيل لقصر حنابو')
    assert 'حنابو' in text
    assert 'suivi' in text and 'ksar' in text
    assert folded(text) == text
    assert folded('المشتري العمومي') != ''


def test_arabic_buyer_must_literally_occur_on_official_page(app):
    from app.modules.radar1_markets.collector import MarketsCollector, listing_to_search_hit
    from app.integrations.pmmp.parser import enrich_detail, verify_detail
    row = notice(buyer='وكالة حماية التراث')
    pages = Pages([row])
    collector = MarketsCollector(Mock(), app.config, pages=pages)
    candidate = enrich_detail(collector._normalize(listing_to_search_hit(row), row.detail_url), pages)
    assert verify_detail(candidate, pages).detail_verified
    with pytest.raises(ValueError, match='identity/buyer/deadline'):
        verify_detail(candidate.model_copy(update={'institution': 'مؤسسة أخرى'}), pages)


def test_old_active_radar1_is_never_recovered_by_age(app):
    worker = AgentOrchestrator(app, no_ai=True)
    run_id = worker.reserve(CODE)
    with app.app_context():
        run = db.session.get(SearchRun, run_id); run.started_at = utcnow() - timedelta(days=2)
        db.session.commit()
    with pytest.raises(ActiveRunError):
        worker.reserve(CODE)
    with app.app_context():
        assert db.session.get(SearchRun, run_id).status == 'initialized'
        assert db.session.get(SearchRun, run_id).error_kind is None


def test_progress_is_committed_during_collection_and_budget_leaves_work(app, monkeypatch):
    rows = [notice(1), notice(2)]
    seed(app, rows); configure(app, monkeypatch, rows)
    snapshots = []
    record = AgentOrchestrator._record_collection
    def capture(self, run, report):
        record(self, run, report)
        raw = db.session.execute(db.text('SELECT run_metadata FROM search_runs WHERE id=:id'), {'id': run.id}).scalar_one()
        snapshots.append(json.loads(raw)['collector_metrics']['radar1_progress'].copy())
    monkeypatch.setattr(AgentOrchestrator, '_record_collection', capture)
    clock = iter([0, 0, 121])
    monkeypatch.setattr('app.modules.radar1_markets.collector.monotonic', lambda: next(clock))
    # Injected pages need no real timing or HTTP. Admissions exhaust the budget
    # after one candidate; the unclaimed second row must survive another launch.
    run = AgentOrchestrator(app, no_ai=True).run_radar(CODE)
    assert run.status == 'completed'
    assert any(s['processed'] == 0 and s['last_listing_id'] is not None for s in snapshots)
    assert any(s['processed'] == 1 for s in snapshots)
    with app.app_context():
        assert count(Result) == 1
        assert db.session.get(SearchRun, run.id).run_metadata['collector_metrics']['radar1_progress']['pending'] == 1


def test_slow_stream_is_bounded_without_retry_loop(monkeypatch):
    from app.integrations.http.html import PublicPages
    elapsed = [0]
    response = Mock()
    response.headers.get.return_value = 'text/html'
    def trickle(size):
        elapsed[0] += 11
        return b'<p>stream'
    response.read1.side_effect = trickle
    context = Mock()
    context.__enter__ = Mock(return_value=response)
    context.__exit__ = Mock(return_value=False)
    opener = Mock(); opener.open.return_value = context
    monkeypatch.setattr('app.integrations.http.html.build_opener', lambda *args: opener)
    monkeypatch.setattr('app.integrations.http.html.monotonic', lambda: elapsed[0])
    pages = PublicPages(('marchespublics.gov.ma',), elapsed_limit=20)
    with pytest.raises(TimeoutError):
        pages.get(notice().detail_url)
    assert response.read1.call_count == 2
    assert opener.open.call_count == 1
    assert not pages.cache
