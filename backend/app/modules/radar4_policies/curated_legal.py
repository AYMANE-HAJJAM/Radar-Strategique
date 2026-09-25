"""Reviewed legal references linking a bounded source corpus to official BOs."""
from datetime import date
from io import BytesIO
import hashlib
import re
from pypdf import PdfReader

HERITAGE_BO = 'https://www.sgg.gov.ma/BO/AR/3111/2025/BO_7415_Ar.pdf'
LEGAL_REGISTRY = {
    'heritage_33_22': {'reference':'33.22','title':'Loi n° 33.22 relative à la protection du patrimoine',
        'bo_url':HERITAGE_BO,'bo_number':'7415','publication_date':'2025-06-23',
        'refresh_days':30,'priority':0,'enabled':True,
        'date_provenance':'Official BO 7415, cover dated 23 June 2025; not promulgation date 6 June 2025'},
}

def arabic_publication_sections(text,entry):
    # PDF bidi extraction may put a reference before its Arabic label. Require
    # the promulgation formula, own reference, law label and subject together.
    from app.modules.radar4_policies.status_verification import reference, REF
    for m in re.finditer(r'ينفذ\s+وينشر\s+بالجريدة\s+الرسمية',text):
        block=text[m.start():m.start()+450]
        refs={reference(v) for v in re.findall(REF,block)}
        if entry['reference'] not in refs or 'القانون رقم' not in block or 'بحماية التراث' not in block:continue
        yield {'reference':entry['reference'],'document_type':'LAW','heading':entry['title'],
            'text':block,'evidence_excerpt':block}

def bo_items(key,raw):
    entry=LEGAL_REGISTRY[key]
    if not raw.startswith(b'%PDF'):return []
    reader=PdfReader(BytesIO(raw),strict=False)
    text='\n'.join(p.extract_text() or '' for p in reader.pages[:30])[:200000]
    # Prevent a changed endpoint serving a different bulletin from inheriting metadata.
    if not re.search(r'(?<!\d)'+entry['bo_number']+r'(?!\d)',text[:12000]):return []
    sections=list(arabic_publication_sections(text,entry))
    doc={'url':entry['bo_url'],'date':date.fromisoformat(entry['publication_date']),
        'bo_number':entry['bo_number'],'text':text,'sections':sections}
    return [{'title':entry['title'],'url':entry['bo_url'],'date':entry['publication_date'],
        'reference':hashlib.sha256(text.encode()).hexdigest(),'bo_document':True,'document':doc}]

def source_records():
    return tuple({'name':'BO '+e['bo_number']+' — '+e['title'],'index_url':e['bo_url'],
        'parser_type':'CURATED_BO:'+key,'refresh_days':e['refresh_days'],
        'priority':e['priority'],'enabled':e['enabled']} for key,e in LEGAL_REGISTRY.items())
