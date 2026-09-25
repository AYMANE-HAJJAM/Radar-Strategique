"""Small reviewed registry: URLs and role scopes, never stored officeholder names.

Each evidence URL is an ordinary cached source. Refresh/priority/enabled can be
overridden through the existing RADAR3_SOURCES configuration.
"""
from dataclasses import dataclass
import re
from app.integrations.http.html import Page
from app.modules.radar3_institutions.leadership import NAME, evidence_date
from app.modules.radar3_institutions.policy import folded, rejection_reason

def normalize_role(value):
    value=folded(value)
    for pattern,kind in (
        (r'direct(?:eur|rice) general', 'DIRECTOR_GENERAL'),
        (r'direct(?:eur|rice) technique','TECHNICAL_DIRECTOR'),
        (r'direct(?:eur|rice) de l urbanisme','URBANISM_DIRECTOR'),
        (r'direct(?:eur|rice) de programme','PROGRAM_DIRECTOR'),
        (r'(?:direct(?:eur|rice)|chef) de projet','PROJECT_DIRECTOR'),
        (r'responsable patrimoine','HERITAGE_MANAGER'),
        (r'responsable partenariats','PARTNERSHIP_MANAGER'),
        (r'responsable (?:marches|projets)','PROCUREMENT_PROJECT_MANAGER'),
        (r'secretaire general','SECRETARY_GENERAL'),
        (r'president','PRESIDENT'),(r'direct(?:eur|rice)','DIRECTOR')):
        if re.match(pattern+r'\b',value):return kind
    return None

@dataclass(frozen=True)
class InstitutionSource:
    key: str
    institution_name: str
    official_domain: str
    role_pattern: str
    normalized_role: str | None
    evidence_url: str
    governance_url: str | None = None
    organization_url: str | None = None
    leadership_url: str | None = None
    appointments_url: str | None = None
    news_url: str | None = None
    projects_url: str | None = None
    refresh_interval: int = 7
    priority: int = 2
    enabled: bool = True
    source_type: str = 'OFFICIAL_RELEASE'

REGISTRY = (
    InstitutionSource('fnm','Fondation Nationale des Musées','fnm.ma',
        r'Président de la Fondation Nationale des Musées','PRESIDENT',
        'https://fnm.ma/actualites/35',
        governance_url='https://www.fnm.ma/about/president-message',
        leadership_url='https://www.fnm.ma/about/president-message', news_url='https://fnm.ma/actualites/'),
    InstitutionSource('essaouira','Conseil Communal d’Essaouira','maroc.ma',
        r'Président du Conseil Communal d[’\x27]Essaouira','PRESIDENT',
        'https://www.maroc.ma/fr/actualites/un-partenariat-strategique-pour-la-valorisation-du-musee-sidi-mohammed-ben-abdellah-dessaouira'),
    InstitutionSource('culture','Ministère de la Jeunesse, de la Culture et de la Communication','maroc.ma',
        r'ministre de la Jeunesse, de la Culture et de la Communication',None,
        'https://www.maroc.ma/fr/actualites/renforcement-des-relations-bilaterales-entre-le-maroc-et-la-france-dans-le-domaine-de-la-culture',
        governance_url='https://www.maroc.ma/fr/le-maroc/gouvernement',news_url='https://mjcc.gov.ma/fr/actualites/'),
    InstitutionSource('eljadida','Agence Urbaine d’El Jadida-Sidi Bennour','auejsb.ma',
        r'[Dd]irect(?:eur|rice)', 'DIRECTOR',
        'https://www.auejsb.ma/index.php/fr/Gouvernance/dirigeants',
        governance_url='https://www.auejsb.ma/index.php/fr/Gouvernance/dirigeants',source_type='GOVERNANCE',priority=6),
    InstitutionSource('apdn','Agence pour la Promotion et le Développement du Nord','apdn.ma',
        r'[Dd]irecteur [Gg]énéral','DIRECTOR_GENERAL','https://www.apdn.ma/',
        news_url='https://www.apdn.ma/',enabled=False),
)

def source_records():
    return tuple({'name':s.institution_name+' — preuve officielle','index_url':s.evidence_url,
        'parser_type':'CURATED_ROLE:'+s.key,'refresh_days':s.refresh_interval,
        'priority':s.priority,'enabled':s.enabled} for s in REGISTRY)

def scoped_page(html):
    # Never use navigation dates, related news, authors or a site's current clock.
    after=re.split(r'</h1\s*>',html,maxsplit=1,flags=re.I)
    if len(after)!=2:return '',None
    body=re.split(r'<(?:footer|aside)\b|<h[234]\b',after[1],maxsplit=1,flags=re.I)[0]
    text=Page(body).text
    text=re.split(r'Dernières actualités|Continuez votre visite|Retour aux actualités',text,maxsplit=1,flags=re.I)[0]
    return text,evidence_date(text[:400])

def role_items(key,raw,charset='utf-8'):
    source=next(s for s in REGISTRY if s.key==key)
    html=raw.decode(charset,errors='replace');text,dated=scoped_page(html)
    title=' '.join(Page(html).h1)
    if not text or rejection_reason(title):return []
    records=[]
    # Explicit person/role adjacency, scoped to the institution's exact role.
    for pattern in (rf'(?P<name>{NAME})\s*,\s*(?P<role>{source.role_pattern})',
                    rf'(?P<role>{source.role_pattern})\s*,\s*(?P<name>{NAME})'):
        for match in re.finditer(pattern,text):
            prefix=folded(text[max(0,match.start()-45):match.start()])
            if any(x in prefix for x in ('auteur','recrutement','ancien','journaliste')):continue
            name=re.sub(r'^(?:Messieurs|Monsieur|Madame|Mme|M)\s+','',match['name'])
            records.append({'person_name':name,'role_title':match['role'],
                'institution':source.institution_name,'source_url':source.evidence_url,
                'source_type':source.source_type,'evidence_date':dated.isoformat() if dated else None,
                'evidence_excerpt':text[max(0,match.start()-30):match.end()+80]})
    return [{'title':source.institution_name,'institution':source.institution_name,'url':source.evidence_url,
        'evidence':text[:1800], 'date':dated.isoformat() if dated else None,'profile_evidence':True,
        'role_records':records,'normalized_role':normalize_role(records[0]['role_title']) if records else None,
        'reference':__import__('hashlib').sha256(text.encode()).hexdigest()}]
