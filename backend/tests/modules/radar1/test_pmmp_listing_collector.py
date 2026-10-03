"""PMMP listing collection: pagination, change detection, and no paid calls."""
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

from app.modules.radar1_markets.collector import MarketsCollector, legacy_discovery
from app.modules.radar1_markets.pmmp_listing_collector import (
    LISTING_URL, NEW, NEXT_HREF, NEXT_TARGET, DUPLICATE, PmmpHttp, PmmpListing,
    PmmpListingCollector, SEARCH_BUTTON, SOURCE, UNCHANGED, UPDATED, ListingIndex,
    new_pmmp_collector, parse_listings,
)


MODULE = Path(__file__).resolve().parents[3] / 'app' / 'modules' / 'radar1_markets' / 'pmmp_listing_collector.py'


def row(index, *, consultation_id, organization, reference, title, buyer,
        deadline='02/10/2026 10:00', publication='03/09/2026', procedure="Appel d'offres ouvert",
        category='Services', location='SETTAT'):
    prefix = f'ctl0_CONTENU_PAGE_resultSearch_tableauResultSearch_ctl{index}'
    name = f'ctl0$CONTENU_PAGE$resultSearch$tableauResultSearch$ctl{index}'
    return (
        f'<input name="{name}$refCons" value="{consultation_id}">'
        f'<input name="{name}$orgCons" value="{organization}">'
        f'<span id="{prefix}_reference">{reference}</span>'
        f'<span id="{prefix}_panelBlocObjet">Objet : {title}</span>'
        f'<span id="{prefix}_panelBlocDenomination">Acheteur public : {buyer}</span>'
        f'<span id="{prefix}_infosLieuExecutionLtRef">{deadline}</span>'
        f'<span id="{prefix}_panelBlocCategorie">{category} {publication}</span>'
        f'<span id="{prefix}_panelBlocTypesProc">{procedure} {category} {publication}</span>'
        f'<span id="{prefix}_infosLieuExecution">{location} ...</span>'
    )


def result_page(rows, *, state, pages, nxt=False, results=None):
    pager = f'<a href="{NEXT_HREF}"></a>' if nxt else ''
    count = results if results is not None else len(rows)
    return (
        f'<input name="PRADO_PAGESTATE" value="{state}">'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombreElement">{count}</span>'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop">{pages}</span>'
        f'<div id="tableauResultSearch">{"".join(rows)}</div>{pager}'
    )


SETTAT = dict(
    consultation_id='1036481', organization='j8k', reference='04/2026/AUS',
    title=('Etude de valorisation du patrimoine culturel, naturel et historique '
           'de la province de Settat.'),
    buyer='Province de Settat', location='SETTAT')


class ScriptedHttp:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url):
        self.calls.append(('GET', url, None))
        return self.pages.pop(0)

    def post(self, url, fields):
        self.calls.append(('POST', url, fields.get('PRADO_POSTBACK_TARGET')))
        return self.pages.pop(0)


def test_legacy_discovery_stays_the_production_entry():
    calls = []

    class Bound:
        config = {'RADAR1_DISCOVERY_MODE': 'legacy'}
        report = SimpleNamespace(metrics={})

        def legacy_discovery(self, radar):
            calls.append(radar)
            return ['legacy']

    assert MarketsCollector.collect(Bound(), 'radar-1') == ['legacy']
    assert calls == ['radar-1']
    assert legacy_discovery(Bound(), 'radar-1') == ['legacy']


def test_multi_page_collect_stops_on_the_final_page():
    first = result_page([row(1, **SETTAT)], state='page-1', pages=2, nxt=True, results=2)
    second = result_page([
        row(1, consultation_id='1', organization='a1t', reference='01/2026',
            title='Autre consultation', buyer='Commune', location='RABAT'),
    ], state='page-2', pages=2, results=2)
    http = ScriptedHttp([first, second])
    crawl = PmmpListingCollector(http).collect(mode='full')
    assert crawl.pages_fetched == 2
    assert crawl.stop_reason == 'final_page'
    assert crawl.declared_pages == 2
    assert [item.state for item in crawl.observations] == [NEW, NEW]
    assert http.calls[1][2] == NEXT_TARGET
    assert http.pages == []


def test_repeated_page_does_not_loop():
    page = result_page([row(1, **SETTAT)], state='same', pages=5, nxt=True)
    http = ScriptedHttp([page, page])
    crawl = PmmpListingCollector(http).collect(mode='full')
    assert crawl.stop_reason == 'pagination_loop'
    assert crawl.pages_fetched == 1
    assert len(crawl.observations) == 1


def test_new_unchanged_and_updated_listing_fingerprints():
    page = result_page([row(1, **SETTAT)], state='s', pages=1)
    first = PmmpListingCollector(ScriptedHttp([page])).collect()
    assert first.observations[0].state == NEW
    saved = first.index.to_dict()
    again = PmmpListingCollector(ScriptedHttp([page])).collect(index=ListingIndex.from_dict(saved))
    assert again.observations[0].state == UNCHANGED
    changed = result_page([row(1, **{**SETTAT, 'deadline': '15/11/2026 18:00'})], state='s', pages=1)
    updated = PmmpListingCollector(ScriptedHttp([changed])).collect(index=ListingIndex.from_dict(saved))
    assert updated.observations[0].state == UPDATED


def test_incremental_overlap_does_not_stop_on_the_first_known_page():
    fresh = row(1, consultation_id='9', organization='zzz', reference='99/2026',
                title='Nouvelle consultation', buyer='Commune', location='FES')
    older = dict(
        consultation_id='2', organization='bbb', reference='02/2026', title='Notice deja vue',
        buyer='Agence', location='OUJDA')
    index = ListingIndex()
    index.classify(parse_listings(result_page([row(1, **SETTAT)], state='k', pages=1))[0])
    index.classify(parse_listings(result_page([row(1, **older)], state='k2', pages=1))[0])
    pages = [
        result_page([fresh], state='p1', pages=9, nxt=True),
        result_page([row(1, **SETTAT)], state='p2', pages=9, nxt=True),
        result_page([row(1, **older)], state='p3', pages=9, nxt=True),
        result_page([
            row(1, consultation_id='8', organization='yyy', reference='88/2026',
                title='Should not be fetched', buyer='X', location='X'),
        ], state='p4', pages=9, nxt=True),
    ]
    http = ScriptedHttp(pages)
    crawl = PmmpListingCollector(http).collect(mode='incremental', index=index, overlap_pages=2)
    assert crawl.stop_reason == 'incremental_overlap'
    assert crawl.pages_fetched == 3
    assert [item.state for item in crawl.observations] == [NEW, UNCHANGED, UNCHANGED]
    assert len(http.pages) == 1


def test_reconciliation_keeps_walking_past_known_pages():
    index = ListingIndex()
    index.classify(parse_listings(result_page([row(1, **SETTAT)], state='k', pages=1))[0])
    pages = [
        result_page([row(1, **SETTAT)], state='p1', pages=2, nxt=True),
        result_page([
            row(1, consultation_id='7', organization='qqq', reference='70/2026',
                title='An older changed notice', buyer='Agence', location='TAZA',
                deadline='01/12/2026 09:00'),
        ], state='p2', pages=2),
    ]
    crawl = PmmpListingCollector(ScriptedHttp(pages)).collect(
        mode='reconciliation', index=index, overlap_pages=1)
    assert crawl.stop_reason == 'final_page'
    assert [item.state for item in crawl.observations] == [UNCHANGED, NEW]


def test_duplicate_row_identity_is_not_a_second_new_listing():
    page = result_page([row(1, **SETTAT), row(2, **SETTAT)], state='s', pages=1)
    crawl = PmmpListingCollector(ScriptedHttp([page])).collect()
    assert [item.state for item in crawl.observations] == [NEW, DUPLICATE]


def test_same_reference_with_different_buyers_are_different_when_pmmp_id_is_absent():
    shared = dict(
        source=SOURCE, consultation_id=None, organization=None, reference='04/2026/AUS',
        title='Etude', publication_date=None, deadline=None, procedure=None, category=None,
        location=None, detail_url=None)
    left = PmmpListing(**shared, buyer='Province de Settat')
    right = PmmpListing(**shared, buyer='Autre acheteur')
    assert left.identity != right.identity


def test_transient_http_failure_is_retried():
    class Response:
        headers = {'Content-Type': 'text/html; charset=utf-8'}

        def read(self, limit):
            return result_page([row(1, **SETTAT)], state='s', pages=1).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Opener:
        def __init__(self):
            self.calls = 0

        def open(self, request, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise URLError('timed out')
            return Response()

    opener = Opener()
    http = PmmpHttp(opener=opener, delay_seconds=0, retries=3, sleep=lambda delay: None)
    crawl = PmmpListingCollector(http).collect()
    assert opener.calls == 2
    assert crawl.observations[0].state == NEW


def test_collection_does_not_call_paid_search_or_openai():
    text = MODULE.read_text(encoding='utf-8')
    assert 'openai' not in text.lower()
    assert 'SearchProvider' not in text
    http = ScriptedHttp([result_page([row(1, **SETTAT)], state='s', pages=1)])
    new_pmmp_collector(http=http)
    assert [call[0] for call in http.calls] == ['GET']


def test_search_form_is_submitted_before_listing_pages_are_read():
    form = (
        '<input name="PRADO_PAGESTATE" value="form-state">'
        f'<input name="{SEARCH_BUTTON}" value="Lancer la recherche">'
    )
    http = ScriptedHttp([form, result_page([row(1, **SETTAT)], state='results', pages=1)])
    crawl = PmmpListingCollector(http).collect()
    assert http.calls[0][0] == 'GET'
    assert http.calls[1] == ('POST', LISTING_URL, '')
    listing = crawl.observations[0].listing
    assert listing.reference == '04/2026/AUS'
    assert 'valorisation du patrimoine' in listing.title
    assert listing.consultation_id == '1036481'
    assert listing.detail_url.startswith('https://www.marchespublics.gov.ma/')


def test_known_settat_notice_is_visible_on_a_later_page_without_a_hardcoded_query():
    text = MODULE.read_text(encoding='utf-8')
    assert '04/2026/AUS' not in text
    assert 'Settat' not in text
    noise = row(1, consultation_id='1', organization='aaa', reference='01/2026',
                title='Fourniture de vehicules', buyer='Ministere', location='RABAT')
    pages = [
        result_page([noise], state='p1', pages=2, nxt=True, results=2),
        result_page([row(1, **SETTAT)], state='p2', pages=2, results=2),
    ]
    crawl = new_pmmp_collector(http=ScriptedHttp(pages), mode='full')
    matched = [item for item in crawl.observations if item.listing.reference == '04/2026/AUS']
    assert len(matched) == 1
    assert matched[0].state == NEW
    assert 'province de Settat' in matched[0].listing.title
