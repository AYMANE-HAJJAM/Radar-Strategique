from datetime import timedelta
from unittest.mock import Mock

from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.validation import today_in_morocco
from backend.app.db.extensions import db
from backend.app.db.models import Result, ResultAuditEvent
from backend.app.core.review import page, decide, run_page
from backend.app.core.review import DiscoveryStatus, ReviewStatus
from backend.app.bot.routing import parse_callback
from backend.scripts.test_agent import MockAnalyzer
from test_agent import candidate
from test_phase3 import CODE, execute


def one(app, **changes):
    execute(app, [candidate(**changes)])
    with app.app_context():
        return db.session.scalar(db.select(Result).where(Result.title == changes.get('title', candidate().title))).id


def test_new_actionable_result_enters_pending(app):
    result_id = one(app)
    with app.app_context():
        row = db.session.get(Result, result_id)
        assert row.discovery_status == DiscoveryStatus.NEW
        assert row.review_status == ReviewStatus.PENDING
        assert [event.event_type for event in db.session.scalars(db.select(ResultAuditEvent)).all()] == ['DISCOVERED']
    assert [item['id'] for item in page(app, 'pending', 0)[0]] == [result_id]


def test_human_decisions_move_between_exclusive_queues(app):
    approved_id = one(app, title='Approved historic building restoration notice', reference='APP-1')
    rejected_id = one(app, title='Rejected historic building restoration notice', reference='REJ-1', url='https://example.com/rejected')
    pending = {item['id']: item for item in page(app, 'pending', 0)[0]}
    decide(app, approved_id, pending[approved_id]['version'], 'approved', 123)
    decide(app, rejected_id, pending[rejected_id]['version'], 'rejected', 123)
    assert not page(app, 'pending', 0)[0]
    assert [item['id'] for item in page(app, 'approved', 0)[0]] == [approved_id]
    assert [item['id'] for item in page(app, 'rejected', 0)[0]] == [rejected_id]
    with app.app_context():
        events = [(event.result_id, event.event_type) for event in
                  db.session.scalars(db.select(ResultAuditEvent).order_by(ResultAuditEvent.id)).all()]
        assert (approved_id, 'APPROVED') in events and (rejected_id, 'REJECTED') in events


def test_unchanged_approved_preserves_decision_and_skips_ai(app):
    item = candidate()
    result_id = one(app)
    pending = page(app, 'pending', 0)[0][0]
    decide(app, result_id, pending['version'], 'approved', 123)
    analyzer = Mock()
    summary = execute(app, [item], analyzer)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.duplicate_count == 1 and not page(app, 'pending', 0)[0]
    with app.app_context():
        row = db.session.get(Result, result_id)
        assert row.discovery_status == DiscoveryStatus.UNCHANGED
        assert row.review_status == ReviewStatus.APPROVED


def test_unchanged_rejected_preserves_decision_and_skips_ai(app):
    item = candidate()
    result_id = one(app)
    pending = page(app, 'pending', 0)[0][0]
    decide(app, result_id, pending['version'], 'rejected', 123)
    analyzer = Mock()
    summary = execute(app, [item], analyzer)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.duplicate_count == 1 and not page(app, 'pending', 0)[0]
    assert page(app, 'rejected', 0)[0][0]['id'] == result_id


def test_meaningful_update_reopens_and_preserves_approval_audit(app):
    item = candidate()
    result_id = one(app)
    pending = page(app, 'pending', 0)[0][0]
    decide(app, result_id, pending['version'], 'approved', 123)
    updated = item.model_copy(update={'deadline': today_in_morocco() + timedelta(days=60)})
    summary = execute(app, [updated])
    assert summary.updated_results_count == 1
    assert page(app, 'pending', 0)[0][0]['id'] == result_id
    with app.app_context():
        row = db.session.get(Result, result_id)
        assert row.discovery_status == DiscoveryStatus.UPDATED
        assert row.review_status == ReviewStatus.PENDING
        assert row.update_reason == {'changed_fields': ['deadline']}
        assert [event.event_type for event in db.session.scalars(db.select(ResultAuditEvent)
            .where(ResultAuditEvent.result_id == result_id).order_by(ResultAuditEvent.id)).all()] == [
                'DISCOVERED', 'APPROVED', 'REOPENED']


def test_minor_metadata_change_does_not_reopen_or_call_ai(app):
    item = candidate()
    result_id = one(app)
    pending = page(app, 'pending', 0)[0][0]
    decide(app, result_id, pending['version'], 'approved', 123)
    minor = item.model_copy(update={'metadata': {'retrieval_note': 'format cleanup'}})
    analyzer = Mock()
    summary = execute(app, [minor], analyzer)
    analyzer.analyze_candidate.assert_not_called()
    assert summary.duplicate_count == 1 and not page(app, 'pending', 0)[0]
    assert page(app, 'approved', 0)[0][0]['id'] == result_id


def test_run_history_page_uses_execution_metrics(app):
    execute(app, [candidate()])
    runs, more, pages = run_page(app, 0)
    assert len(runs) == 1 and not more and pages == 1
    assert runs[0]['found'] == 1 and runs[0]['new'] == 1 and runs[0]['known'] == 0


def test_new_radar1_callback_names_are_valid_and_old_queues_are_absent():
    for action in ('pending', 'approved', 'rejected', 'runs'):
        assert parse_callback(f'{action}:{CODE}') == (action, CODE)
