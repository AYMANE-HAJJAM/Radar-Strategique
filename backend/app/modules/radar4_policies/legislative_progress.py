"""Extract explicit parliamentary stages; a chamber vote is not effectiveness."""
import re
from app.integrations.http.html import Page
from app.modules.radar4_policies.policy import folded
from app.modules.radar4_policies.status_verification import REF, reference

def parliament_items(raw,url,charset='utf-8'):
    from app.modules.radar3_institutions.curated_sources import scoped_page
    html=raw.decode(charset,errors='replace');page=Page(html)
    text,dated=scoped_page(html)
    title=' '.join(page.h1)
    match=re.search(r'(?:projet de )?loi\s+n[°ºo]?\s*('+REF+r')',title,re.I)
    if not match or not text:return []
    value=folded(text)
    if any(x in value for x in ('non adopte','pas adopte','pas encore adopte')):stage='PRESENTED'
    elif 'adopte definitivement' in value or 'adopte par les deux chambres' in value:stage='PARLIAMENT_ADOPTED'
    elif 'adopte' in value and 'chambre' in value:stage='CHAMBER_ADOPTED'
    elif 'commission' in value:stage='COMMITTEE'
    else:stage='PRESENTED'
    return [{'title':title,'url':url,'evidence':text[:1800], 'date':dated.isoformat() if dated else None,
        'reference':reference(match[1]),'parliamentary_stage':stage}]
