"""Bounded GET-only evidence reader, used only by the Radar 3/4 verifiers."""
import json
import re
from io import BytesIO
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit, quote
from pypdf import PdfReader
from app.integrations.http.html import Page, NoRedirect


class VerificationPages:
    def __init__(self, domains, metrics, limit=8, timeout=20):
        self.domains, self.metrics, self.limit, self.timeout = domains, metrics, limit, timeout
        self.attempts = 0
        self.cache = {}

    def allowed(self, url):
        p = urlsplit(url); host = (p.hostname or '').lower().removeprefix('www.')
        return p.scheme in {'http','https'} and not p.username and not p.password and any(
            host == d or host.endswith('.'+d) for d in self.domains)

    def get(self, url, headers=None):
        if url in self.cache: return self.cache[url]
        if not self.allowed(url) or self.attempts >= self.limit: return None
        original = url
        self.cache[original] = None
        try:
            for _ in range(3):
                if self.attempts >= self.limit: return None
                self.attempts += 1
                self.metrics['direct_http_requests'] = self.metrics.get('direct_http_requests',0)+1
                try:
                    response = build_opener(NoRedirect).open(Request(quote(url,safe=':/?=&%+#'),
                        headers={'User-Agent':'ArcheritageRadar/2.0',**(headers or {})}),timeout=self.timeout)
                    break
                except HTTPError as error:
                    if error.code not in {301,302,303,307,308}: raise
                    url=urljoin(url,error.headers.get('Location',''))
                    if not self.allowed(url): return None
            else: return None
            with response:
                raw=response.read(5_000_001)
                if len(raw)>5_000_000: return None
                charset=response.headers.get_content_charset() or 'utf-8'
            if raw.startswith(b'%PDF'):
                reader=PdfReader(BytesIO(raw),strict=False)
                text='\n'.join(p.extract_text() or '' for p in reader.pages[:30])[:200000]
                result={'url':url,'text':text,'page':None,'kind':'pdf','raw':None}
            else:
                html=raw.decode(charset,errors='replace'); page=Page(html)
                body=re.split(r'</h1\s*>',html,maxsplit=1,flags=re.I)
                scoped=re.split(r'<(?:footer|aside)\b|<h[234]\b',body[1],maxsplit=1,flags=re.I)[0] if len(body)==2 else html
                result={'url':url,'text':Page(scoped).text,'page':page,'kind':'html','raw':html}
            self.cache[original]=result
            return result
        except Exception as error:
            # External parse/access errors affect this evidence source only.
            self.metrics['verification_source_errors']=self.metrics.get('verification_source_errors',0)+1
            return None
