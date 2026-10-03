from datetime import timedelta

import pytest

from app.core.review import card, decide, page
from app.core.review_changes import business_changes
from app.db.extensions import db
from app.db.models import Result, ResultAuditEvent, MarketReview, SearchRun
from app.db.repositories.results import ResultService
from scripts.test_agent import MockAnalyzer
from test_agent import candidate
from test_phase3 import execute


def reviewed(app, decision='approved', **fields):
    item = candidate(**fields)
    execute(app, [item])
    pending = page(app, 'pending', 0)[0][0]
    decide(app, pending['id'], pending['version'], decision, 123)
    return item, pending['id']


def save_reanalysis(app, result_id, item):
    """Exercise persistence even when changed agent memory forces reanalysis."""
    with app.app_context():
        row = db.session.get(Result, result_id)
        run = db.session.scalar(db.select(SearchRun).order_by(SearchRun.id.desc()))
        analysis = MockAnalyzer().analyze_candidate(item, None).analysis
        ResultService().save(run, item, analysis, row, workflow_enabled=True)
        db.session.commit()


def test_validated_unchanged_stays_validated(app):
    item, result_id = reviewed(app)
    execute(app, [item])
    assert not page(app, 'pending', 0)[0]
    assert page(app, 'approved', 0)[0][0]['id'] == result_id


@pytest.mark.parametrize('updates', [
    {'title': '  Etude  architecturale   patrimoniale  ', 'metadata': {'technical_note': 'refresh'}},
    {'business_category': 'P1_CONCOURS'},
    {'estimated_amount_source': 'PMMP_DETAIL', 'publication_date_verified': True},
    {'estimated_currency': 'MAD', 'estimated_amount_tax_mode': 'TTC'},
    {'estimated_lots': [{'name': 'Lot A', 'amount': 200}, {'name': 'Lot B', 'amount': 300}]},
])
def test_non_material_reanalysis_does_not_reopen(app, updates):
    fields = {'estimated_lots': [{'amount': 300, 'name': 'Lot B'}, {'amount': 200, 'name': 'Lot A'}]} if 'estimated_lots' in updates else {}
    item, result_id = reviewed(app, **fields)
    save_reanalysis(app, result_id, item.model_copy(update=updates))
    with app.app_context():
        row = db.session.get(Result, result_id)
        assert row.review_status == 'APPROVED'
        assert not db.session.scalar(db.select(ResultAuditEvent).where(
            ResultAuditEvent.result_id == result_id, ResultAuditEvent.event_type == 'REOPENED'))
    assert not page(app, 'pending', 0)[0]
    assert page(app, 'approved', 0)[0][0]['id'] == result_id


@pytest.mark.parametrize('field,value', [
    ('deadline', None), ('title', 'Etude architecturale patrimoniale et diagnostic structurel'),
    ('estimated_amount', 2000000), ('procedure_type', 'architectural_consultation'),
    ('institution', 'Autre acheteur'), ('location_evidence', 'Fes, Maroc'),
    ('provisional_bond_amount', 70000), ('deadline_time', '14:30'),
])
def test_material_change_reopens_approval_with_recorded_diff(app, field, value):
    item, result_id = reviewed(app)
    if field == 'deadline':
        value = item.deadline + timedelta(days=5)
    save_reanalysis(app, result_id, item.model_copy(update={field: value}))
    with app.app_context():
        row = db.session.get(Result, result_id)
        payload = card(row)
        assert row.review_status == 'PENDING'
        assert row.discovery_status == 'UPDATED'
        assert payload['previous_review_status'] == 'APPROVED'
        changes = {change['field']: change for change in payload['review_changes']}
        assert field in changes
        assert changes[field]['after'] == (value.isoformat() if field == 'deadline' else value)
        assert db.session.scalar(db.select(db.func.count()).select_from(MarketReview)) == 1


def test_rejection_reopens_and_second_review_preserves_both_decisions(app):
    item, result_id = reviewed(app, 'rejected')
    execute(app, [item.model_copy(update={'deadline': item.deadline + timedelta(days=7)})])
    pending = page(app, 'pending', 0)[0][0]
    assert pending['previous_review_status'] == 'REJECTED'
    assert pending['discovery_status'] == 'UPDATED'
    decide(app, result_id, pending['version'], 'approved', 456)
    with app.app_context():
        reviews = db.session.scalars(db.select(MarketReview).order_by(MarketReview.id)).all()
        assert [review.decision for review in reviews] == ['rejected', 'approved']
        assert [review.reviewed_by for review in reviews] == [123, 456]
        assert reviews[0].snapshot['business_snapshot']['deadline'] == item.deadline.isoformat()
        row = db.session.get(Result, result_id)
        assert row.review_status == 'APPROVED'
        assert card(row)['previous_review_status'] is None
        events = db.session.scalars(db.select(ResultAuditEvent).order_by(ResultAuditEvent.id)).all()
        assert [e.event_type for e in events] == ['DISCOVERED', 'REJECTED', 'REOPENED', 'APPROVED']


def test_second_review_can_reject_previously_approved_result(app):
    item, result_id = reviewed(app)
    execute(app, [item.model_copy(update={'deadline': item.deadline + timedelta(days=7)})])
    pending = page(app, 'pending', 0)[0][0]
    decide(app, result_id, pending['version'], 'rejected', 456)
    with app.app_context():
        assert db.session.get(Result, result_id).review_status == 'REJECTED'
        assert [r.decision for r in db.session.scalars(db.select(MarketReview).order_by(MarketReview.id))] == ['approved', 'rejected']


def test_legacy_missing_values_are_not_invented():
    assert business_changes({'title': 'Identical title'}, {'title': 'Identical title', 'deadline': '2026-10-22'}) == []


def test_currency_is_material_when_there_is_an_actual_estimate():
    changes = business_changes({'estimated_amount': 1000, 'estimated_currency': 'MAD'},
                               {'estimated_amount': 1000, 'estimated_currency': 'EUR'})
    assert [change['field'] for change in changes] == ['estimated_currency']


def test_empty_optional_metadata_hydration_is_non_material():
    assert business_changes({'estimated_lots': None, 'document_types': None,
                             'competition_regulation_available': None},
                            {'estimated_lots': [], 'document_types': [],
                             'competition_regulation_available': False}) == []


def test_api_list_and_detail_show_prior_decision_and_changes(app):
    from test_api import make_user, login
    item, result_id = reviewed(app)
    summary = execute(app, [item.model_copy(update={'deadline': item.deadline + timedelta(days=7)})])
    _, code = make_user(app)
    client = app.test_client()
    login(client, code)
    for path in ['/api/radars/1/results?status=pending',
                 f'/api/radars/1/results?status=pending&run_id={summary.id}',
                 f'/api/results/{result_id}']:
        response = client.get(path)
        assert response.status_code == 200
        payload = response.get_json()
        result = payload['items'][0] if 'items' in payload else payload
        assert result['id'] == result_id
        assert result['previous_review_status'] == 'APPROVED'
        assert result['review_changes'] == [{'field': 'deadline', 'before': item.deadline.isoformat(),
            'after': (item.deadline + timedelta(days=7)).isoformat()}]


def test_unchanged_rediscovery_does_not_hide_previous_review_context(app):
    item, result_id = reviewed(app)
    updated = item.model_copy(update={'deadline': item.deadline + timedelta(days=7)})
    execute(app, [updated])
    execute(app, [updated])
    result = page(app, 'pending', 0)[0][0]
    assert result['id'] == result_id
    assert result['previous_review_status'] == 'APPROVED'
    assert [change['field'] for change in result['review_changes']] == ['deadline']
