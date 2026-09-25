"""Reusable direct-source ingestion with conditional HTTP and meaningful list hashing."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener

from app.integrations.http.html import NoRedirect, Page


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    index_url: str
    source_type: str = 'official'
    parser_type: str = 'HTML_LIST'
    refresh_days: int = 7
    priority: int = 50
    enabled: bool = True


@dataclass
class SourceFetch:
    source: SourceDefinition
    url: str
    status: str
    items: list[dict] = field(default_factory=list)
    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    http_requests: int = 0
    error_code: int | None = None


def normalized_item_hash(items):
    identities = sorted('|'.join(str(item.get(key) or '').strip().casefold()
                       for key in ('title', 'date', 'reference', 'url')) for item in items)
    return hashlib.sha256('\n'.join(identities).encode()).hexdigest()


class BaseSourceAdapter:
    """GET-only source adapter. State storage is injected and can be DB backed."""
    def __init__(self, definition, domains, *, timeout=20, state=None, opener=None):
        self.definition = definition
        self.domains = tuple(domains)
        self.timeout = timeout
        self.state = state
        self.opener = opener or build_opener(NoRedirect)

    def _allowed(self, url):
        host = (urlsplit(url).hostname or '').lower().removeprefix('www.')
        return urlsplit(url).scheme in {'http', 'https'} and any(
            host == domain or host.endswith('.' + domain) for domain in self.domains)

    def fetch(self):
        source = self.definition
        if not source.enabled or not self._allowed(source.index_url):
            return SourceFetch(source, source.index_url, 'FAILED')
        previous = self.state.get(source.index_url) if self.state else {}
        if self.state and not self.state.refresh_due(source.index_url, source.refresh_days):
            status = 'COOLDOWN' if previous.get('health') in {'BLOCKED', 'FAILED'} else 'UNCHANGED'
            return SourceFetch(source, source.index_url, status, content_hash=previous.get('content_hash'))
        headers = {'User-Agent': 'ArcheritageRadar/2.0'}
        if previous.get('etag'):
            headers['If-None-Match'] = previous['etag']
        if previous.get('last_modified'):
            headers['If-Modified-Since'] = previous['last_modified']
        try:
            url = source.index_url
            response = None
            for _ in range(4):
                try:
                    response = self.opener.open(Request(url, headers=headers), timeout=self.timeout)
                    break
                except HTTPError as error:
                    if error.code not in {301, 302, 303, 307, 308}:
                        raise
                    target = urljoin(url, error.headers.get('Location', ''))
                    if not self._allowed(target):
                        raise ValueError('redirect_outside_source_domains')
                    url = target
            if response is None:
                raise ValueError('too_many_redirects')
            with response:
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise ValueError('source_page_too_large')
                content_type = response.headers.get('Content-Type', '').lower()
                items = self.list_items(raw, content_type, response.headers.get_content_charset() or 'utf-8')
                digest = normalized_item_hash(items)
                status = 'UNCHANGED' if previous.get('content_hash') == digest else 'CHANGED'
                result = SourceFetch(source, response.geturl(), status, items, digest,
                    response.headers.get('ETag'), response.headers.get('Last-Modified'), 1)
                if self.state:
                    self.state.record(result)
                return result
        except HTTPError as error:
            if error.code == 304:
                result = SourceFetch(source, source.index_url, 'NOT_MODIFIED',
                    content_hash=previous.get('content_hash'), etag=previous.get('etag'),
                    last_modified=previous.get('last_modified'), http_requests=1, error_code=304)
                if self.state:
                    self.state.record(result)
                return result
            status = 'BLOCKED' if error.code in {403, 429} else 'FAILED'
            result = SourceFetch(source, source.index_url, status, http_requests=1, error_code=error.code)
            if self.state:
                self.state.record(result)
            return result
        except (OSError, TimeoutError, ValueError):
            result = SourceFetch(source, source.index_url, 'FAILED', http_requests=1)
            if self.state:
                self.state.record(result)
            return result

    def list_items(self, raw, content_type, charset='utf-8'):
        parser = self.definition.parser_type.upper()
        if parser == 'JSON_API' or 'json' in content_type:
            return self._json_items(json.loads(raw.decode(charset, errors='replace')))
        text = raw.decode(charset, errors='replace')
        if parser in {'RSS', 'ATOM'} or 'xml' in content_type:
            return self._feed_items(text)
        page = Page(text)
        if parser == 'TABLE':
            items = []
            for index, cells in enumerate(page.table_rows):
                title = ' '.join(cell for cell in cells if cell).strip()
                links = page.row_links[index] if index < len(page.row_links) else []
                if len(title) >= 18:
                    items.append({'title': title[:1000],
                        'url': urljoin(self.definition.index_url, links[0][0]) if links else self.definition.index_url,
                        'evidence': title[:2000]})
            if items:
                return items[:250]
        items = []
        for href, label in page.links:
            title = ' '.join(label.split())
            if len(title) >= 18:
                items.append({'title': title[:1000], 'url': urljoin(self.definition.index_url, href),
                              'evidence': title[:2000]})
        return items[:250]

    def _feed_items(self, text):
        blocks = re.findall(r'<(?:item|entry)\b.*?</(?:item|entry)>', text, re.I | re.S)
        output = []
        for block in blocks:
            def value(tag):
                match = re.search(fr'<{tag}\b[^>]*>(.*?)</{tag}>', block, re.I | re.S)
                return re.sub('<[^>]+>', ' ', match.group(1)).strip() if match else None
            link = value('link')
            if not link:
                match = re.search(r'<link\b[^>]*href=["\']([^"\']+)', block, re.I)
                link = match.group(1) if match else None
            output.append({'title': value('title') or '', 'url': link or self.definition.index_url,
                           'date': value('pubDate') or value('updated'),
                           'evidence': value('description') or value('summary') or ''})
        return output[:250]

    def _json_items(self, value):
        if isinstance(value, dict):
            value = next((value[key] for key in ('projects', 'items', 'results', 'data')
                          if isinstance(value.get(key), (list, dict))), [])
        if isinstance(value, dict):
            value = list(value.values())
        if not isinstance(value, list):
            return []
        output = []
        for item in value[:500]:
            if not isinstance(item, dict):
                continue
            title = next((item.get(k) for k in ('project_name', 'name', 'title', 'projectName') if item.get(k)), '')
            url = next((item.get(k) for k in ('url', 'link', 'project_url') if item.get(k)), self.definition.index_url)
            output.append({'title': str(title), 'url': str(url), 'date': item.get('approval_date') or item.get('boardapprovaldate') or item.get('date'),
                           'reference': item.get('id') or item.get('project_id'),
                           'evidence': json.dumps(item, ensure_ascii=False)[:4000], 'raw': item})
        return output


def build_source_adapters(records, domains, **kwargs):
    definitions = [record if isinstance(record, SourceDefinition) else SourceDefinition(**record) for record in records]
    return [BaseSourceAdapter(item, domains, **kwargs) for item in sorted(definitions, key=lambda x: x.priority) if item.enabled]
