import re
from datetime import datetime

from app.core.validation import today_in_morocco
from app.core.normalization import fold_text
from app.core.dates import parse_fr_date


SIGNALS = (
    ('FINANCING_APPROVED', ('financement approuve', 'financement accorde', 'finance par', 'pret approuve')),
    ('CONVENTION_SIGNED', ('convention signee', 'signature d une convention', 'accord signe')),
    ('BUDGET_ALLOCATED', ('budget alloue', 'budget consacre', 'enveloppe budgetaire')),
    ('PROGRAM_APPROVED', ('programme approuve', 'programme adopte', 'programme lance', 'lancement du programme')),
    ('STUDY_LAUNCHED', ('lancement des etudes', 'lancement d etudes', 'etudes lancees', 'etude lancee')),
    ('FEASIBILITY_PREPARATION', ('etude de faisabilite', 'etudes prealables', 'etude prealable')),
    ('DESIGN_PREPARATION', ('conception architecturale', 'phase de conception', 'concours architectural')),
    ('LAND_OR_SITE_PREPARATION', ('site selectionne', 'terrain mobilise', 'foncier mobilise')),
    ('PARTNER_SELECTED', ('partenaire selectionne', 'partenariat conclu')),
    ('IMPLEMENTATION_PREPARATION', ('mise en oeuvre prochaine', 'preparation de la mise en oeuvre', 'lancement prochain')),
    ('PROJECT_ANNOUNCED', ('projet annonce', 'a annonce le projet', 'lancement du projet',
                           'lancement officiel du projet', 'projet de rehabilitation',
                           'projet d amenagement', 'projet de restauration')),
)
SCOPE = ('architecture', 'architectural', 'rehabilitation', 'restauration', 'conservation',
    'medina', 'monument', 'patrimoine', 'batiment historique', 'equipement culturel',
    'espace public', 'amenagement urbain', 'urbanisme', 'planification urbaine',
    'developpement territorial', 'regeneration', 'transformation urbaine',
    'programme de developpement', 'investissement public', 'valorisation du site',
    'developpement regional', 'strategie territoriale', 'gouvernance territoriale',
    'innovation territoriale', 'developpement local', 'centre historique',
    'site archeologique', 'ingenierie territoriale')
IRRELEVANT = ('autoroute', 'reseau d assainissement', 'adduction d eau', 'centrale electrique',
    'materiel medical', 'agriculture', 'industrie automobile')
VAGUE = ('a souligne l importance', 'a appele a', 'vision ambitieuse', 'discours', 'ceremonie')
COMPLETED = ('projet acheve', 'travaux acheves', 'inaugure', 'mise en service')
TENDER = ('appel d offres', 'marche public', 'soumission', 'date limite de remise')


def folded(value):
    return fold_text(value, oe_ligature=True)


def has(text, terms):
    return any(term in text for term in terms)


def classify_signal(title, evidence, publication_date=None):
    text = folded((title or '') + ' ' + (evidence or ''))
    signal = next((name for name, terms in SIGNALS if has(text, terms)), None)
    scope = [term for term in SCOPE if term in text]
    recent_update = has(text, ('nouvelle phase', 'financement approuve', 'convention signee',
                               'lancement des etudes', 'lancement prochain'))
    old = bool(publication_date and (today_in_morocco() - publication_date).days > 90 and not recent_update)
    completed = has(text, COMPLETED) and not recent_update
    vague = has(text, VAGUE) and signal is None
    tender = has(text, TENDER)
    irrelevant = not scope or (has(text, IRRELEVANT) and not has(text, ('architecture', 'rehabilitation', 'urbanisme')))
    rejection = ('published_tender' if tender else 'completed' if completed else 'old' if old else
                 'vague' if vague or signal is None else 'irrelevant' if irrelevant else None)
    maturity = ('A' if signal in {'FINANCING_APPROVED', 'PROGRAM_APPROVED', 'BUDGET_ALLOCATED'} else
                'B' if signal in {'CONVENTION_SIGNED', 'PROJECT_ANNOUNCED', 'PARTNER_SELECTED'} else
                'C' if signal else 'D')
    priority = 1 if has(text, ('patrimoine', 'medina', 'monument', 'historique', 'restauration')) else 2
    budget = re.search(r'\b(?:[\d.,]+)\s*(?:milliards?|millions?|mmdh|mdh|dh)\b', text)
    return dict(signal_type=signal, maturity=maturity, scope=scope, rejection=rejection,
                completed=completed, recent_update=recent_update, vague=vague, tender=tender,
                priority=priority, budget=budget.group() if budget else None)


def parse_date(value):
    return parse_fr_date(value)
