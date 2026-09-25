from datetime import timedelta, date, datetime, timezone
from unittest.mock import Mock

import pytest

from backend.app.db.extensions import db
from backend.app.db.models import Result, MarketReview
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar1_markets.parser import normalize_hit
from backend.app.modules.radar1_markets.official_link_resolver import OfficialLinkResolver
from backend.app.core.review import page, decide, best_link, CODE
from backend.app.bot.handlers.common import on_callback
from backend.app.bot.keyboards.main import radar_keyboard
from backend.app.bot.handlers.markets import parse_market_callback
from test_bot import fixture_update
from test_phase3 import hit, execute, URL
from test_agent import candidate
from backend.scripts.test_agent import MockAnalyzer


def review_rows(app, count=1):
    execute(app, [candidate(title=f'Etude architecturale patrimoniale {n}', reference=f'REF-{n}',
        url=f'https://example.com/notice/{n}', source_conflict=True) for n in range(count)])
    return page(app, 'pending', 0)[0]


def test_workflow_menu_radar1_only():
    labels = [row[0].text for row in radar_keyboard(CODE).inline_keyboard]
    assert labels == ['🔎 Lancer une recherche', '📥 À traiter', '✅ Validés', '❌ Rejetés',
                      '🕘 Recherches précédentes', '⬅️ Retour']
    assert all('nouveautés' not in label.casefold() and 'vérifier' not in label.casefold() and
               label != '🗂️ Historique' for label in labels)
    for code in RADAR_AGENT_REGISTRY.catalog():
        if code != CODE:
            assert not any('vérifier' in row[0].text for row in radar_keyboard(code).inline_keyboard)


def test_review_pagination(app):
    review_rows(app, 12)
    first, more = page(app, 'pending', 0)
    second, more2 = page(app, 'pending', 1)
    last, more3 = page(app, 'pending', 2)
    assert (len(first), len(second), len(last)) == (5, 5, 2)
    assert more and more2 and not more3
    assert len({item['id'] for item in first + second + last}) == 12


@pytest.mark.parametrize('decision,state', [('approved', 'new'), ('rejected', 'rejected')])
def test_decision_and_audit(app, decision, state):
    item = review_rows(app)[0]
    decide(app, item['id'], item['version'], decision, 123)
    assert page(app, 'pending', 0)[0] == []
    assert bool(page(app, decision, 0)[0])
    with app.app_context():
        row = db.session.get(Result, item['id'])
        audit = db.session.scalar(db.select(MarketReview))
        assert row.status == state and not row.radar_metadata['needs_manual_review']
        assert audit.reviewed_by == 123 and audit.reviewed_at
        assert audit.previous_review_reason == 'OFFICIAL_SOURCE_CONFLICT'
        assert audit.snapshot['radar_metadata']['needs_manual_review'] is True
    with pytest.raises(ValueError, match='déjà traité'):
        decide(app, item['id'], item['version'], decision, 123)


def test_stale_foreign_or_unauthorized_actions_denied(app):
    item = review_rows(app)[0]
    with pytest.raises(ValueError):
        decide(app, item['id'], '0'*12, 'approved', 123)
    # Telegram allowlist is enforced in the bot layer (handlers.authorized), not decide().
    with app.app_context():
        row = db.session.get(Result, item['id'])
        row.deadline = today_in_morocco() - timedelta(days=1)
        db.session.commit()
    with pytest.raises(ValueError, match='actualité'):
        decide(app, item['id'], item['version'], 'approved', 123)


def test_approval_survives_unchanged_but_changed_evidence_reopens_review(app):
    original = candidate(source_conflict=True)
    execute(app, [original])
    item = page(app, 'pending', 0)[0][0]
    decide(app, item['id'], item['version'], 'approved', 123)
    summary = execute(app, [original])
    assert summary.analyzed_count == 0 and len(page(app, 'approved', 0)[0]) == 1
    execute(app, [original.model_copy(update={'deadline': today_in_morocco()+timedelta(days=40)})])
    assert len(page(app, 'pending', 0)[0]) == 1 and not page(app, 'approved', 0)[0]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(MarketReview)) == 1


def test_secondary_resolves_exact_official_snapshot():
    secondary = normalize_hit(hit(url='https://news.example/item'))
    lookup = Mock(return_value=[normalize_hit(hit())])
    resolved = OfficialLinkResolver().resolve(secondary, lookup)
    assert lookup.call_count == 1 and resolved.url == URL and resolved.official_url == URL
    assert resolved.official_url_status == 'VERIFIED_DIRECT'
    assert resolved.metadata['discovery_url'] == secondary.url


def test_unrelated_confirmation_cannot_replace_source():
    secondary = normalize_hit(hit(url='https://news.example/item'))
    unrelated = normalize_hit(hit(reference='OTHER'))
    resolved = OfficialLinkResolver().resolve(secondary, lambda _: [unrelated])
    assert resolved.url == secondary.url and resolved.official_url_status == 'SECONDARY_ONLY'


def test_institutional_confirmation_and_missing_reference():
    secondary = normalize_hit(hit(url='https://news.example/item', reference=None))
    official = normalize_hit(hit(url='https://culture.gov.ma/consultation/notice', reference=None))
    found = OfficialLinkResolver().resolve(secondary, lambda _: [official])
    assert found.official_url_status == 'VERIFIED_INSTITUTIONAL' and found.url == official.url


def test_legacy_review_flag_is_actionable_and_not_news(app):
    item = review_rows(app)[0]
    with app.app_context():
        row = db.session.get(Result, item['id'])
        row.status = 'new'
        db.session.commit()
    assert page(app, 'pending', 0)[0] and not page(app, 'approved', 0)[0]
    decide(app, item['id'], item['version'], 'approved', 123)
    assert page(app, 'approved', 0)[0]


def test_old_review_hidden_without_deletion(app):
    item = review_rows(app)[0]
    with app.app_context():
        row = db.session.get(Result, item['id'])
        row.deadline = date(2025, 1, 1)
        row.source_status = 'closed'
        db.session.commit()
    assert not page(app, 'pending', 0)[0]
    with app.app_context():
        assert db.session.get(Result, item['id']) is not None


def test_generic_pmmp_not_preferred_over_detail(app):
    generic = 'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch'
    indirect = normalize_hit(hit(url=generic))
    result = OfficialLinkResolver().resolve(indirect, lambda _: [normalize_hit(hit())])
    assert result.url == URL and result.official_url_status == 'VERIFIED_DIRECT'
    fallback = OfficialLinkResolver().resolve(indirect, lambda _: [])
    assert fallback.official_url_status == 'INDIRECT_PMMP'
    assert fallback.reference and fallback.institution and fallback.metadata['discovery_url'] == generic
    execute(app, [fallback])
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        assert best_link(row) == (None, 'indisponible')


@pytest.mark.parametrize('changes,reason', [({'deadline': None}, 'DEADLINE_UNCLEAR'),

    ({'reference_conflict': True}, 'REFERENCE_CONFLICT'),
    ({'morocco_related': None}, 'GEOGRAPHY_AMBIGUOUS'),
    ({'source_status': 'unknown'}, 'STATUS_UNCLEAR')])
def test_specific_reasons(changes, reason):
    decision = RADAR_AGENT_REGISTRY.resolve(CODE).validate_candidate(candidate(**changes))
    assert decision.needs_manual_review and reason in decision.reasons


def test_strong_evidence_resolves_medium_confidence_but_not_low_or_uncertainty():
    radar = RADAR_AGENT_REGISTRY.resolve(CODE)
    item = normalize_hit(hit()).model_copy(update={'detail_verified': True})
    analysis = MockAnalyzer().analyze_candidate(item, None, analysis_schema=radar.analysis_schema).analysis
    analysis.confidence = 0.7
    assert not radar.validated_analysis(item, analysis).needs_manual_review
    uncertain = item.model_copy(update={'deadline': None})
    assert radar.validated_analysis(uncertain, analysis).needs_manual_review
    analysis.confidence = 0.4
    assert radar.validated_analysis(item, analysis).relevant
    assert radar.validated_analysis(item, analysis).needs_manual_review


@pytest.mark.parametrize('year', [2024, 2025])
def test_old_closed_excluded(app, year):
    summary = execute(app, [candidate(publication_date=date(year, 1, 1), deadline=date(year, 2, 1), source_status='closed')])
    assert summary.rejected_count == 1 and not page(app, 'approved', 0)[0]


def test_current_open_news_and_same_day_time_expiry(app):
    execute(app, [normalize_hit(hit()).model_copy(update={'detail_verified': True})])
    assert len(page(app, 'pending', 0)[0]) == 1
    with app.app_context():
        row = db.session.scalar(db.select(Result))
        row.radar_metadata = {**row.radar_metadata, 'deadline_at': (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
        db.session.commit()
    assert not page(app, 'pending', 0)[0]


async def test_telegram_review_cards_buttons_and_next_page(app):
    review_rows(app, 6)
    update, context = fixture_update(app, data=f'pending:{CODE}')
    await on_callback(update, context)
    calls = update.callback_query.message.reply_text.call_args_list
    assert len(calls) == 6  # five cards plus navigation
    assert '⚠️ À vérifier' in calls[0].args[0]
    card_buttons = calls[0].kwargs['reply_markup'].inline_keyboard
    assert card_buttons[0][0].url == URL or card_buttons[0][0].url.startswith('https://')
    approve = card_buttons[1][0].callback_data
    assert len(approve.encode()) <= 64
    parse_market_callback(approve)
    assert calls[-1].kwargs['reply_markup'].inline_keyboard[0][0].callback_data == 'm:pending:1'
    stored = list(context.user_data['queue_view']['result_message_ids'])
    nav_id = context.user_data['queue_view']['navigation_message_id']
    update2, context2 = fixture_update(app, data=approve)
    context2.user_data = context.user_data
    context2.application.bot = context.application.bot
    await on_callback(update2, context2)
    assert context2.user_data['queue_view']['navigation_message_id'] == nav_id
    # Five remaining items still fill the five slots — same message IDs reused.
    assert context2.user_data['queue_view']['result_message_ids'] == stored
    assert any(c.kwargs.get('text') == 'Page 1/1'
               for c in context.application.bot.edit_message_text.call_args_list)
    assert update2.callback_query.message.reply_text.await_count == 0


async def test_unauthorized_market_callback(app):
    update, context = fixture_update(app, user_id=999, data='m:review:0')
    await on_callback(update, context)
    update.callback_query.answer.assert_awaited_once_with('Accès non autorisé.', show_alert=True)
    update.callback_query.message.reply_text.assert_not_awaited()
