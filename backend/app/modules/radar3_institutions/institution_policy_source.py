"""Evidence parsers used only by Radars 3 and 4."""
import re
import hashlib
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from app.integrations.http.adapters import BaseSourceAdapter
from app.integrations.http.html import Page


class InstitutionSourceAdapter(BaseSourceAdapter):
    def list_items(self, raw, content_type, charset='utf-8'):
        if self.definition.parser_type.startswith('CURATED_ROLE:'):
            from app.modules.radar3_institutions.curated_sources import role_items
            return role_items(self.definition.parser_type.split(':',1)[1],raw,charset)
        if self.definition.parser_type == 'GOVERNMENT_ROLES':
            from app.modules.radar3_institutions.policy import folded
            html=raw.decode(charset, errors='replace')
            items=[]
            for name,body in re.findall(r'<h3[^>]*>(.*?)</h3>\s*<div\s+class="paragraph--gouver">(.*?)</div>',html,re.I|re.S):
                name=Page(name).text;role=Page(body).text
                if not re.match(r'^M(?:me)?\.',name.strip()):continue
                if not role.strip().startswith('Ministre') or not any(t in folded(role) for t in ('urbanisme','culture')):continue
                person=re.sub(r'^M(?:me)?\.\s*','',name.strip())
                institution=re.sub(r'^Ministre','Ministère',role.strip())
                items.append({'title':institution,'institution':institution,'url':self.definition.index_url,
                    'evidence':role,'person_name':person,'role_title':role,'source_type':'GOVERNANCE',
                    'profile_evidence':True,'reference':hashlib.sha256((person+role).encode()).hexdigest()})
            return items
        if self.definition.parser_type != 'INSTITUTION_PROFILE':
            return super().list_items(raw, content_type, charset)
        html = raw.decode(charset, errors='replace')
        # Scope evidence to the page body after its H1; navigation/job links are not facts.
        body = re.split(r'</h1\s*>', html, maxsplit=1, flags=re.I)
        if len(body) != 2:
            return []
        body = re.split(r'<(?:footer|aside)\b|<h2\b', body[1], maxsplit=1, flags=re.I)[0]
        evidence = Page(body).text[:6000]
        if len(evidence) < 100:
            return []
        return [{'title': self.definition.name, 'url': self.definition.index_url,
            'evidence': evidence, 'institution': self.definition.name,
            'profile_evidence': True, 'reference': hashlib.sha256(evidence.encode()).hexdigest()}]


class PolicySourceAdapter(BaseSourceAdapter):
    def fetch(self):
        # Public SGG listing requires only its published module/tab identifiers.
        if self.definition.parser_type == 'BO_PUBLICATIONS':
            original=self.opener
            class HeaderOpener:
                def open(self, request, **kwargs):
                    request.add_header('ModuleId','2873'); request.add_header('TabId','775')
                    return original.open(request,**kwargs)
            self.opener=HeaderOpener()
            try:return super().fetch()
            finally:self.opener=original
        return super().fetch()

    def list_items(self, raw, content_type, charset='utf-8'):
        if self.definition.parser_type.startswith('CURATED_BO:'):
            from app.modules.radar4_policies.curated_legal import bo_items
            items=bo_items(self.definition.parser_type.split(':',1)[1],raw)
            if not items or not items[0]['document']['sections']:
                raise ValueError('curated_bo_reference_not_readable')
            return items
        if self.definition.parser_type == 'PARLIAMENT_STAGE':
            from app.modules.radar4_policies.legislative_progress import parliament_items
            items=parliament_items(raw,self.definition.index_url,charset)
            return items or super().list_items(raw,content_type,charset)
        if self.definition.parser_type == 'SGG_CONSOLIDATED':
            page=Page(raw.decode(charset,errors='replace'))
            return [{'title':label.removeprefix('La '),'url':urljoin(self.definition.index_url,href),
                     'evidence':label+' — Version consolidée SGG ; statut actuel à vérifier.', 'consolidated_lookup':True}
                    for href,label in page.links if '/textesconsolides/' in href.lower() and label.startswith('La loi')]
        if self.definition.parser_type == 'BO_PUBLICATIONS':
            rows=json.loads(raw.decode(charset))
            items=[]
            for row in sorted(rows,key=lambda r:int(re.search(r'-?\d+',r['BoDate']).group()),reverse=True)[:2]:
                stamp=int(re.search(r'-?\d+',row['BoDate']).group())/1000
                items.append({'title':'Bulletin Officiel '+row['BoNum'],'url':urljoin(self.definition.index_url,row['BoUrl']),
                    'date':(datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(seconds=stamp)).astimezone(ZoneInfo('Africa/Casablanca')).date().isoformat(),
                    'reference':row['BoNum'],'bo_document':True})
            return items
        if self.definition.parser_type != 'SGG_DRAFT_TABLE':
            return super().list_items(raw, content_type, charset)
        html = raw.decode(charset, errors='replace')
        page = Page(html)
        items = []
        rows = list(zip(page.table_rows, page.row_links))
        # Current SGG uses div.repeater with column list items, not HTML tables.
        for block in re.split(r'<div\s+class=[\"\']repeater[\"\']\s*>', html, flags=re.I)[1:]:
            heading = re.search(r'<li\s+class=[\"\']?col1[\"\']?\s*>\s*<p>(.*?)</p>', block, re.I | re.S)
            if heading:
                rows.append(([Page(heading.group(1)).text], Page(block.split('</div>', 1)[0]).links))
        for cells, links in rows:
            # The SGG list labels instrument type separately from the exact title.
            kind = next((cell.strip() for cell in cells if cell.strip() in {'Loi', 'Décret', 'Arrêté'}), None)
            if not kind:
                continue
            for href, label in links:
                title = ' '.join(label.split())
                target = urljoin(self.definition.index_url, href)
                if len(title) < 25 or not target.lower().endswith('.pdf'):
                    continue
                items.append({'title': title, 'url': target, 'evidence': f'Projet de {kind.lower()} : {title}',
                    'draft_listing': True, 'listing_url': self.definition.index_url,
                    'document_type': {'Loi': 'DRAFT_LAW', 'Décret': 'DECREE', 'Arrêté': 'ORDER'}[kind]})
        return items
