"""Durable PMMP listing index: baseline, incremental, and reconciliation."""
from pathlib import Path

from app.db.extensions import db
from app.db.models import Result
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.modules.radar1_markets.pmmp_listing_collector import (
    LISTING_URL, NEW, NEXT_HREF, NEXT_TARGET, SEARCH_BUTTON, SOURCE, UNCHANGED, UPDATED,
    PmmpListing,
)
from app.modules.radar1_markets.pmmp_listing_index import (
    DurableListingIndex, actionable_listings, import_baseline, sync_listings,
)


MODULE = Path(__file__).resolve().parents[3] / 'app' / 'modules' / 'radar1_markets' / 'pmmp_listing_index.py'


def listing(**changes):
    values = dict(
        source=SOURCE, consultation_id='1036481', organization='j8k',
        reference='04/2026/AUS',
        title='Etude de valorisation du patrimoine culturel de Settat',
        buyer='Agence urbaine de Settat', publication_date='03/09/2026',
        deadline='02/10/2026 11:00', procedure="Appel d'offres ouvert",
        category='Services', location='SETTAT',
        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                    'page=entreprise.EntrepriseDetailsConsultation'
                    '&refConsultation=1036481&orgAcronyme=j8k'),
    )
    values.update(changes)
    return PmmpListing(**values)


def row(index, item):
    prefix = f'ctl0_CONTENU_PAGE_resultSearch_tableauResultSearch_ctl{index}'
    name = f'ctl0$CONTENU_PAGE$resultSearch$tableauResultSearch$ctl{index}'
    return (
        f'<input name="{name}$refCons" value="{item.consultation_id}">'
        f'<input name="{name}$orgCons" value="{item.organization}">'
        f'<span id="{prefix}_reference">{item.reference}</span>'
        f'<span id="{prefix}_panelBlocObjet">Objet : {item.title}</span>'
        f'<span id="{prefix}_panelBlocDenomination">Acheteur public : {item.buyer}</span>'
        f'<span id="{prefix}_infosLieuExecutionLtRef">{item.deadline}</span>'
        f'<span id="{prefix}_panelBlocCategorie">{item.category} {item.publication_date}</span>'
        f'<span id="{prefix}_panelBlocTypesProc">{item.procedure} {item.category} {item.publication_date}</span>'
        f'<span id="{prefix}_infosLieuExecution">{item.location or ""} ...</span>'
    )


def result_page(items, *, state, pages, nxt=False):
    pager = f'<a href="{NEXT_HREF}"></a>' if nxt else ''
    body = ''.join(row(index, item) for index, item in enumerate(items, start=1))
    return (
        f'<input name="PRADO_PAGESTATE" value="{state}">'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombreElement">{len(items)}</span>'
        f'<span id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop">{pages}</span>'
        f'<div id="tableauResultSearch">{body}</div>{pager}'
    )


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


def test_baseline_insert_creates_index_rows_not_business_results(app):
    with app.app_context():
        result = import_baseline([listing(), listing(
            consultation_id='1', organization='a1t', reference='01/2026',
            title='Autre', buyer='Commune', detail_url=None)])
        assert result.counts == {NEW: 2}
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 2
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 0
        assert [item.state for item in result.actionable] == [NEW, NEW]


def test_unchanged_second_baseline_updates_last_seen(app):
    with app.app_context():
        first = import_baseline([listing()])
        row = db.session.scalar(db.select(PmmpListingIndex))
        first_seen = row.first_seen_at
        first_changed = row.last_changed_at
        first_last = row.last_seen_at
        second = import_baseline([listing()])
        db.session.refresh(row)
        assert second.counts == {UNCHANGED: 1}
        assert second.actionable == []
        assert row.first_seen_at == first_seen
        assert row.last_changed_at == first_changed
        assert row.last_seen_at >= first_last
        assert first.counts[NEW] == 1


def test_updated_listing_changes_fingerprint_and_last_changed(app):
    with app.app_context():
        import_baseline([listing()])
        row = db.session.scalar(db.select(PmmpListingIndex))
        before = row.last_changed_at
        fingerprint = row.fingerprint
        result = import_baseline([listing(deadline='15/11/2026 18:00')])
        db.session.refresh(row)
        assert result.counts == {UPDATED: 1}
        assert len(result.actionable) == 1
        assert row.fingerprint != fingerprint
        assert row.deadline == '15/11/2026 18:00'
        assert row.last_changed_at >= before


def test_duplicate_pmmp_consultation_id_does_not_insert_a_second_row(app):
    with app.app_context():
        first = listing()
        twin = listing(organization='zzz', title='Same id different org text')
        # Same consultation_id must resolve to one durable row.
        assert first.consultation_id == twin.consultation_id
        import_baseline([first])
        result = import_baseline([twin])
        assert result.counts[UPDATED] == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 1
        row = db.session.scalar(db.select(PmmpListingIndex))
        assert row.organization == 'zzz'


def test_fallback_identity_without_consultation_id(app):
    with app.app_context():
        left = listing(consultation_id=None, organization=None, detail_url=None,
                       reference='04/2026/AUS', buyer='Province de Settat')
        right = listing(consultation_id=None, organization=None, detail_url=None,
                        reference='04/2026/AUS', buyer='Autre acheteur')
        assert left.identity != right.identity
        result = import_baseline([left, right])
        assert result.counts == {NEW: 2}
        assert db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex)) == 2


def test_incremental_overlap_and_actionable_handoff(app):
    with app.app_context():
        known = listing()
        older = listing(consultation_id='2', organization='bbb', reference='02/2026',
                        title='Ancienne notice', buyer='Agence', location='OUJDA',
                        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                                    'page=entreprise.EntrepriseDetailsConsultation'
                                    '&refConsultation=2&orgAcronyme=bbb'))
        import_baseline([known, older])
        fresh = listing(consultation_id='9', organization='zzz', reference='99/2026',
                        title='Nouvelle consultation', buyer='Commune', location='FES',
                        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                                    'page=entreprise.EntrepriseDetailsConsultation'
                                    '&refConsultation=9&orgAcronyme=zzz'))
        pages = [
            result_page([fresh], state='p1', pages=9, nxt=True),
            result_page([known], state='p2', pages=9, nxt=True),
            result_page([older], state='p3', pages=9, nxt=True),
            result_page([
                listing(consultation_id='8', organization='yyy', reference='88/2026',
                        title='Should not be fetched', buyer='X', location='X',
                        detail_url=None),
            ], state='p4', pages=9, nxt=True),
        ]
        http = ScriptedHttp(pages)
        result = sync_listings(mode='incremental', overlap_pages=2, http=http, delay_seconds=0)
        assert result.stop_reason == 'incremental_overlap'
        assert result.pages_fetched == 3
        assert result.counts[NEW] == 1
        assert result.counts[UNCHANGED] == 2
        assert [item.listing.consultation_id for item in result.actionable] == ['9']
        assert len(http.pages) == 1
        assert actionable_listings(result)[0].state == NEW


def test_reconciliation_walks_past_known_pages(app):
    with app.app_context():
        known = listing()
        import_baseline([known])
        pages = [
            result_page([known], state='p1', pages=2, nxt=True),
            result_page([
                listing(consultation_id='7', organization='qqq', reference='70/2026',
                        title='Older notice still open', buyer='Agence', location='TAZA',
                        detail_url=('https://www.marchespublics.gov.ma/index.php?'
                                    'page=entreprise.EntrepriseDetailsConsultation'
                                    '&refConsultation=7&orgAcronyme=qqq')),
            ], state='p2', pages=2),
        ]
        result = sync_listings(mode='reconciliation', overlap_pages=1,
                               http=ScriptedHttp(pages), delay_seconds=0)
        assert result.stop_reason == 'final_page'
        assert result.counts[UNCHANGED] == 1
        assert result.counts[NEW] == 1
        assert len(result.actionable) == 1


def test_restart_persistence_survives_new_session(app):
    with app.app_context():
        import_baseline([listing()])
        identity = db.session.scalar(db.select(PmmpListingIndex)).identity_key
        db.session.remove()
        again = import_baseline([listing()])
        assert again.counts == {UNCHANGED: 1}
        row = db.session.scalar(db.select(PmmpListingIndex).where(
            PmmpListingIndex.identity_key == identity))
        assert row is not None


def test_sync_does_not_call_paid_search_or_openai(app):
    text = MODULE.read_text(encoding='utf-8')
    assert 'openai' not in text.lower()
    assert 'SearchProvider' not in text
    with app.app_context():
        form = (
            '<input name="PRADO_PAGESTATE" value="form-state">'
            f'<input name="{SEARCH_BUTTON}" value="Lancer la recherche">'
        )
        http = ScriptedHttp([form, result_page([listing()], state='results', pages=1)])
        sync_listings(mode='full', http=http, delay_seconds=0)
        assert [call[0] for call in http.calls] == ['GET', 'POST']
        assert http.calls[1][1] == LISTING_URL
        assert http.calls[1][2] == ''


def test_durable_classify_matches_listing_index_contract(app):
    with app.app_context():
        index = DurableListingIndex()
        assert index.classify(listing()) == NEW
        assert index.classify(listing()) == UNCHANGED
        assert index.classify(listing(deadline='01/12/2026 09:00')) == UPDATED
        db.session.commit()
