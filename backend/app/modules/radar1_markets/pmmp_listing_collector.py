"""PMMP listing collector for Radar 1 discovery coverage.

This module reads public consultation listings over HTTP and compares them
locally. It does not apply the ARCHERITAGE acceptance policy and it does not
call a model or paid web search. Production Radar 1 still uses
MarketsCollector.legacy_discovery until this collector is validated.
"""
from dataclasses import dataclass, field
import logging
import re
import time
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from app.core.dedup import digest, normalize_text
from app.integrations.pmmp.client import canonical_detail_url

logger = logging.getLogger(__name__)

SOURCE = 'marchespublics.gov.ma'
LISTING_URL = (
    'https://www.marchespublics.gov.ma/index.php?'
    'page=entreprise.EntrepriseAdvancedSearch&searchAnnCons'
)
SEARCH_BUTTON = 'ctl0$CONTENU_PAGE$AdvancedSearch$lancerRecherche'
NEXT_TARGET = 'ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2'
NEXT_HREF = 'javascript:;//ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2'
USER_AGENT = 'ArcheritageRadar/1.0'
MODES = ('full', 'incremental', 'reconciliation')
NEW = 'NEW'
UPDATED = 'UPDATED'
UNCHANGED = 'UNCHANGED'
DUPLICATE = 'DUPLICATE'
_TRANSIENT_HTTP = {500, 502, 503, 504}
_DATE = re.compile(r'\b(\d{2}/\d{2}/\d{4})(?:\s+(\d{2}:\d{2}))?\b')
_PAGE_STATE = re.compile(r'name="PRADO_PAGESTATE"[^>]*value="([^"]+)"')
_PAGE_COUNT = re.compile(
    r'id="ctl0_CONTENU_PAGE_resultSearch_nombrePageTop"[^>]*>\s*(\d+)')
_RESULT_COUNT = re.compile(
    r'id="ctl0_CONTENU_PAGE_resultSearch_nombreElement"[^>]*>\s*(\d+)')
_REF = re.compile(
    r'name="ctl0\$CONTENU_PAGE\$resultSearch\$tableauResultSearch\$ctl(\d+)\$refCons"'
    r'[^>]*value="(\d+)"')
_ORG = re.compile(
    r'name="ctl0\$CONTENU_PAGE\$resultSearch\$tableauResultSearch\$ctl(\d+)\$orgCons"'
    r'[^>]*value="([A-Za-z0-9]+)"')
_CATEGORY = re.compile(r'\b(Travaux|Services|Fournitures)\b', re.I)


class PmmpListingError(RuntimeError):
    """A public listing page could not be collected."""


@dataclass(frozen=True)
class PmmpListing:
    """Fields actually present on a PMMP result row. Missing values stay None."""
    source: str
    consultation_id: str | None
    organization: str | None
    reference: str | None
    title: str | None
    buyer: str | None
    publication_date: str | None
    deadline: str | None
    procedure: str | None
    category: str | None
    location: str | None
    detail_url: str | None
    estimated_amount: str | None = None

    @property
    def identity(self):
        if self.consultation_id and self.organization:
            return digest(['pmmp-id', self.source, self.consultation_id, self.organization])
        if self.detail_url:
            return digest(['pmmp-url', canonical_detail_url(self.detail_url)])
        return digest([
            'pmmp-ref', self.source, normalize_text(self.reference), normalize_text(self.buyer),
        ])

    @property
    def fingerprint(self):
        return digest([
            normalize_text(self.title), normalize_text(self.buyer), self.deadline,
            self.publication_date, normalize_text(self.procedure), normalize_text(self.category),
            normalize_text(self.location), self.detail_url, normalize_text(self.reference),
            normalize_text(self.estimated_amount),
        ])


@dataclass
class ListingObservation:
    listing: PmmpListing
    state: str


@dataclass
class ListingIndex:
    """In-memory baseline of listing identity to content fingerprint.

    Callers can round-trip this with to_dict and from_dict. Durable storage
    across process restarts is not a current table; see the phase-1 note.
    """
    records: dict = field(default_factory=dict)

    def classify(self, listing):
        previous = self.records.get(listing.identity)
        self.records[listing.identity] = listing.fingerprint
        if previous is None:
            return NEW
        if previous == listing.fingerprint:
            return UNCHANGED
        return UPDATED

    def to_dict(self):
        return dict(self.records)

    @classmethod
    def from_dict(cls, records):
        return cls(dict(records or {}))


@dataclass
class ListingCrawl:
    observations: list
    index: ListingIndex
    pages_fetched: int
    stop_reason: str
    declared_pages: int | None
    declared_results: int | None
    mode: str


class PmmpHttp:
    """Plain HTTP for one public host. No browser, no paid API."""

    def __init__(self, *, delay_seconds=0.35, retries=3, timeout=25, sleep=time.sleep, opener=None):
        self.delay_seconds = delay_seconds
        self.retries = retries
        self.timeout = timeout
        self.sleep = sleep
        self.opener = opener or build_opener()
        self._sent = 0

    def get(self, url):
        return self._request(url, None)

    def post(self, url, fields):
        return self._request(url, urlencode(fields).encode())

    def _request(self, url, data):
        host = url.split('/')[2].split(':')[0].lower() if '://' in url else ''
        if host != SOURCE and not host.endswith('.' + SOURCE):
            raise PmmpListingError('Refusing a non-PMMP listing URL.')
        if self._sent and self.delay_seconds:
            self.sleep(self.delay_seconds)
        attempts = max(1, self.retries)
        last = None
        for attempt in range(1, attempts + 1):
            try:
                request = Request(url, data=data, headers={'User-Agent': USER_AGENT})
                if data is not None:
                    request.add_header('Content-Type', 'application/x-www-form-urlencoded')
                with self.opener.open(request, timeout=self.timeout) as response:
                    kind = response.headers.get('Content-Type', '')
                    if 'html' not in kind:
                        raise PmmpListingError('PMMP listing response was not HTML.')
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise PmmpListingError('PMMP listing page exceeds the size limit.')
                    self._sent += 1
                    charset = None
                    if hasattr(response.headers, 'get_content_charset'):
                        charset = response.headers.get_content_charset()
                    return raw.decode(charset or 'utf-8', errors='replace')
            except HTTPError as error:
                last = error
                if error.code not in _TRANSIENT_HTTP or attempt == attempts:
                    raise
            except (URLError, TimeoutError, OSError) as error:
                last = error
                if attempt == attempts:
                    raise
            logger.warning('pmmp_listing retry=%s error=%s', attempt, type(last).__name__)
            self.sleep(0.25 * attempt)
        raise PmmpListingError('PMMP listing request failed.')


class PmmpListingCollector:
    """Collect lightweight PMMP listings. Relevance stays outside this class."""

    def __init__(self, http=None, *, listing_url=LISTING_URL, delay_seconds=0.35, retries=3):
        self.http = http or PmmpHttp(delay_seconds=delay_seconds, retries=retries)
        self.listing_url = listing_url

    def collect(self, *, mode='full', index=None, overlap_pages=2, max_pages=None):
        if mode not in MODES:
            raise ValueError('mode must be full, incremental, or reconciliation.')
        if overlap_pages < 1:
            raise ValueError('overlap_pages must be at least 1.')
        index = index or ListingIndex()
        html = self._first_page()
        observations = []
        seen_pages = set()
        seen_ids = set()
        unchanged_pages = 0
        pages_fetched = 0
        declared_pages = _number(_PAGE_COUNT, html)
        declared_results = _number(_RESULT_COUNT, html)
        stop = 'final_page'
        while html:
            signature = _page_signature(html)
            if signature in seen_pages:
                stop = 'pagination_loop'
                logger.info('pmmp_listing stop=pagination_loop pages=%s', pages_fetched)
                break
            seen_pages.add(signature)
            rows = parse_listings(html)
            pages_fetched += 1
            declared_pages = _number(_PAGE_COUNT, html) or declared_pages
            declared_results = _number(_RESULT_COUNT, html) or declared_results
            page_changed = False
            for listing in rows:
                if listing.identity in seen_ids:
                    observations.append(ListingObservation(listing, DUPLICATE))
                    continue
                seen_ids.add(listing.identity)
                state = index.classify(listing)
                page_changed = page_changed or state != UNCHANGED
                observations.append(ListingObservation(listing, state))
            logger.info(
                'pmmp_listing mode=%s page=%s rows=%s has_next=%s declared_pages=%s',
                mode, pages_fetched, len(rows), _has_next(html), declared_pages)
            if mode == 'incremental':
                unchanged_pages = 0 if page_changed or not rows else unchanged_pages + 1
                if rows and unchanged_pages >= overlap_pages:
                    stop = 'incremental_overlap'
                    break
            if not rows and not _has_next(html):
                stop = 'empty_page'
                break
            if max_pages is not None and pages_fetched >= max_pages:
                stop = 'max_pages'
                break
            if not _has_next(html):
                stop = 'final_page'
                break
            if declared_pages is not None and pages_fetched >= declared_pages:
                stop = 'final_page'
                break
            html = self._next_page(html)
        logger.info('pmmp_listing stop=%s pages=%s observations=%s', stop, pages_fetched, len(observations))
        return ListingCrawl(
            observations=observations, index=index, pages_fetched=pages_fetched,
            stop_reason=stop, declared_pages=declared_pages,
            declared_results=declared_results, mode=mode)

    def _first_page(self):
        html = self.http.get(self.listing_url)
        if _is_result_page(html):
            return html
        if SEARCH_BUTTON not in html or not _PAGE_STATE.search(html):
            raise PmmpListingError('PMMP page is neither a result list nor the consultation search form.')
        return self.http.post(self.listing_url, {
            'PRADO_PAGESTATE': _PAGE_STATE.search(html).group(1),
            'PRADO_POSTBACK_TARGET': '',
            'PRADO_POSTBACK_PARAMETER': '',
            SEARCH_BUTTON: 'Lancer la recherche',
        })

    def _next_page(self, html):
        state = _PAGE_STATE.search(html)
        if not state:
            raise PmmpListingError('PMMP result page has no page state for the next page.')
        return self.http.post(self.listing_url, {
            'PRADO_PAGESTATE': state.group(1),
            'PRADO_POSTBACK_TARGET': NEXT_TARGET,
            'PRADO_POSTBACK_PARAMETER': '',
        })


def new_pmmp_collector(*, http=None, index=None, mode='full', overlap_pages=2,
                       listing_url=LISTING_URL, delay_seconds=0.35, max_pages=None):
    """Side-by-side entry. Not used by the production Radar 1 run."""
    return PmmpListingCollector(http, listing_url=listing_url, delay_seconds=delay_seconds).collect(
        mode=mode, index=index, overlap_pages=overlap_pages, max_pages=max_pages)


def parse_listings(html):
    organizations = {int(index): value for index, value in _ORG.findall(html)}
    rows = []
    for index, consultation_id in _REF.findall(html):
        number = int(index)
        if number == 0:
            continue
        organization = organizations.get(number)
        reference = _clean(_field(html, number, 'reference'))
        title = _after(_field(html, number, 'panelBlocObjet'), 'objet')
        if not title:
            title = _after(_field(html, number, 'infosBullesObjet'), 'objet')
        buyer = _after(_field(html, number, 'panelBlocDenomination'), 'acheteur public')
        deadline = _date_text(_field(html, number, 'infosLieuExecutionLtRef'))
        category_block = _field(html, number, 'panelBlocCategorie')
        procedure_block = _field(html, number, 'panelBlocTypesProc')
        category = _category(category_block) or _category(procedure_block)
        procedure = _procedure(procedure_block, category)
        publication = _date_text(category_block) or _date_text(procedure_block)
        if publication and deadline and publication == deadline:
            publication = None
        location = _location(_field(html, number, 'infosLieuExecution'))
        detail = None
        if consultation_id and organization:
            detail = canonical_detail_url(
                'https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation'
                f'&refConsultation={consultation_id}&orgAcronyme={organization}')
        rows.append(PmmpListing(
            source=SOURCE, consultation_id=consultation_id, organization=organization,
            reference=reference, title=title, buyer=buyer, publication_date=publication,
            deadline=deadline, procedure=procedure, category=category, location=location,
            detail_url=detail, estimated_amount=None))
    return rows


def _is_result_page(html):
    return 'tableauResultSearch' in html and 'nombreElement' in html


def _has_next(html):
    return NEXT_HREF in html


def _page_signature(html):
    return tuple(_REF.findall(html))


def _number(pattern, html):
    match = pattern.search(html)
    return int(match.group(1)) if match else None


def _field(html, index, suffix):
    marker = f'id="ctl0_CONTENU_PAGE_resultSearch_tableauResultSearch_ctl{index}_{suffix}"'
    start = html.find(marker)
    if start < 0:
        return ''
    start = html.find('>', start)
    if start < 0:
        return ''
    start += 1
    nxt = html.find('id="ctl0_CONTENU_PAGE_resultSearch_tableauResultSearch_ctl', start)
    if nxt > 0:
        nxt = html.rfind('<', start, nxt)
    chunk = html[start:nxt if nxt > 0 else start + 4000]
    text = re.sub(r'<[^>]+>', ' ', chunk)
    return unescape(re.sub(r'\s+', ' ', text)).strip()


def _clean(value):
    value = (value or '').strip(' :')
    return value or None


def _after(value, label):
    text = _clean(value)
    if not text:
        return None
    folded = normalize_text(text)
    prefix = normalize_text(label)
    if folded.startswith(prefix):
        text = text[len(label):].strip(' :')
    return text or None


def _date_text(value):
    match = _DATE.search(value or '')
    if not match:
        return None
    return f'{match.group(1)} {match.group(2)}' if match.group(2) else match.group(1)


def _category(value):
    match = _CATEGORY.search(value or '')
    return match.group(1).capitalize() if match else None


def _procedure(value, category):
    text = _clean(value)
    if not text:
        return None
    if category:
        text = re.split(re.escape(category), text, maxsplit=1, flags=re.I)[0]
    text = _DATE.sub('', text)
    text = _clean(re.sub(r'\s+', ' ', text))
    return text


def _location(value):
    text = _clean(value)
    if not text:
        return None
    text = text.split('...')[0]
    text = _clean(re.sub(r'\s+', ' ', text))
    return text
