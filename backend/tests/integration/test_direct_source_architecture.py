import json
from email.message import Message
from urllib.error import HTTPError

from backend.app.integrations.http.adapters import BaseSourceAdapter, SourceDefinition, normalized_item_hash


class Response:
    def __init__(self, body, content_type='text/html', headers=None):
        self.body = body
        self.headers = Message()
        self.headers['Content-Type'] = content_type
        for key, value in (headers or {}).items():
            self.headers[key] = value
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, _): return self.body
    def geturl(self): return 'https://example.gov.ma/index'


class Opener:
    def __init__(self, response): self.response = response; self.request = None
    def open(self, request, timeout): self.request = request; return self.response


class State:
    def __init__(self, value=None, due=True): self.value=value or {}; self.due=due; self.saved=[]
    def get(self, _): return self.value
    def refresh_due(self, *_): return self.due
    def record(self, result): self.saved.append(result)


def test_html_adapter_hashes_meaningful_list_items():
    opener = Opener(Response(b'<nav>noise</nav><a href="/p/1">Convention signee pour rehabilitation medina</a>'))
    adapter = BaseSourceAdapter(SourceDefinition('Official', 'https://example.gov.ma/index'),
                                ('example.gov.ma',), opener=opener)
    result = adapter.fetch()
    assert result.status == 'CHANGED'
    assert result.items[0]['url'] == 'https://example.gov.ma/p/1'
    assert result.content_hash == normalized_item_hash(result.items)


def test_conditional_headers_and_304_skip_processing():
    state = State({'etag': 'abc', 'last_modified': 'Mon, 01 Jan 2024 00:00:00 GMT', 'content_hash': 'old'})
    error = HTTPError('https://example.gov.ma/index', 304, 'not modified', {}, None)
    opener = Opener(None)
    def fail(request, timeout): opener.request=request; raise error
    opener.open = fail
    adapter = BaseSourceAdapter(SourceDefinition('Official', 'https://example.gov.ma/index'),
                                ('example.gov.ma',), opener=opener, state=state)
    result = adapter.fetch()
    assert result.status == 'NOT_MODIFIED' and result.items == []
    assert opener.request.get_header('If-none-match') == 'abc'


def test_refresh_interval_skips_http_entirely():
    opener = Opener(Response(b''))
    state = State({'content_hash': 'same'}, due=False)
    result = BaseSourceAdapter(SourceDefinition('Stable', 'https://example.gov.ma/index'),
        ('example.gov.ma',), opener=opener, state=state).fetch()
    assert result.status == 'UNCHANGED' and opener.request is None and result.http_requests == 0


def test_json_api_extracts_structured_project_fields_without_ai():
    body = json.dumps({'projects': [{'id': 'P1', 'project_name': 'Morocco urban rehabilitation',
                                    'approval_date': '2026-01-01', 'url': 'https://example.gov.ma/p1'}]}).encode()
    adapter = BaseSourceAdapter(SourceDefinition('API', 'https://example.gov.ma/index', parser_type='JSON_API'),
                                ('example.gov.ma',), opener=Opener(Response(body, 'application/json')))
    item = adapter.fetch().items[0]
    assert item['reference'] == 'P1' and item['date'] == '2026-01-01'
