"""Regression: Radar 1 queue uniqueness, pagination, and architecture final gate."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.app.bot.handlers.common import on_callback
from backend.app.bot.handlers.markets import handle, parse_market_callback, show_page
from backend.app.modules.radar1_markets.policy import evaluate_relevance, relevant
from backend.app.db.extensions import db
from backend.app.db.models import Result, Radar
from backend.app.core.review import page, _unique_eligible, CODE
from backend.app.core.review import ReviewStatus
from test_bot import fixture_update
from backend.tests.modules.radar1.test_market_usability import review_rows
from test_phase3 import execute
from test_agent import candidate


def _pending_row(app, title, fingerprint, **metadata):
    with app.app_context():
        radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == CODE))
        row = Result(
            radar_id=radar_id,
            title=title,
            fingerprint=fingerprint,
            status='new',
            review_status=ReviewStatus.PENDING,
            discovery_status='NEW',
            priority='2',
            source_status='open',
            content_hash='abc123def456' + fingerprint[:4],
            radar_metadata={
                'detail_verified': True,
                'official_confirmation': True,
                'morocco_related': True,
                **metadata,
            },
        )
        db.session.add(row)
        db.session.commit()
        return row.id


@pytest.mark.parametrize('title,reason', [
    ('Prestations topographiques par LiDAR', 'topography_only'),
    ('Contrôle topographique des ouvrages', 'topography_only'),
    ('Topographic surveys for subdivision', 'topography_only'),
    ('Levés LiDAR pour lotissement', 'topography_only'),
    ('Étude géomètre et cartographie SIG', 'topography_only'),
])
def test_topography_and_lidar_only_rejected(title, reason):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['rejection_reason'] == reason
    assert not relevant(title)


@pytest.mark.parametrize('title', [
    'Études architecturales et topographiques pour réhabilitation',
    'Consultation architecturale et levés topographiques',
    'Conception architecturale avec topographie complémentaire',
])
def test_architecture_mixed_with_topography_without_heritage_rejected(title):
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['architecture_scope'] is False


@pytest.mark.parametrize('title', [
    'Étude architecturale',
    'Études architecturales',
])
def test_bare_architectural_study_without_project_family_is_rejected(title):
    from backend.app.modules.radar1_markets.policy import REASON_REJECT_GENERIC
    result = evaluate_relevance(title)
    assert result['decision'] == 'reject'
    assert result['reason_code'] == REASON_REJECT_GENERIC


def test_architectural_competition_is_now_first_class():
    result = evaluate_relevance('Concours architectural pour un équipement public')
    assert result['business_category'] == 'P1_CONCOURS'
    assert result['architecture_scope'] is True


def test_pending_queue_hides_topography_legacy_rows(app):
    kept = _pending_row(app, 'Etude architecturale du monument historique', 'arch-keep-1')
    _pending_row(app, 'Prestations topographiques par LiDAR', 'topo-hide-1')
    _pending_row(app, 'Topographic surveys for roads', 'topo-hide-2')
    cards = page(app, 'pending', 0)[0]
    ids = [item['id'] for item in cards]
    assert ids == [kept]
    assert len(ids) == len(set(ids))


def test_duplicate_sql_rows_collapse_to_one_card():
    twin = SimpleNamespace(
        id=7, title='Etude architecturale patrimoniale', radar_metadata={'detail_verified': True},
        source_status='open', deadline=None, publication_date=None, analysis=None)
    collapsed = list(_unique_eligible([twin, twin, twin], 'pending', CODE))
    assert len(collapsed) == 1 and collapsed[0].id == 7


def test_same_result_id_rendered_once_across_pages(app):
    review_rows(app, 12)
    first = page(app, 'pending', 0)[0]
    second = page(app, 'pending', 1)[0]
    third = page(app, 'pending', 2)[0]
    assert len(first) == 5 and len(second) == 5 and len(third) == 2
    ids = [item['id'] for item in first + second + third]
    assert len(ids) == len(set(ids)) == 12
    assert set(item['id'] for item in first).isdisjoint(item['id'] for item in second)


async def test_repeated_a_traiter_replaces_queue_without_duplicate_ids(app):
    review_rows(app, 5)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    first_ids = []
    for call in update.callback_query.message.reply_text.call_args_list[:-1]:
        text = call.args[0]
        if text.startswith('['):
            first_ids.append(text.split(']', 1)[0])
    assert len(first_ids) == 5
    view = context.user_data['queue_view']
    stored = list(view['result_message_ids'])
    update2, context2 = fixture_update(app, data=f'pending:{CODE}')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await on_callback(update2, context2)
    # Same slots reused via edit — no duplicate card sends.
    assert context.user_data['queue_view']['result_message_ids'] == stored
    assert context.application.bot.edit_message_text.await_count >= 5
    second_replies = [c.args[0] for c in update2.callback_query.message.reply_text.call_args_list
                      if c.args and str(c.args[0]).startswith('[')]
    assert second_replies == []


async def test_details_back_does_not_resend_queue(app):
    record = review_rows(app)[0]
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    slot_ids = list(context.user_data['queue_view']['result_message_ids'])
    nav_id = context.user_data['queue_view']['navigation_message_id']

    details_update, details_context = fixture_update(app, data=f'm:details:pending:{record["id"]}:0')
    details_context.user_data = context.user_data
    details_context.application.bot = context.application.bot
    await on_callback(details_update, details_context)
    edit = context.application.bot.edit_message_text.call_args
    back = edit.kwargs['reply_markup'].inline_keyboard[-1][0].callback_data
    assert back == 'm:back:pending:0'
    assert parse_market_callback(back)[0] == 'back_pending'

    back_update, back_context = fixture_update(app, data=back)
    back_context.user_data = details_context.user_data
    back_context.application.bot = context.application.bot
    await on_callback(back_update, back_context)
    assert back_context.user_data['queue_view']['result_message_ids'] == slot_ids
    assert back_context.user_data['queue_view']['navigation_message_id'] == nav_id
    new_cards = [c.args[0] for c in back_update.callback_query.message.reply_text.call_args_list
                 if c.args and str(c.args[0]).startswith('[')]
    assert new_cards == []


async def test_pagination_callbacks_preserve_pending_status(app):
    review_rows(app, 6)
    update, context = fixture_update(app, data='m:pending:0')
    await handle(update, context, parse_market_callback('m:pending:0'))
    assert len(context.user_data['queue_view']['result_message_ids']) == 5
    stored_first = context.user_data['queue_view']['result_message_ids'][0]
    nav_id = context.user_data['queue_view']['navigation_message_id']

    update2, context2 = fixture_update(app, data='m:pending:1')
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await handle(update2, context2, parse_market_callback('m:pending:1'))
    view = context2.user_data['queue_view']
    assert view['result_message_ids'] == [stored_first]
    assert view['navigation_message_id'] == nav_id
    assert context.application.bot.delete_message.await_count == 4
    nav_edits = [c for c in context.application.bot.edit_message_text.call_args_list
                 if str(c.kwargs.get('text', '')).startswith('Page')]
    assert nav_edits
    assert nav_edits[-1].kwargs['reply_markup'].inline_keyboard[0][0].callback_data == 'm:pending:0'

def test_discovery_coverage_sector_unchanged(app):
    from backend.app.modules.radar1_markets.discovery_strategies import direct_discovery_plan
    plan = direct_discovery_plan(app.config)
    assert any(item.url.endswith('services-architecturales-et-topographiques') for item in plan)


def test_radars_2_to_5_queue_helpers_unchanged():
    # Radar 2 still bypasses Radar 1 architecture/obsolete gates via code argument.
    twin = SimpleNamespace(
        id=9, title='Prestations topographiques par LiDAR', radar_metadata={},
        source_status='open', deadline=None, publication_date=None, analysis=None)
    assert list(_unique_eligible([twin], 'pending', 'RADAR_2_PROJECTS'))[0].id == 9
