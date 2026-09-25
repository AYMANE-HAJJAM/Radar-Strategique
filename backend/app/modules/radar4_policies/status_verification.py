"""Official instrument evidence, with publication distinct from effectiveness."""
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit
from app.modules.radar4_policies.policy import folded
from app.modules.radar3_institutions.leadership import evidence_date

REF=r'\d+(?:\s*[./\-٫]\s*\d+)+'

def reference(value):
    value=unicodedata.normalize('NFKC',value or '')
    value=''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value)
    return re.sub(r'\s+','',re.sub(r'[./\-٫]','.',value))

def document_sections(doc):
    return doc['sections'] if 'sections' in doc else instrument_sections(doc['text'])

def official_bo(url):
    p=urlsplit(url);host=(p.hostname or '').removeprefix('www.')
    return host=='sgg.gov.ma' and '/bo/' in p.path.lower() and p.path.lower().endswith('.pdf')

def instrument_sections(text, include_drafts=False):
    # Require a legal heading on its own line, not an incidental mention of a law.
    pattern=rf'(?im)^\s*((?:projet de |avant-projet de )?)(Dahir|Décret|Arrêté|Loi)\s+n[°ºo]?\s*({REF})\b'
    matches=list(re.finditer(pattern,text))
    for i,m in enumerate(matches):
        if m[1] and not include_drafts:continue
        block=text[m.start():matches[i+1].start() if i+1<len(matches) else len(text)][:12000]
        heading=' '.join(block[:1400].split())
        own=m[3];kind={'dahir':'LAW','loi':'LAW','décret':'DECREE','arrêté':'ORDER'}[m[2].lower()]
        if m[2].lower()=='dahir':
            law=re.search(rf'promulgation de la loi\s+n[°ºo]?\s*({REF})',heading,re.I)
            if not law:continue
            own=law[1]
        yield {'reference':reference(own),'document_type':kind,'heading':heading,'text':block}

def publication_evidence(candidate,documents,as_of):
    if not candidate.reference_number:return None
    for doc in documents:
        if not official_bo(doc['url']):continue
        for section in document_sections(doc):
            expected='LAW' if candidate.document_type=='DRAFT_LAW' else candidate.document_type
            if section['reference']!=reference(candidate.reference_number) or section['document_type']!=expected:continue
            status='PUBLISHED';effective=None
            clause=re.search(r'(?:La présente loi|Le présent décret|Le présent arrêté)\s+entre(?:ra)?\s+en vigueur\s+(?:à compter du|le)\s+([^\.\n]{5,60})',section['text'],re.I)
            if clause:
                effective=evidence_date(clause[1])
                if effective and effective<=as_of:status='IN_FORCE'
            return {'status':status,'effective_date':effective,'document_type':section['document_type'],
                'url':doc['url'],'date':doc.get('date'),'bo_number':doc.get('bo_number'),
                'excerpt':section.get('evidence_excerpt',section['heading'])[:1200]}
    return None

def apply_publication(candidate,proof,as_of):
    if not proof:
        return candidate.model_copy(update={'publication_check':'NOT_FOUND_IN_CHECKED_BULLETINS',
            'verification_date':as_of})
    summary=f"{proof['status']} — Bulletin Officiel {proof['bo_number'] or ''}, {proof['date'] or 'date non vérifiée'}. "
    if proof['status']=='PUBLISHED':summary+='Publication vérifiée ; entrée en vigueur actuelle non établie. '
    return candidate.model_copy(update={'legal_status':proof['status'],'reported_status':proof['status'],
        'document_type':proof['document_type'],'effective_date':proof['effective_date'],
        'publication_date':proof['date'],'official_document_url':proof['url'],
        'official_source':proof['url'],'status_source_url':proof['url'],'status_source_type':'BULLETIN_OFFICIEL',
        'status_confidence':.98,'publication_verified':True,'publication_check':'VERIFIED',
        'bo_number':proof['bo_number'],'verification_date':as_of,'reliable_status_evidence':True,
        'status_evidence':proof['excerpt'],'summary':(summary+proof['excerpt'])[:2000]})
