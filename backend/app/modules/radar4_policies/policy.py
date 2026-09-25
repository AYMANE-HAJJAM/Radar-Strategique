import re
from datetime import datetime

from app.core.normalization import fold_text
from app.core.dates import parse_fr_date

RELEVANCE = ('architecture','architectural','patrimoine','conservation','urbanisme','amenagement du territoire',
    'amenagement urbain','foncier','rehabilitation','medina','culturel','regeneration','espace public',
    'planification','developpement territorial','developpement regional','strategie territoriale',
    'gouvernance territoriale','decentralisation','innovation territoriale','tourisme culturel',
    'site historique','politique publique')
PROCUREMENT = ('appel d offres','marche public','remise des plis','adjudicataire')
TYPES = (('DRAFT_LAW',('projet de loi','avant projet de loi')),('LAW',('loi n','loi-cadre','loi ')),
    ('DECREE',('decret','décret')),('ORDER',('arrete','arrêté')),('CIRCULAR',('circulaire',)),
    ('PUBLIC_CONSULTATION',('consultation publique',)),('STRATEGY',('strategie','stratégie')),
    ('PROGRAM',('programme public','programme national')),('REGULATORY_REFORM',('reforme reglementaire','réforme réglementaire')),
    ('POLICY_STUDY',('etude de politique','étude stratégique')),('PUBLIC_STUDY',('etude territoriale','étude urbaine')),
    ('OFFICIAL_GUIDELINE',('directive','guide officiel','norme')))

def folded(value):
    return fold_text(value)

def contains(text, term): return f' {folded(term)} ' in f' {folded(text)} '

def classify(text, evidence=''):
    value=folded(text + ' ' + evidence)
    # The named instrument owns its type; a decree may cite its enabling law.
    title=folded(text)
    primary=re.match(r'^(?:projet de |avant projet de )?(decret|arrete|circulaire)\b', title)
    dtype=({'decret':'DECREE','arrete':'ORDER','circulaire':'CIRCULAR'}[primary.group(1)] if primary else
        next((name for name,terms in TYPES if any(contains(title,t) for t in terms)),None))
    if not dtype:
        dtype=next((name for name,terms in TYPES if any(contains(value,t) for t in terms)),None)
    if not dtype: return None
    if any(contains(value,t) for t in ('rehabilitation fonctionnelle', 'reeducation', 'functional rehabilitation')): return None
    if any(contains(value,t) for t in PROCUREMENT) and dtype not in {'PUBLIC_CONSULTATION'}: return None
    if not any(contains(value,t) for t in RELEVANCE): return None
    # Effectiveness of an enabling/cited law is not effectiveness of this instrument.
    status_value=re.split(r'\b(?:en application de|pour l application de|pris pour application de|conformement a|en vertu de)\b',value,maxsplit=1)[0]
    if dtype=='DRAFT_LAW': status='PUBLIC_CONSULTATION' if (contains(value,'consultation publique') or contains(value,'commentaires publics') or contains(value,'commentaires du public')) else 'DRAFT'
    elif any(contains(title,t) for t in ('projet de decret','projet d arrete')): status='UNDER_PREPARATION'
    elif dtype=='PUBLIC_CONSULTATION': status='PUBLIC_CONSULTATION'
    elif any(contains(status_value,t) for t in ('non adopte', 'pas adopte', 'pas encore adopte', 'pas en vigueur', 'non entre en vigueur', 'entrera en vigueur')): status='POLICY_SIGNAL'
    elif any(contains(status_value,t) for t in ('entre en vigueur','en vigueur')): status='IN_FORCE'
    elif any(contains(status_value,t) for t in ('adopte','adoptee','adoption definitive','promulgue')): status='ADOPTED'
    elif any(contains(value,t) for t in ('mise en oeuvre','application du programme')): status='IMPLEMENTATION'
    elif any(contains(value,t) for t in ('en preparation','elaboration en cours','projet de decret','projet d arrete')): status='UNDER_PREPARATION'
    else: status='POLICY_SIGNAL'
    if dtype in {'STRATEGY','PROGRAM','PUBLIC_STUDY','POLICY_STUDY'}:
        if status=='IN_FORCE':status='POLICY_SIGNAL'
        if status=='POLICY_SIGNAL' and any(contains(value,t) for t in ('annonce','annoncee','lancement')):status='ANNOUNCED'
    return dtype,status

def parse_date(value):
    if value is None: return None
    if not isinstance(value, str): return value
    return parse_fr_date(value)
