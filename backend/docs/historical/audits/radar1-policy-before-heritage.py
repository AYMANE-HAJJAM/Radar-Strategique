"""Deterministic procurement source and business boundaries (Radar 1 only)."""
import re
import unicodedata
from urllib.parse import urlsplit, parse_qs

from app.collectors.markets.pmmp import is_pmmp, is_direct_notice

DEFAULT_AGGREGATORS = ('cpmaroc.com', 'marchefacile.ma', 'borjmarchepublic.ma', 'marchesfaciles.ma')
DEFAULT_WHITELIST = ('marchespublics.gov.ma', *DEFAULT_AGGREGATORS, 'culture.gov.ma', 'alomrane.gov.ma')
KEYWORDS = {
    'HERITAGE_STRONG': ('patrimoine', 'patrimonial', 'patrimoniale', 'medina', 'monument', 'monuments',
        'historique', 'historiques', 'rempart', 'remparts', 'muraille', 'kasbah', 'heritage', 'historic buildings', 'traditional architecture', 'architecture traditionnelle'),
    'ARCHITECTURE': ('architecture', 'architectural', 'architecturaux', 'architecturale', 'architecturales',
        "maitrise d oeuvre", 'moe', 'reconversion', 'diagnostic batiment'),
    'TERRITORIAL': ('urbanisme', 'etude urbaine', 'etudes urbaines', 'urban planning', 'plan d amenagement', 'plans d amenagement',
        'charte architecturale', 'charte paysagere', 'planification urbaine', 'requalification urbaine',
        'developpement territorial', 'amenagement du territoire', 'territoriale', 'territorial',
        'territoriaux', 'territoriales', 'mobilite urbaine', 'tourisme culturel', 'foncier'),
    'REHABILITATION': ('rehabilitation', 'restauration', 'reamenagement', 'redeveloppement'),
    'TECHNICAL': ('etude technique', 'etudes techniques', 'suivi', 'controle', 'coordination',
        'assistance technique', 'assistance a maitrise d ouvrage', 'amo'),
    'PUBLIC_ENVIRONMENT': ('batiment', 'batiments', 'construction', 'travaux', 'equipement public',
        'equipements publics', 'equipements collectifs', 'equipement culturel', 'institut',
        'dar talib', 'dar taliba', 'espace public', 'espaces publics', 'jardin public', 'parc public',
        'corniche', 'paysager', 'paysagere', 'paysagers', 'complexe public', 'siege administratif',
        'unites prescolaires', 'voie d acces', 'amenagement urbain'),
    'NEGATIVE': ('gardiennage', 'nettoyage', 'restauration collective', 'denrees alimentaires',
        'fournitures de bureau', 'informatique', 'ordinateurs', 'vehicules', 'consommables',
        'materiel de laboratoire', 'equipements de laboratoire', 'securite privee',
        'repas', 'alimentation', 'mobilier de bureau', 'mobilier standard', 'fournitures medicales',
        'materiel medical', 'medico technique', 'medico hospitalier', 'medicaments', 'dispositifs medicaux', 'fauteuils roulants', 'unite medicale mobile', 'tables radiologiques', 'scanner tdm', 'endoscopie', 'fournitures', 'catering', 'securite', 'maintenance des logiciels', 'reactifs', 'maintenance informatique', 'maintenance des vehicules'),
}
WEIGHTS = {'HERITAGE_STRONG': 5, 'ARCHITECTURE': 4, 'TERRITORIAL': 4,
           'REHABILITATION': 3, 'TECHNICAL': 2, 'PUBLIC_ENVIRONMENT': 2, 'NEGATIVE': -5}



def folded(value):
    value = unicodedata.normalize('NFKD', value or '').casefold().replace('œ', 'oe')
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).split())


def contains(text, term):
    return f' {folded(term)} ' in f' {folded(text)} '


# Explicit architecture signals that can rescue a mixed topography tender.
ARCHITECTURE_RESCUE = (
    'architecture', 'architectural', 'architecturale', 'architecturales', 'architecturaux',
    'consultation architecturale', 'concours architectural', 'conception architecturale',
    'suivi architectural', 'maitrise d oeuvre architecturale', 'rehabilitation architecturale',
)
TOPOGRAPHY_ONLY = (
    'topographie', 'topographique', 'topographiques', 'topographic', 'topography',
    'leve topographique', 'leves topographiques', 'geometre', 'cartographie',
    'systeme d information geographique', 'sig', 'lidar', 'leve lidar', 'leves lidar',
)


def evaluate_relevance(title, groups=None, scope=None):
    """Architecture-only business boundary for Radar 1."""
    groups = {**KEYWORDS, **(groups or {})}
    source = ' '.join(part for part in (title, scope) if part)
    signals = {group: [term for term in terms if contains(source, term)]
               for group, terms in groups.items() if group in WEIGHTS}
    signals = {group: terms for group, terms in signals.items() if terms}
    text = folded(source)
    architecture = 'ARCHITECTURE' in signals or any(contains(text, term) for term in ARCHITECTURE_RESCUE)
    # "Ksar" is also common in place names (for example Ksar Sghir). It is a
    # heritage signal only when the mission explicitly intervenes on the ksar.
    ksar_heritage = contains(text, 'ksar') and any(contains(text, term) for term in (
        'restauration', 'rehabilitation', 'conservation', 'sauvegarde', 'valorisation'))
    heritage = 'HERITAGE_STRONG' in signals or ksar_heritage
    intervention = any(contains(text, term) for term in (
        'restauration', 'rehabilitation', 'renovation', 'reamenagement', 'reconversion',
        'conservation', 'sauvegarde', 'valorisation', 'conception', 'etude', 'etudes'))
    building = any(contains(text, term) for term in (
        'batiment', 'batiments', 'siege', 'ecole', 'internat', 'mosquee', 'mausolee',
        'equipement public', 'equipements publics', 'centre culturel', 'institut',
        'dar talib', 'dar taliba', 'unites prescolaires', 'architecture'))
    urban_design = any(contains(text, term) for term in (
        'etude urbaine', 'etudes urbaines', 'urban design', 'plan d amenagement',
        'plans d amenagement', 'charte architecturale', 'planification urbaine',
        'requalification urbaine', 'amenagement urbain')) or (
            contains(text, 'urbanisme') and any(contains(text, term) for term in (
                'etude', 'etudes', 'plan', 'schema', 'conception', 'amenagement', 'reamenagement')))
    rehabilitation = 'REHABILITATION' in signals and building
    heritage_architecture = heritage and intervention
    architectural_scope = architecture or rehabilitation or heritage_architecture or urban_design

    topography = any(contains(text, term) for term in TOPOGRAPHY_ONLY)
    technical = any(contains(text, term) for term in (
        'etude technique', 'etudes techniques', 'geotechnique', 'laboratoire', 'controle qualite',
        'genie civil', 'voirie', 'assainissement', 'reseau', 'reseaux', 'route', 'routes',
        'ouvrage d art', 'ouvrages d art', 'hydraulique', 'supervision'))
    landscaping = any(contains(text, term) for term in ('paysager', 'paysagere', 'paysagisme'))
    generic_territorial = any(contains(text, term) for term in (
        'developpement territorial', 'etude territoriale', 'etudes territoriales',
        'amenagement du territoire')) and not urban_design

    rejection_reason = None
    # Strong negative override: topography/LiDAR without an explicit architecture signal.
    if topography and not architecture:
        rejection_reason = 'topography_only'
    elif not architectural_scope:
        if technical:
            rejection_reason = 'technical_only'
        elif landscaping:
            rejection_reason = 'landscaping_only'
        elif generic_territorial:
            rejection_reason = 'territorial_without_architecture'
        else:
            rejection_reason = 'no_architectural_scope'
    if 'NEGATIVE' in signals and not architecture:
        rejection_reason = rejection_reason or 'non_architectural_purchase'

    priority = 1 if heritage_architecture else 2
    return dict(score=5 if priority == 1 and not rejection_reason else
                          4 if not rejection_reason else -5,
                priority=priority, signals=signals,
                decision='keep' if not rejection_reason else 'reject',
                rejection_reason=rejection_reason,
                architecture_scope=architectural_scope and not (topography and not architecture))


def relevant(title, groups=None, scope=None):
    return evaluate_relevance(title, groups, scope=scope)['decision'] != 'reject'


def normalize_domain(value):
    host = (urlsplit(value.strip() if '://' in value else 'https://' + value.strip()).hostname or '').lower().rstrip('.')
    return host.removeprefix('www.').encode('idna').decode('ascii')


def domain_match(url, domains):
    try:
        host = normalize_domain(url)
        normalized = [normalize_domain(d) for d in domains]
        return any(d and (host == d or host.endswith('.' + d)) for d in normalized)
    except ValueError:
        return False


def source_role(url, config):
    whitelist = config.get('RADAR1_SOURCE_WHITELIST', DEFAULT_WHITELIST)
    if not domain_match(url, whitelist):
        return None
    if is_pmmp(url):
        return 'OFFICIAL_PROCUREMENT'
    if domain_match(url, config.get('RADAR1_AGGREGATOR_DOMAINS', DEFAULT_AGGREGATORS)):
        return 'PROCUREMENT_AGGREGATOR'
    if domain_match(url, config.get('RADAR1_DISCOVERY_DOMAINS', ())):
        return 'DISCOVERY_ONLY'
    return 'OFFICIAL_INSTITUTIONAL'


def aggregate_title(title):
    text = folded(title)
    return bool(re.search(r'\b\d+ appels? d offres\b|\bappels d offres de services a\b|\bliste des appels\b|\bactualites\b', text))


def detail_url(url):
    if not url:
        return False
    if urlsplit(url).scheme not in {'http', 'https'}:
        return False
    if is_pmmp(url):
        return is_direct_notice(url)
    parts = urlsplit(url)
    path = parts.path.strip('/').lower()
    if not path or re.search(r'(^|/)(blog|news|actualites?|articles?|search|recherche|category|categorie|archives|presse)(/|$)', path):
        return False
    if any(k.lower() in {'s', 'search', 'q', 'query'} for k in parse_qs(parts.query)):
        return False
    return path.rsplit('/', 1)[-1] not in {'appels-offres', 'appels-d-offres', 'appels-doffres',
        'marches-publics', 'consultations', 'index.php', 'index.html', 'resultats', 'avis'}
