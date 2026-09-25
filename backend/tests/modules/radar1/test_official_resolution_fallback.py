from datetime import timedelta
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from backend.app.modules.radar1_markets.service import MarketsRadarAgent
from backend.app.core.validation import today_in_morocco
from backend.app.modules.radar1_markets.collector import MarketsCollector
from backend.app.integrations.http.html import AccessLimitedPages
from backend.app.integrations.pmmp.client import canonical_detail_url, is_direct_notice
from backend.app.modules.radar1_markets.resolution import CREDIBLE, VERIFIED, with_resolution
from backend.app.integrations.openai.base import SearchHit, SearchResponse
from backend.app.core.review import page, decide
from backend.app.modules.radar1_markets.official_link_resolver import OfficialLinkResolver
from backend.app.bot.presenters.result_presenter import format_result_card, format_result_details
from backend.app.bot.handlers.markets import result_keyboard
from backend.app.db.extensions import db
from backend.app.db.models import Result
from test_agent import candidate
from test_phase3 import execute
from backend.tests.modules.radar1.test_collection_diagnostics import official_page, LIVE_URL

SECONDARY = 'https://cpmaroc.com/appels-offres/12345'


def fallback(**changes):
    item = candidate(url=SECONDARY, title='Etude architecturale de restauration du patrimoine historique bâti',
                     source_type='PROCUREMENT_AGGREGATOR', metadata={'discovery_url': SECONDARY}, **changes)
    return with_resolution(item, CREDIBLE, error='HTTP 403')


def live_fixture(app, *, code=403, weak=False, official=None, reference='CA11/2026/APDN'):
    source = SearchHit(title='Avis' if weak else 'Etude architecturale de restauration du patrimoine historique bâti',
        reference=None if weak else reference, institution=None if weak else 'APDN',
        url=SECONDARY, kind='tender', execution_country='MA', location='Maroc', status='open',
        publication_date=today_in_morocco().isoformat(),
        deadline=(today_in_morocco()+timedelta(days=20)).isoformat(), procedure_type='consultation')
    provider, reader = Mock(), Mock()
    def search(query, **kwargs):
        if 'etudes architecturales patrimoine' in query:
            return SearchResponse([source])
        if official and ((reference and f'"{reference}"' in query) or (not reference and 'site:culture.gov.ma' in query)):
            return SearchResponse([SearchHit(url=official, kind='discovery_page')])
        return SearchResponse([])
    provider.search.side_effect = search
    def get(url):
        if url == SECONDARY:
            raise HTTPError(url, code, 'Blocked', {}, None)
        page = official_page(title=source.title, reference=reference or 'NEW-1')
        page.texts.append('Maroc')
        return url, page
    reader.get.side_effect = get
    app.config.update(RADAR1_MIN_DISCOVERIES=1, RADAR1_MAX_QUERIES_PER_RUN=8,
                      RADAR1_MIN_SEARCH_QUERIES=1, RADAR1_TARGET_OBSERVATIONS=1)
    run = MarketsCollector(provider, app.config, pages=reader)
    return run, reader


def test_403_reference_resolves_pmmp_without_reading_secondary(app):
    run, reader = live_fixture(app, official=LIVE_URL)
    result = run.collect(MarketsRadarAgent())[0]
    assert result.resolution_state == VERIFIED and result.detail_verified
    assert result.official_url == canonical_detail_url(LIVE_URL)
    assert SECONDARY not in [call.args[0] for call in reader.get.call_args_list]
    assert '"CA11/2026/APDN"' in run.provider.search.call_args_list[1].args[0]


def test_429_title_buyer_resolves_institution_without_secondary_dependency(app):
    url = 'https://culture.gov.ma/avis/architecture-123'
    run, reader = live_fixture(app, code=429, reference=None, official=url)
    result = run.collect(MarketsRadarAgent())[0]
    assert result.resolution_state == VERIFIED and result.official_url == url
    assert any('site:culture.gov.ma' in call.args[0] for call in run.provider.search.call_args_list)


@pytest.mark.parametrize('code', [403, 429])
def test_blocked_strong_identity_kept_and_access_limit_counted_once(app, code):
    run, reader = live_fixture(app, code=code)
    results = run.collect(MarketsRadarAgent())
    assert len(results) == 1 and results[0].resolution_state == CREDIBLE
    assert results[0].official_url is None and not results[0].dce_available
    assert run.report.metrics['http_' + str(code)] == 1
    assert run.report.metrics['unverified_credible'] == 1
    assert run.report.health == 'PARTIAL'
    with pytest.raises(HTTPError):
        run.pages.get(SECONDARY)
    assert reader.get.call_count == 1


def test_blocked_weak_identity_is_unresolved(app):
    run, _ = live_fixture(app, weak=True)
    assert not run.collect(MarketsRadarAgent())
    assert run.report.metrics['query_scope_filtered'] == 0
    assert run.report.metrics['rejected_by_relevance'] >= 1


def test_429_stops_host_until_next_run():
    reader = Mock()
    reader.get.side_effect = HTTPError(SECONDARY, 429, 'Limited', {}, None)
    metrics = {'http_403': 0, 'http_429': 0}
    pages = AccessLimitedPages(reader, metrics)
    for url in (SECONDARY, SECONDARY + 'other'):
        with pytest.raises(HTTPError):
            pages.get(url)
    assert reader.get.call_count == 1 and metrics['http_429'] == 1


def test_fallback_queue_warning_source_button_and_no_dce(app):
    item = fallback(dce_available=True)
    execute(app, [item])
    card = page(app, 'pending', 0)[0][0]
    assert card['url'] == SECONDARY and not card['dce_available']
    assert 'Lien officiel à confirmer' in format_result_card(card, 1, 'pending')
    assert 'DCE : non vérifié' in format_result_card(card, 1, 'pending')
    assert 'Vérification officielle : À confirmer' in format_result_details(card)
    assert 'Agrégateur de marchés publics' in format_result_details(card)
    assert result_keyboard(card, 'pending', 0).inline_keyboard[0][0].text == '🔗 Ouvrir la source'


@pytest.mark.parametrize('changed_deadline', [False, True])
def test_official_enrichment_keeps_same_result_and_only_reopens_for_commercial_change(app, changed_deadline):
    first = fallback()
    execute(app, [first])
    card = page(app, 'pending', 0)[0][0]
    decide(app, card['id'], card['version'], 'approved', 123)
    verified = candidate(title=first.title, reference=first.reference,
        deadline=first.deadline + timedelta(days=3) if changed_deadline else first.deadline,
        resolution_state=VERIFIED, resolution_attempted=True)
    summary = execute(app, [verified])
    with app.app_context():
        rows = db.session.scalars(db.select(Result)).all()
        assert len(rows) == 1 and rows[0].id == card['id']
        assert rows[0].radar_metadata['resolution_state'] == VERIFIED
        assert rows[0].radar_metadata['official_url'] == verified.official_url
        assert rows[0].review_status == ('PENDING' if changed_deadline else 'APPROVED')
    assert summary.updated_results_count == int(changed_deadline)


def test_fallback_reference_without_buyer_later_enriches_same_row(app):
    first = fallback(institution=None)
    execute(app, [first])
    execute(app, [candidate(title=first.title, resolution_state=VERIFIED)])
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 1


def test_duplicate_fallback_does_not_recreate_or_analyze(app):
    item = fallback()
    execute(app, [item])
    analyzer = Mock()
    assert execute(app, [item], analyzer).duplicate_count == 1
    analyzer.analyze_candidate.assert_not_called()


def test_strong_undated_identity_is_reviewable_but_cannot_be_approved_as_current(app):
    execute(app, [fallback(publication_date=None, deadline=None, current_evidence=False)])
    card = page(app, 'pending', 0)[0][0]
    assert 'DEADLINE_UNCLEAR' in card['reason']
    with pytest.raises(ValueError):
        decide(app, card['id'], card['version'], 'approved', 123)


@pytest.mark.parametrize('has_reference', [True, False])
def test_distinct_fallback_tenders_can_share_one_supporting_listing(app, has_reference):
    first = fallback(reference='REF-1' if has_reference else None)
    second = fallback(reference='DIFFERENT-2' if has_reference else None).model_copy(update={'title': 'Restauration architecturale du jardin historique'})
    execute(app, [first, second])
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 2


@pytest.mark.parametrize('change', [dict(source_status='closed'), dict(source_conflict=True),
    dict(deadline=today_in_morocco()-timedelta(days=1)), dict(morocco_related=False),
    dict(publication_date=today_in_morocco()+timedelta(days=1))])
def test_fallback_does_not_bypass_safeguards(app, change):
    item = fallback().model_copy(update=change)
    with app.app_context():
        assert not MarketsRadarAgent().validate_candidate(item).accepted


@pytest.mark.parametrize('path', ['index.php', 'index.php5'])
@pytest.mark.parametrize('route', ['EntrepriseDetailConsultation', 'EntrepriseDetailsConsultation'])
def test_pmmp_url_variants(path, route):
    url = f'https://marchespublics.gov.ma/{path}?page=entreprise.{route}&refConsultation=123&orgAcronyme=a1t'
    assert is_direct_notice(url)
    assert canonical_detail_url(url) == canonical_detail_url(url.replace(path, 'index.php').replace(route, 'EntrepriseDetailsConsultation'))


def test_reference_variants_and_conflicting_buyer():
    original = candidate(reference='27/BG/2026')
    found = candidate(reference='27 BG 2026')
    assert OfficialLinkResolver.matches(original, found)
    assert not OfficialLinkResolver.matches(original, found.model_copy(update={'institution': 'Other buyer'}))
