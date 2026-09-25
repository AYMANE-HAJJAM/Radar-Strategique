import re
from datetime import datetime

from app.core.validation import today_in_morocco
from app.core.normalization import fold_text
from app.core.dates import parse_fr_date

RELEVANCE = ('architecture', 'architectural', 'patrimoine', 'culture', 'medina', 'restauration',
    'rehabilitation', 'urbanisme', 'amenagement urbain', 'espace public', 'developpement territorial',
    'planification', 'regeneration', 'equipement culturel', 'investissement public', 'cadre bati',
    'developpement regional', 'strategie territoriale', 'gouvernance territoriale',
    'innovation territoriale', 'developpement local', 'politique publique')
ACTIVITIES = (
    ('NEW_APPOINTMENT', ('nomme', 'nomination', 'nouveau directeur', 'nouvelle directrice')),
    ('LEADERSHIP_CHANGE', ('changement de direction', 'nouveau president', 'nouvelle presidente')),
    ('NEW_RESPONSIBILITY', ('charge de', 'responsable de', 'pilotage du projet')),
    ('PROGRAM_LAUNCH', ('lance un programme', 'lancement du programme', 'nouveau programme')),
    ('RESTRUCTURING', ('restructuration', 'reorganisation')),
    ('PARTNERSHIP', ('convention signee', 'partenariat', 'accord de cooperation')),
    ('INVESTMENT_FOCUS', ('programme d investissement', 'investissement dans')),
)
ROLE_TYPES = (
    ('STRATEGIC_DECISION_MAKER', ('ministre', 'wali', 'gouverneur', 'president', 'presidente',
                                  'directeur general', 'directrice generale', 'secretaire general')),
    ('HERITAGE_MANAGER', ('patrimoine', 'conservation', 'medina')),
    ('URBANISM_MANAGER', ('urbanisme', 'amenagement', 'planification urbaine')),
    ('PROJECT_DIRECTOR', ('directeur de projet', 'directrice de projet', 'chef de projet')),
    ('PROCUREMENT_MANAGER', ('marches', 'commande publique', 'achats')),
    ('PARTNERSHIP_MANAGER', ('partenariat', 'cooperation')),
    ('PROGRAM_MANAGER', ('programme', 'programmes')),
    ('TECHNICAL_MANAGER', ('directeur technique', 'directrice technique', 'responsable technique')),
    ('OPERATIONAL_MANAGER', ('directeur operationnel', 'directrice operationnelle')),
)
OBSOLETE = ('ancien directeur', 'ancienne directrice', 'ex directeur', 'a quitte ses fonctions',
            'remplace par', 'mandat termine', 'jusqu en 2023', 'jusqu en 2024', 'jusqu en 2025')


def folded(value):
    return fold_text(value)


def contains(text, term):
    return f' {folded(term)} ' in f' {folded(text)} '


def classify(text, published=None):
    value = folded(text)
    relevant = any(contains(value, term) for term in RELEVANCE)
    activity = next((name for name, terms in ACTIVITIES if any(contains(value, t) for t in terms)), 'CURRENT_PROFILE')
    role = next((name for name, terms in ROLE_TYPES if any(contains(value, t) for t in terms)), None)
    obsolete = any(contains(value, term) for term in OBSOLETE)
    current = bool(published and 0 <= (today_in_morocco() - published).days <= 180)
    return {'relevant': relevant, 'activity_type': activity, 'role_type': role,
            'obsolete': obsolete, 'current': current}


def rejection_reason(title, evidence=''):
    headline = folded(title)
    if any(contains(headline, t) for t in ('recrutement', 'offre d emploi', 'offres d emploi',
            'appel a candidature', 'appel a candidatures', 'job', 'vacancy')):
        return 'recruitment_notice'
    if any(contains(headline, t) for t in ('ancien directeur', 'ancienne directrice', 'ancien president', 'ex directeur')):
        return 'obsolete_role'
    if any(contains(headline, t) for t in ('conference', 'colloque')):
        return 'generic_article'
    return None


def parse_date(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    return parse_fr_date(value)


def public_excerpt(value):
    # Store institutional facts; remove contact coordinates if a source excerpt contains them.
    value = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', '[contact omitted]', value or '')
    value = re.sub(r'(?<!\d)(?:\+?212[ .-]?|0)[5-7](?:[ .-]?\d{2}){4}(?!\d)', '[contact omitted]', value)
    return ' '.join(value.split())[:2000]
