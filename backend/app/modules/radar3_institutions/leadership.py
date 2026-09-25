"""Institution-scoped, dated role evidence. Never infer names from topic words."""
import re
from dataclasses import dataclass
from datetime import date
from app.modules.radar3_institutions.policy import folded

SOURCE_RANK={'GOVERNANCE':0,'ORGANIGRAM':1,'APPOINTMENT':2,'OFFICIAL_RELEASE':3,'OFFICIAL_PROGRAM':4,'PROFESSIONAL':5}
MONTHS={'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12}

def evidence_date(text):
    value=folded(text)
    match=re.search(r'\b(\d{1,2}) ('+'|'.join(MONTHS)+r') (\d{4})\b',value)
    try:
        if match:return date(int(match[3]),MONTHS[match[2]],int(match[1]))
        match=re.search(r'\b(20\d{2})-(\d{2})-(\d{2})\b',text)
        return date(*map(int,match.groups())) if match else None
    except ValueError:return None

@dataclass(frozen=True)
class RoleEvidence:
    person_name:str
    role_title:str
    institution:str
    source_url:str
    source_type:str
    evidence_date:date|None
    evidence_excerpt:str
    departed:bool=False
    interim:bool=False

def role_valid(role):
    value=folded(role)
    return bool(re.search(r'\b(directeur|directrice|president|presidente|secretaire general|secretaire generale|responsable patrimoine|responsable partenariats|responsable marches|chef de projet|ministre)\b',value)) and not any(
        t in value for t in ('journaliste','auteur','recrutement','ancien','ancienne','ex directeur')) and (
            'communication' not in value or value.startswith('ministre '))

def resolve(evidence, as_of):
    """Resolve one institution/role slot; recency outranks static official pages."""
    valid=[e for e in evidence if role_valid(e.role_title) and e.source_type in SOURCE_RANK
           and (e.evidence_date is None or e.evidence_date<=as_of)]
    official=[e for e in valid if e.source_type!='PROFESSIONAL']
    pool=official or valid
    if not pool:return None,'UNVERIFIED'
    pool.sort(key=lambda e:(e.evidence_date or date.min,-SOURCE_RANK[e.source_type]),reverse=True)
    best=pool[0]
    if best.departed or (best.evidence_date and (as_of-best.evidence_date).days>180):return best,'OBSOLETE'
    same=[e for e in pool if e.evidence_date==best.evidence_date and SOURCE_RANK[e.source_type]==SOURCE_RANK[best.source_type]]
    if len({folded(e.person_name) for e in same})>1:return None,'UNVERIFIED'
    if best.source_type=='PROFESSIONAL' or best.evidence_date is None:return best,'PROBABLY_CURRENT'
    return best,'VERIFIED_CURRENT'

NAME=r"[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'-]+(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÿ'-]+){1,5}"
ROLE=r"(?:[Mm]inistre(?:\s+[^,.]{3,120})?|[Dd]irect(?:eur|rice)(?:\s+général(?:e)?)?|[Pp]résident(?:e)?(?:\s+du\s+directoire)?|[Ss]ecrétaire\s+général(?:e)?|[Cc]hef\s+de\s+projet|[Rr]esponsable\s+(?:patrimoine|partenariats|marchés))"

def extract(text,institution,url,source_type,dated=None):
    text=' '.join(text.split()); dated=dated or evidence_date(text[:800])
    records=[]
    pattern=rf'(?P<name>{NAME})\s*(?:,|a été nommé(?:e)?|est nommé(?:e)?|est)\s*(?P<role>{ROLE}(?:\s+(?:technique|de programme|de projet|de l[’\x27]urbanisme|par intérim))?)'
    for m in re.finditer(pattern,text):
        name=re.sub(r'^(?:Monsieur|Madame|Mme|M)\s+','',m['name'])
        context=text[max(0,m.start()-90):m.end()+160]
        if any(t in folded(context[:90]) for t in ('auteur','journaliste','contact presse','recrutement')):continue
        departure=any(t in folded(context) for t in ('a quitte ses fonctions','fin de mandat','ancien directeur','ancienne directrice'))
        records.append(RoleEvidence(name,m['role'],institution,url,source_type,dated,context[:600],departure,'interim' in folded(context)))
    return records
