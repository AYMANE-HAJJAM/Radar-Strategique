from datetime import timedelta
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from backend.app.core.agent_schemas import RunSummary, RunStatus, Stage
from backend.app.bot.handlers.jobs import notify_when_finished
from backend.app.bot.keyboards.main import COMPLETION_LABELS, radar_keyboard
from backend.app.db.extensions import db
from backend.app.db.models import Radar, Result, ResultObservation, SearchRun, utcnow
from backend.app.core.agent_job_service import JobTicket
from backend.app.core.review import page, run_result_page, run_actionable_count, detail
from backend.app.bot.handlers.markets import parse_market_callback
from backend.app.bot.handlers.projects import parse_project_callback
from backend.app.bot.handlers.institutions import parse_institution_callback
from backend.app.bot.handlers.policies import parse_policy_callback
from backend.app.bot.handlers.funding import parse_funding_callback

RADARS = [('RADAR_1_MARKETS', 'm', parse_market_callback), ('RADAR_2_PROJECTS', 'p', parse_project_callback), ('RADAR_3_INSTITUTIONS', 'i', parse_institution_callback), ('RADAR_4_POLICIES', 'l', parse_policy_callback), ('RADAR_5_FUNDING', 'f', parse_funding_callback)]


def add_result(radar_id, suffix, review='PENDING', discovery='NEW', status='new'):
    row = Result(radar_id=radar_id, title=f'Étude de restauration du monument historique {suffix}', fingerprint=f'fp-{radar_id}-{suffix}', status=status, discovery_status=discovery, review_status=review, priority='2', source_status='open', content_hash=f'{suffix:0>12}'[-12:], url='https://example.com/item', radar_metadata={'detail_verified': True, 'official_confirmation': True, 'morocco_related': True, 'current_evidence': True})
    db.session.add(row); db.session.flush(); return row


def seed_run(app, code, observations, *, rejected=0):
    """observations: list of (obs_state, discovery, review_status)."""
    with app.app_context():
        radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == code))
        run = SearchRun(radar_id=radar_id, status='completed', finished_at=utcnow(),
                        new_results_count=sum(1 for state, disc, _ in observations if disc == 'NEW'),
                        updated_results_count=sum(1 for state, disc, _ in observations if disc == 'UPDATED'),
                        duplicate_count=sum(1 for state, _, _ in observations if state == 'unchanged'),
                        rejected_count=rejected,
                        manual_review_count=sum(1 for _, disc, rev in observations
                                                if disc in {'NEW', 'UPDATED'} and rev == 'PENDING'))
        db.session.add(run); db.session.flush()
        ids = []
        for n, (state, discovery, review) in enumerate(observations):
            status = 'manual_review' if state == 'manual_review' else ('unchanged' if state == 'unchanged' else state)
            row = add_result(radar_id, f'{code}-{n}', review=review, discovery=discovery, status=status)
            ids.append(row.id)
            db.session.add(ResultObservation(run_id=run.id, result_id=row.id, state=state, snapshot={}))
        db.session.commit()
        return run.id, ids


@pytest.mark.parametrize('code,prefix,parser', RADARS)
def test_exact_run_queue_excludes_backlog_unchanged_and_reviewed(app, code, prefix, parser):
    with app.app_context():
        radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == code))
        run = SearchRun(radar_id=radar_id, status='completed', finished_at=utcnow())
        other_run = SearchRun(radar_id=radar_id, status='completed', started_at=utcnow() - timedelta(days=1), finished_at=utcnow())
        db.session.add_all([run, other_run]); db.session.flush()
        for n in range(7): add_result(radar_id, f'old{n}')
        expected = []
        for n, state in enumerate(('new', 'updated', 'new', 'updated', 'new')):
            row = add_result(radar_id, f'run{n}'); expected.append(row.id)
            db.session.add(ResultObservation(run_id=run.id, result_id=row.id, state=state, snapshot={}))
        unchanged = add_result(radar_id, 'unchanged')
        reviewed = add_result(radar_id, 'reviewed', 'APPROVED')
        wrong_run = add_result(radar_id, 'wrongrun')
        db.session.add_all([ResultObservation(run_id=run.id, result_id=unchanged.id, state='unchanged', snapshot={}), ResultObservation(run_id=run.id, result_id=reviewed.id, state='new', snapshot={}), ResultObservation(run_id=other_run.id, result_id=wrong_run.id, state='new', snapshot={})])
        db.session.commit(); run_id = run.id
    global_cards = page(app, 'pending', 0, include_total=True, code=code)
    cards, more, total = run_result_page(app, run_id, 0, include_total=True, code=code)
    assert global_cards[2] == 3 and len(global_cards[0]) == 5
    assert {item['id'] for item in cards} == set(expected)
    assert not more and total == 1 and run_actionable_count(app, run_id, code) == 5
    assert parser(f'{prefix}:run:{run_id}:0') == (f'run_{run_id}', 0, None, None)
    assert parser(f'{prefix}:run_details:{run_id}:{expected[0]}:0') == (f'run_details_{run_id}', 0, expected[0], None)


def test_cross_radar_observation_can_open_from_exact_run(app):
    with app.app_context():
        radars = db.session.scalars(db.select(Radar).order_by(Radar.id)).all()
        run = SearchRun(radar_id=radars[1].id, status='completed', finished_at=utcnow())
        row = add_result(radars[0].id, 'shared')
        db.session.add(run); db.session.flush()
        db.session.add(ResultObservation(run_id=run.id, result_id=row.id, state='updated', snapshot={}))
        db.session.commit(); run_id, result_id = run.id, row.id
    assert detail(app, result_id, 'RADAR_2_PROJECTS') is None
    assert detail(app, result_id, 'RADAR_2_PROJECTS', run_id)['id'] == result_id


@pytest.mark.parametrize('code,prefix,_', RADARS)
async def test_completion_keyboard_shows_voir_for_manual_review_observations(app, code, prefix, _):
    """Regression: workflow saves use observation state 'manual_review' for NEW/UPDATED PENDING."""
    observations = (
        [('manual_review', 'NEW', 'PENDING')] * 3 +
        [('manual_review', 'UPDATED', 'PENDING')] * 2
    )
    run_id, _ = seed_run(app, code, observations, rejected=94)
    assert run_actionable_count(app, run_id, code) == 5
    future = Future()
    future.set_result(RunSummary(id=run_id, radar_code=code, status=RunStatus.COMPLETED,
        current_stage=Stage.COMPLETED, new_results_count=3, updated_results_count=2,
        rejected_count=94, manual_review_count=5))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(run_id, future), message, code,
                               list(COMPLETION_LABELS).index(code) + 1, app)
    labels = [button.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard
              for button in row]
    callbacks = [button.callback_data for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard
                 for button in row]
    assert labels == [COMPLETION_LABELS[code], '⬅️ Retour']
    assert callbacks == [f'{prefix}:run:{run_id}:0', f'radar:{code}']


@pytest.mark.parametrize('code,prefix,_', RADARS)
async def test_completion_keyboard_retour_only_when_only_unchanged(app, code, prefix, _):
    observations = [('unchanged', 'UNCHANGED', 'PENDING')] * 3
    run_id, _ = seed_run(app, code, observations, rejected=97)
    assert run_actionable_count(app, run_id, code) == 0
    future = Future()
    future.set_result(RunSummary(id=run_id, radar_code=code, status=RunStatus.COMPLETED,
        current_stage=Stage.COMPLETED, duplicate_count=3, rejected_count=97, manual_review_count=0))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(run_id, future), message, code,
                               list(COMPLETION_LABELS).index(code) + 1, app)
    labels = [button.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard
              for button in row]
    assert labels == ['⬅️ Retour']
    assert 'Voir' not in ''.join(labels)


@pytest.mark.parametrize('code,prefix,_', RADARS)
async def test_completion_keyboard_retour_only_after_all_reviewed(app, code, prefix, _):
    observations = (
        [('manual_review', 'NEW', 'APPROVED')] * 3 +
        [('manual_review', 'UPDATED', 'REJECTED')] * 2
    )
    run_id, _ = seed_run(app, code, observations)
    assert run_actionable_count(app, run_id, code) == 0
    future = Future()
    future.set_result(RunSummary(id=run_id, radar_code=code, status=RunStatus.COMPLETED,
        current_stage=Stage.COMPLETED, new_results_count=3, updated_results_count=2,
        manual_review_count=5))
    message = SimpleNamespace(reply_text=AsyncMock())
    await notify_when_finished(JobTicket(run_id, future), message, code,
                               list(COMPLETION_LABELS).index(code) + 1, app)
    labels = [button.text for row in message.reply_text.call_args.kwargs['reply_markup'].inline_keyboard
              for button in row]
    assert labels == ['⬅️ Retour']


@pytest.mark.parametrize('code,prefix,_', RADARS)
def test_live_pending_partial_review_keeps_voir_cta(app, code, prefix, _):
    observations = (
        [('manual_review', 'NEW', 'PENDING')] * 2 +
        [('manual_review', 'UPDATED', 'APPROVED')] * 3
    )
    run_id, _ = seed_run(app, code, observations)
    assert run_actionable_count(app, run_id, code) == 2
    cards, _, total = run_result_page(app, run_id, 0, include_total=True, code=code)
    assert len(cards) == 2 and total == 1


@pytest.mark.parametrize('code', COMPLETION_LABELS)
def test_radar_menu_still_has_recherches_precedentes(code):
    labels = [row[0].text for row in radar_keyboard(code).inline_keyboard]
    assert '🕘 Recherches précédentes' in labels
    assert '📥 À traiter' in labels
