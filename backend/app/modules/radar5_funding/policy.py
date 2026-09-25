import re
from datetime import datetime
from app.core.normalization import fold_text
from app.core.dates import parse_fr_date
SCOPE=('architecture','patrimoine','heritage','rehabilitation','medina','culturel','culturelle','cultural infrastructure','developpement urbain','urban development','urban',
       'developpement territorial','territorial development','territorial','espace public','resilience urbaine','planification','regeneration','equipement public','infrastructure culturelle')
def folded(v):
    return fold_text(v)
def has(t,terms):return any(f' {folded(x)} ' in f' {t} ' for x in terms)
def classify(text):
    t=folded(text)
    if not has(t,('maroc','morocco','marocaine','marocain')) or not has(t,SCOPE):return None
    denies_open=any(x in t for x in ('not a specific grant tender or open call','not an open call','no open call','does not announce a direct'))
    denies_consultant=any(x in t for x in ('does not establish a new financing call consultant opportunity','no consultant opportunity'))
    if has(t,('cloture','closed','acheve','completed')): status='closed';letter='E'
    elif 'strategic pipeline framework' in t:status='pipeline';letter='D'
    elif not denies_open and has(t,('appel ouvert','candidatures ouvertes','open call','date limite')):status='open';letter='A'
    elif has(t,('approuve','approved','signe','signed','en cours','active','accord de financement','financing agreement')):status='active';letter='B'
    elif has(t,('en preparation','concept note','preparation')):status='preparation';letter='C'
    else:status='pipeline';letter='D'
    if not denies_open and has(t,('eligibles','peut candidater','apply','appel a projets','subvention')):mode='DIRECT_ACCESS'
    elif not denies_consultant and has(t,('consultant','services de conseil','consulting services')):mode='CONSULTANT_OPPORTUNITY'
    elif has(t,('plan de passation','procurement plan','marches du beneficiaire')):mode='BENEFICIARY_PROCUREMENT'
    elif has(t,('assistance technique','technical assistance')):mode='TECHNICAL_ASSISTANCE'
    elif not denies_open and has(t,('grant','subvention')):mode='GRANT'
    elif status in {'preparation','pipeline'}:mode='PROJECT_PIPELINE'
    else:mode='MONITORING_ONLY'
    return status,letter,mode
def parse_date(v):
    if v is None: return None
    if not isinstance(v, str): return v
    return parse_fr_date(v)
