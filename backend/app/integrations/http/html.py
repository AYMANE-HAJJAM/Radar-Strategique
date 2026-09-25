"""Generic bounded HTML fetch helpers. No source-specific field extraction."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

from app.modules.radar1_markets.policy import domain_match


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.texts, self.links, self.rows = [], [], []
        self.anchor = None
        self.row = None
        self.cells = None
        self.cell = None
        self.table_rows = []
        self.row_parts = []
        self.row_links = []
        self.current_row_links = None
        self.hidden = 0
        self.has_form = False
        self.headings = []
        self.h1 = []
        self.in_h1 = False
        self.heading = False
        self.article_depth = 0
        self.article_parts = []
        self.article_links = []
        self.articles = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article':
            self.article_depth = 1
            self.article_parts, self.article_links = [], []
        elif self.article_depth:
            self.article_depth += 1
        if tag in {'script', 'style'}:
            self.hidden += 1
        if tag == 'form':
            self.has_form = True
        if tag in {'h1', 'title'}:
            self.heading = True
        if tag == 'h1':
            self.in_h1 = True
        if tag == 'tr':
            self.row = []
            self.cells = []
            self.current_row_links = []
        if tag in {'td', 'th'}:
            self.cell = []
        if tag == 'a':
            self.anchor = [attrs.get('href', ''), []]

    def handle_data(self, data):
        if self.hidden:
            return
        self.texts.append(data)
        if self.heading:
            self.headings.append(data)
        if self.in_h1:
            self.h1.append(data)
        if self.row is not None:
            self.row.append(data)
        if self.cell is not None:
            self.cell.append(data)
        if self.anchor is not None:
            self.anchor[1].append(data)
        if self.article_depth:
            self.article_parts.append(data)

    def handle_endtag(self, tag):
        if tag in {'h1', 'title'}:
            self.heading = False
        if tag == 'h1':
            self.in_h1 = False
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)
        if tag == 'a' and self.anchor is not None:
            self.links.append((self.anchor[0], ' '.join(self.anchor[1])))
            if self.article_depth:
                self.article_links.append(self.links[-1])
            if self.current_row_links is not None:
                self.current_row_links.append(self.links[-1])
            self.anchor = None
        if tag in {'td', 'th'} and self.cell is not None:
            if self.cells is not None:
                self.cells.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        if tag == 'tr' and self.row is not None:
            self.row_parts.append(self.row)
            self.row_links.append(self.current_row_links or [])
            self.current_row_links = None
            self.rows.append(' '.join(self.row))
            self.row = None
            self.table_rows.append(self.cells or [])
            self.cells = None
        if self.article_depth:
            self.article_depth -= 1
            if tag == 'article' and self.article_depth == 0:
                self.articles.append((' '.join(' '.join(self.article_parts).split()),
                                      list(self.article_links)))

    @property
    def text(self):
        return ' '.join(' '.join(self.texts).split())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicPages:
    def __init__(self, domains, timeout=20):
        self.domains = domains
        self.timeout = timeout
        self.cache = {}
        self.request_attempts = 0

    def get(self, url):
        if url in self.cache:
            return self.cache[url]
        original = url
        for _ in range(4):
            if not domain_match(url, self.domains) or urlsplit(url).scheme not in {'https', 'http'}:
                raise ValueError('Page outside whitelist')
            try:
                self.request_attempts += 1
                with build_opener(NoRedirect).open(Request(url, headers={'User-Agent': 'ArcheritageRadar/1.0'}), timeout=self.timeout) as response:
                    if 'html' not in response.headers.get('Content-Type', ''):
                        raise ValueError('Only public HTML inspected')
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000:
                        raise ValueError('Page exceeds limit')
                    page = Page(raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace'))
                    self.cache[original] = (url, page)
                    return url, page
            except HTTPError as error:
                if error.code not in {301, 302, 303, 307, 308}:
                    raise
                url = urljoin(url, error.headers.get('Location', ''))
        raise ValueError('Too many redirects')


class AccessLimitedPages:
    """One request per failed URL per run; a 429 stops that host for this run.

    A new scheduled run can retry. No sleeping or aggressive retry loop.
    Successful pages also cache, including injected page readers used by tests.
    """
    def __init__(self, reader, metrics, on_error=None):
        self.reader, self.metrics, self.on_error = reader, metrics, on_error or (lambda code: None)
        self.cache, self.errors, self.limited_hosts = {}, {}, {}

    def get(self, url):
        if url in self.cache:
            return self.cache[url]
        if url in self.errors:
            raise self.errors[url]
        host = urlsplit(url).hostname
        if host in self.limited_hosts:
            raise self.limited_hosts[host]
        try:
            value = self.reader.get(url)
            self.cache[url] = value
            return value
        except (OSError, ValueError, TimeoutError) as error:
            self.errors[url] = error
            code = getattr(error, 'code', None)
            if code in {403, 429}:
                self.metrics['http_' + str(code)] += 1
                self.on_error(code)
                if code == 429:
                    self.limited_hosts[host] = error
            raise
