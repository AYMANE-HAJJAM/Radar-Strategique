"""Shared ARCHERITAGE/Innova business boundary for intelligence Radars 2-5."""
import re
import unicodedata


ARCHERITAGE = (
    'patrimoine', 'heritage', 'restauration', 'conservation', 'rehabilitation patrimoniale',
    'architecture patrimoniale', 'bati ancien', 'tissu ancien', 'medina', 'monument',
    'site historique', 'centre historique', 'ancienne ville', 'valorisation patrimoniale',
    'reconversion', 'regeneration historique', 'site archeologique', 'circuit patrimonial',
    'tourisme culturel', 'historic site', 'cultural heritage', 'adaptive reuse',
    'تراث', 'ترميم', 'تأهيل', 'مدينة عتيقة',
)
INNOVA = (
    'ingenierie territoriale', 'developpement territorial', 'developpement regional',
    'strategie territoriale', 'urbanisme', 'amenagement du territoire', 'amenagement urbain',
    'gouvernance territoriale', 'valorisation territoriale', 'projet structurant',
    'innovation territoriale', 'regeneration urbaine', 'developpement local',
    'politique publique', 'planification territoriale', 'investissement territorial',
    'regional development', 'territorial development', 'territorial strategy',
    'urban planning', 'urban regeneration', 'urban development', 'local development', 'public policy',
    'programme regional de developpement', 'developpement de la region',
    'territorial governance', 'تنمية ترابية', 'حكامة ترابية', 'تخطيط حضري',
)
NEGATIVE = (
    'football', 'match de football', 'celebrite', 'people', 'fait divers',
    'produit bancaire', 'credit a la consommation', 'consumer banking',
    'logiciel de gestion', 'erp', 'cybersecurite', 'materiel informatique',
    'application mobile', 'recrutement', 'offre d emploi', 'resultats sportifs',
    'revêtement de la route', 'revetement de la route', 'entretien routier',
    'education prescolaire', 'programme scolaire',
)
STRATEGIC_EVIDENCE = (
    'programme', 'projet', 'strategie', 'reforme', 'convention', 'partenariat',
    'financement', 'investissement', 'etude', 'initiative', 'plan', 'schema',
    'lancement', 'mise en oeuvre', 'appel a projets', 'assistance technique',
    'loi', 'decret', 'reglement', 'directive', 'circulaire', 'consultation publique',
    'program', 'project', 'strategy', 'reform', 'agreement', 'financing', 'study',
)


def fold(value):
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.sub(r'[^\w]+', ' ', ''.join(
        character for character in value if not unicodedata.combining(character))).split())


def _hits(text, terms):
    padded = f' {text} '
    return [term for term in terms if f' {fold(term)} ' in padded]


def evaluate_business_relevance(*parts, uncertain_review=True):
    """Return a deterministic shared scope decision without replacing radar-specific rules."""
    text = fold(' '.join(str(part) for part in parts if part))
    archeritage, innova = _hits(text, ARCHERITAGE), _hits(text, INNOVA)
    negative = _hits(text, NEGATIVE)
    positive = archeritage + innova
    if negative and not positive:
        return {'decision': 'reject', 'domains': [], 'signals': negative,
                'reason': 'unrelated_generic_content'}
    if not positive:
        return {'decision': 'reject', 'domains': [], 'signals': [],
                'reason': 'outside_archeritage_innova_scope'}
    domains = (['ARCHERITAGE'] if archeritage else []) + (['INNOVA'] if innova else [])
    credible = bool(_hits(text, STRATEGIC_EVIDENCE))
    return {'decision': 'keep' if credible or not uncertain_review else 'review',
            'domains': domains, 'signals': positive, 'reason': None}
