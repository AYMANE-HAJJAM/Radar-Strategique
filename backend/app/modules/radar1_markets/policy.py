"""Deterministic procurement source and business boundaries (Radar 1 only)."""
import re
from urllib.parse import urlsplit, parse_qs

from app.integrations.pmmp.client import is_pmmp, is_direct_notice
from app.core.normalization import fold_text

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
    return fold_text(value, oe_ligature=True)


def contains(text, term):
    """Substring match on folded tokens; `text` may already be folded (fold is idempotent)."""
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


# Fixed signals cannot be weakened by configurable architecture keywords.
HERITAGE_ASSETS = ('patrimoine', 'patrimonial', 'patrimoniale', 'patrimoniaux', 'patrimoniales',
    'historique', 'historiques', 'monument', 'monuments', 'rempart', 'remparts',
    'muraille', 'murailles', 'fortification', 'fortifications', 'bastion', 'bastions',
    'kasbah', 'kasbahs', 'ksar', 'ksour', 'enceinte', 'enceintes', 'heritage', 'historic')
BUILT_HERITAGE_ASSETS = ('patrimoine bati', 'patrimoine historique bati', 'bati patrimonial',
    'batiment historique', 'batiments historiques', 'monument', 'monuments', 'rempart',
    'remparts', 'muraille', 'murailles', 'fortification', 'fortifications', 'bastion',
    'bastions', 'kasbah', 'kasbahs', 'ksar', 'ksour', 'enceinte', 'enceintes',
    'porte historique', 'portes historiques', 'fondouk', 'fondouks', 'riad historique',
    'riads historiques', 'site archeologique', 'sites archeologiques', 'vestige archeologique',
    'facade historique', 'facades historiques', 'edifice ancien', 'edifices anciens',
    'batiment ancien', 'batiments anciens', 'structure ancienne', 'structures anciennes',
    'structure historique', 'structures historiques', 'architecture traditionnelle',
    'element architectural traditionnel', 'elements architecturaux traditionnels',
    'traditional architecture', 'historic building', 'historic buildings')
OLD_FABRIC = ('medina', 'medinas', 'bati ancien', 'batis anciens', 'tissu ancien',
    'tissus anciens', 'tissu urbain historique', 'tissus urbains historiques',
    'centre historique', 'centres historiques', 'quartier historique', 'quartiers historiques',
    'ancienne ville', 'anciennes villes', 'ville ancienne', 'villes anciennes',
    'vieille ville', 'vieilles villes', 'old urban fabric', 'historic urban fabric',
    'historic center', 'historic centre', 'old city')
HERITAGE_WORK = ('restauration', 'restaurations', 'rehabilitation', 'conservation',
    'sauvegarde', 'valorisation', 'mise en valeur', 'reconversion', 'consolidation',
    'traitement', 'revitalisation', 'requalification', 'regeneration', 'mise a niveau',
    'restoration', 'rehabilitation', 'conservation', 'safeguarding', 'adaptive reuse')
BUILT_WORK = HERITAGE_WORK + ('etude', 'etudes', 'diagnostic', 'diagnostics',
    'intervention', 'interventions', 'amenagement', 'reamenagement', 'travaux',
    'architecture', 'architectural', 'architecturale', 'architecturales', 'architecturaux',
    'suivi', 'maitrise d oeuvre', 'plan', 'programme')
GENERIC_WORK = ('construction', 'construction neuve', 'ecole', 'ecoles', 'lycee',
    'prescolaire', 'prescolaires', 'gendarmerie', 'caserne', 'cimetiere', 'cimetieres',
    'centre de sante', 'sport', 'sportif', 'sportifs', 'route', 'routes', 'voirie',
    'assainissement', 'eclairage', 'lotissement', 'logements', 'marche', 'souk')
BROAD_HERITAGE_CONTEXT = ('patrimoine culturel', 'patrimoine historique',
    'heritage culturel', 'heritage historique', 'cultural heritage', 'historical heritage',
    'etude patrimoniale', 'etudes patrimoniales', 'strategie de valorisation patrimoniale',
    'circuit patrimonial', 'circuits patrimoniaux', 'site patrimonial', 'sites patrimoniaux',
    'circuit historique', 'circuits historiques', 'route culturelle', 'routes culturelles',
    'site historique', 'sites historiques', 'paysage culturel', 'paysages culturels',
    'valorisation du patrimoine',
    'valorisation patrimoniale', 'diagnostic patrimonial', 'documentation du patrimoine',
    'interpretation du patrimoine', 'gestion du patrimoine culturel',
    'plan de conservation', 'plan de sauvegarde', 'schema directeur patrimonial',
    'masterplan patrimonial', 'tourisme patrimonial', 'tourisme culturel',
    'developpement du patrimoine culturel', 'developpement patrimonial',
    'territorial heritage valorisation', 'heritage development', 'heritage strategy',
    'heritage interpretation', 'heritage management', 'cultural route')
BROAD_HERITAGE_WORK = ('valorisation', 'mise en valeur', 'etude', 'etudes', 'strategie',
    'inventaire', 'diagnostic', 'circuit', 'circuits', 'site', 'sites', 'developpement',
    'development', 'documentation', 'interpretation', 'gestion', 'management', 'tourisme',
    'route', 'routes', 'plan', 'schema directeur', 'masterplan', 'amenagement',
    'requalification', 'revitalisation', 'regeneration')
ASSET_MANAGEMENT_CONTEXT = ('patrimoine automobile', 'parc automobile', 'patrimoine informatique',
    'patrimoine actif', 'actifs patrimoniaux',
    'erp', 'logiciel', 'application informatique', 'systeme d information',
    'patrimoine foncier', 'patrimoine immobilier', 'gestion fonciere', 'gestion immobiliere',
    'inventaire physique', 'inventaire des biens', 'inventaire de parc', 'biens mobiliers')
NATURAL_ONLY_CONTEXT = ('patrimoine naturel', 'patrimoine vegetal', 'patrimoine forestier',
    'natural heritage', 'vegetal', 'forestier')

ARCHITECTURAL_COMPETITION = ('concours architectural', 'concours d architecture',
    'concours de conception architecturale', 'concours pour la conception architecturale',
    'concours de conception', 'consultation architecturale', 'consultations architecturales',
    'architectural competition', 'architectural consultation')
ARCHITECTURAL_SCOPE = ('architecture', 'architectural', 'architecturale', 'architecturales',
    'conception', 'design', 'conception architecturale', 'etude architecturale', 'etudes architecturales',
    'maitrise d oeuvre', 'mission d architecte', 'mission de conception',
    'suivi architectural', 'design architectural', 'programmation architecturale',
    'services d architecture', 'service d architecture', 'architecture paysagere',
    'diagnostic architectural', 'consultation architecturale',
    'maitrise d oeuvre architecturale')
# Explicit architectural ROLE wording — proves profession, not project fit by itself.
ARCHITECTURAL_ROLE_SIGNALS = (
    'etude architecturale', 'etudes architecturales', 'conception architecturale',
    'consultation architecturale', 'mission d architecte',
    'services d architecture', 'service d architecture', 'architecture paysagere',
    'architecture agencement et decoration', 'architecture, agencement et decoration',
    'maitrise d oeuvre architecturale', 'suivi architectural',
    'programmation architecturale', 'diagnostic architectural',
    'architectural services', 'architectural service',
    'rehabilitation architecturale',
)
# Back-compat alias used by collector deferral / tests.
STRONG_ARCHITECTURAL_SCOPE = ARCHITECTURAL_ROLE_SIGNALS
PROFESSIONAL_SERVICES = ARCHITECTURAL_COMPETITION + (
    'etude', 'etudes', 'study', 'studies', 'diagnostic', 'diagnostics', 'expertise',
    'conception', 'design', 'consultation architecturale', 'mission d architecte',
    'mission de conception', 'mission d accompagnement', 'maitrise d oeuvre',
    'suivi des travaux', 'suivi de travaux', 'suivi architectural', 'direction architecturale',
    'supervision architecturale', 'architectural supervision', 'project management',
    'assistance a maitrise d ouvrage', 'amo', 'assistance technique architecturale',
    'programmation architecturale', 'strategie de valorisation', 'plan amenagement',
    'plan d amenagement', 'plan de sauvegarde',
    'plan de conservation', 'schema directeur', 'masterplan', 'inventaire patrimonial',
    'releve architectural', 'releves architecturaux', 'documentation patrimoniale',
    'services d architecture', 'service d architecture', 'rehabilitation architecturale')
PURE_WORKS = ('travaux de construction', 'travaux construction', 'travaux de restauration',
    'travaux de rehabilitation', 'travaux de confortement', 'travaux d amenagement',
    'travaux de demolition', 'demolition reconstruction', 'execution des travaux',
    'execution de travaux', 'lot gros oeuvre', 'gros oeuvre', 'second oeuvre',
    'installations techniques', 'civil works', 'construction works', 'restoration works',
    'rehabilitation works')
EXECUTION_ACTIONS = ('construction', 'restauration', 'rehabilitation', 'confortement',
    'amenagement', 'demolition', 'reconstruction', 'gros oeuvre', 'second oeuvre')
MAJOR_ASSETS = ('musee', 'theatre', 'centre culturel', 'palais des congres',
    'centre de congres', 'centre d exposition', 'campus', 'universite',
    'complexe hospitalier', 'centre hospitalier universitaire', 'chu',
    'siege regional', 'siege national', 'siege administratif', 'complexe public',
    'complexe architectural', 'grand equipement public', 'equipement culturel',
    'pole universitaire', 'pole hospitalier', 'hospital complex', 'espace public', 'corniche', 'projet urbain',
    'amenagement urbain', 'mixed use', 'usage mixte')
MAJOR_SCALE = ('grand projet', 'projet majeur', 'majeur', 'majeure', 'structurant',
    'structurante', 'emblematique', 'flagship', 'grande echelle', 'large scale',
    'multi batiments', 'ensemble immobilier', 'vaste complexe', 'nouveau campus',
    'grand complexe', 'grand musee', 'grand centre culturel', 'grand equipement',
    'nouveau siege', 'redeveloppement majeur', 'regeneration urbaine')
# Ordinary / non-strategic public works — blocks major-track promotion.
ROUTINE_WORK = ('maintenance', 'entretien', 'reparation courante', 'petit centre',
    'petite extension', 'extension simple', 'unites prescolaires', 'ecole primaire',
    'ecole', 'ecoles', 'lycee', 'lycees', 'college', 'collegial', 'centre communal',
    'centre de sante', 'caserne', 'gendarmerie', 'cimetiere',
    'logements', 'logement de fonction', 'logements de fonction',
    'salle multisports', 'maison du quartier', 'noyau collegial', 'unite scolaire',
    'unites scolaires', 'fromagerie', 'magasin', 'magasins', 'petit batiment',
    'demolition reconstruction')
INFRASTRUCTURE_ONLY = (
    'route', 'routes', 'voirie', 'assainissement', 'reseau d eau', 'reseaux d eau',
    'eau potable', 'canalisation', 'pipeline', 'reseau electrique', 'reseaux electriques',
    'eclairage public', 'eclairage', 'ouvrage hydraulique', 'travaux hydrauliques',
    'topographie', 'topographique', 'geotechnique', 'transport equipment',
    'equipement de transport', 'systeme informatique', 'logiciel',
    'chaussee', 'chaussees', 'parking', 'parkings', 'drainage', 'egout', 'egouts',
    'reseau', 'reseaux', 'revetement', 'enrobe', 'enrobes', 'trottoir', 'trottoirs',
    'carrefour', 'carrefours', 'giratoire', 'signalisation routiere', 'feux de signalisation',
    'adduction', 'station d epuration', 'voirie urbaine', 'genie civil routier',
    'reseaux divers', 'vrd', 'infrastructure routiere', 'travaux routiers',
    'rue', 'rues',
)
DEFAULT_MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD = 20_000_000

# Explainable reason codes (hard policy). Adaptive feedback never invents these.
REASON_ACCEPT_HERITAGE = 'ACCEPT_HERITAGE_PROFESSIONAL_SERVICE'
REASON_ACCEPT_CONCOURS = 'ACCEPT_ARCHITECTURAL_COMPETITION'
REASON_ACCEPT_MAJOR = 'ACCEPT_MAJOR_ARCHITECTURAL_SERVICE'
REASON_REVIEW = 'REVIEW_AMBIGUOUS_RELEVANCE'
REASON_REJECT_EXECUTION = 'REJECT_PURE_EXECUTION'
REASON_REJECT_INFRA = 'REJECT_OUT_OF_SCOPE_INFRASTRUCTURE'
REASON_REJECT_NO_ROLE = 'REJECT_NO_ARCHITECTURAL_ROLE'
REASON_REJECT_NO_DOMAIN = 'REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT'
REASON_REJECT_GENERIC = 'REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC'
REASON_REJECT_IRRELEVANT = 'REJECT_IRRELEVANT_DOMAIN'

_REASON_FROM_LEGACY = {
    'pure_execution_works': REASON_REJECT_EXECUTION,
    'infrastructure_without_architecture': REASON_REJECT_INFRA,
    'topography_only': REASON_REJECT_INFRA,
    'generic_construction_or_infrastructure': REASON_REJECT_INFRA,
    'generic_work_in_historic_location': REASON_REJECT_INFRA,
    'non_architectural_purchase': REASON_REJECT_IRRELEVANT,
    'non_patrimonial_purchase': REASON_REJECT_IRRELEVANT,
    'natural_heritage_only': REASON_REJECT_IRRELEVANT,
    'no_heritage_scope': REASON_REJECT_NO_DOMAIN,
    'generic_architecture_not_strategic': REASON_REJECT_GENERIC,
}


def _hits(text, terms):
    return [term for term in terms if contains(text, term)]


def _corpus(title, scope=None):
    return folded(' '.join(part for part in (title, scope) if part))


def is_pure_execution(text, *, procedure_type=None, professional=None):
    """True when the notice is execution-only (no professional-service role)."""
    professional = professional if professional is not None else _hits(text, PROFESSIONAL_SERVICES)
    if professional:
        return False
    works = _hits(text, PURE_WORKS)
    execution_actions = _hits(text, EXECUTION_ACTIONS)
    starts_as_execution = bool(re.match(
        r'^(travaux|construction|restauration|rehabilitation|confortement|amenagement)\b', text))
    travaux_category = contains(procedure_type or '', 'travaux')
    return bool(works or execution_actions or starts_as_execution or travaux_category)


def has_professional_service_role(text):
    """ARCHERITAGE can act as architect / BE / MOE / AMO / heritage study provider."""
    return _hits(text, PROFESSIONAL_SERVICES)


def has_heritage_context(text):
    """Built heritage / historic fabric / patrimonial mission (not natural or asset-mgmt)."""
    return _evaluate_heritage_signals(text)['decision'] != 'reject'


def has_architectural_context(text):
    return bool(_hits(text, ARCHITECTURAL_SCOPE) or _hits(text, ARCHITECTURAL_COMPETITION)
                or _hits(text, ARCHITECTURAL_ROLE_SIGNALS))


def has_strong_architectural_scope(text):
    """Explicit architectural role wording (études/conception/mission…). Role ≠ project fit."""
    return bool(_hits(text, ARCHITECTURAL_ROLE_SIGNALS))


def is_out_of_scope_infrastructure(text, *, heritage_keep=False):
    """Ordinary roads/networks/sanitation without heritage or major architectural rescue."""
    if heritage_keep:
        return False
    infra = _hits(text, INFRASTRUCTURE_ONLY) or _hits(text, TOPOGRAPHY_ONLY)
    if not infra:
        return False
    # Heritage urban fabric / major public space rescues mixed titles (médina + voies).
    fabric = _hits(text, OLD_FABRIC) or _hits(text, BUILT_HERITAGE_ASSETS) or _hits(text, HERITAGE_ASSETS)
    if fabric or _hits(text, MAJOR_ASSETS):
        if _hits(text, ARCHITECTURE_RESCUE) or _hits(text, ARCHITECTURAL_SCOPE) or _hits(text, PROFESSIONAL_SERVICES):
            return False
        if fabric and _hits(text, HERITAGE_WORK):
            return False
    # Architecture role on infra-only object remains out of scope.
    return True


def is_architectural_competition(text, *, procedure_type=None):
    architecture = _hits(text, ARCHITECTURAL_SCOPE)
    return bool(_hits(text, ARCHITECTURAL_COMPETITION) or
                (procedure_type == 'competition' and architecture))


def is_major_architectural_service(text, *, estimated_amount=None, amount_verified=False,
                                   threshold_mad=DEFAULT_MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD):
    architecture = _hits(text, ARCHITECTURAL_SCOPE)
    assets, scale, routine = _hits(text, MAJOR_ASSETS), _hits(text, MAJOR_SCALE), _hits(text, ROUTINE_WORK)
    high_estimate = bool(amount_verified and estimated_amount is not None and
                         estimated_amount >= threshold_mad)
    proven = bool(architecture and assets and (high_estimate or scale) and not routine)
    reviewable = bool(architecture and assets and not routine and not proven)
    return proven, reviewable, {
        'ARCHITECTURAL_SCOPE': architecture, 'MAJOR_ASSET': assets,
        'MAJOR_SCALE': scale, 'VERIFIED_HIGH_ESTIMATE': high_estimate,
    }


def preliminary_plausible(title, scope=None):
    """Cheap pre-detail filter: reject obvious non-procurement / goods / IT noise."""
    text = _corpus(title, scope)
    if _hits(text, KEYWORDS['NEGATIVE']) or _hits(text, ASSET_MANAGEMENT_CONTEXT):
        return dict(decision='reject', reason_code=REASON_REJECT_IRRELEVANT,
                    rejection_reason='non_architectural_purchase', architecture_scope=False,
                    business_category='REJECT', business_tracks=[], signals={'NEGATIVE': True})
    if is_pure_execution(text):
        return dict(decision='reject', reason_code=REASON_REJECT_EXECUTION,
                    rejection_reason='pure_execution_works', architecture_scope=False,
                    business_category='REJECT', business_tracks=[], signals={'PURE_WORKS': True})
    return dict(decision='continue', reason_code=None)


def _evaluate_heritage_signals(text):
    """Patrimoine-first signals. Scope must describe the procurement, not the buyer mission."""
    hits = lambda terms: _hits(text, terms)
    assets, built_assets = hits(HERITAGE_ASSETS), hits(BUILT_HERITAGE_ASSETS)
    fabric, work = hits(OLD_FABRIC), hits(BUILT_WORK)
    if contains(text, 'ksar sghir') and not contains(text, 'du ksar'):
        assets = [term for term in assets if term != 'ksar']
        built_assets = [term for term in built_assets if term != 'ksar']
    negative, generic = hits(KEYWORDS['NEGATIVE']), hits(GENERIC_WORK)
    broad_context = hits(BROAD_HERITAGE_CONTEXT)
    broad_work = hits(BROAD_HERITAGE_WORK)
    asset_management = hits(ASSET_MANAGEMENT_CONTEXT)
    natural_only = hits(NATURAL_ONLY_CONTEXT) and not hits((
        'patrimoine culturel', 'patrimoine historique', 'heritage culturel',
        'heritage historique', 'cultural heritage', 'historical heritage'))
    patrimonial_architecture = hits(('architecture patrimoniale', 'architectural patrimonial',
        'architecturale patrimoniale', 'architecturales patrimoniales',
        'diagnostic architectural patrimonial'))
    if hits(('patrimonial', 'patrimoniale', 'patrimoniales', 'patrimoniaux')) and hits(ARCHITECTURE_RESCUE):
        patrimonial_architecture = patrimonial_architecture or ['patrimonial_architecture']
    direct_work = hits(HERITAGE_WORK)
    historic_structure = hits(('batiment', 'batiments', 'edifice', 'edifices', 'structure',
        'structures', 'facade', 'facades')) and hits(('historique', 'historiques')) and direct_work
    religious_heritage = hits(('zaouia', 'zaouias', 'mausolee', 'mausolees', 'synagogue',
        'synagogues', 'eglise', 'eglises', 'mosquee', 'mosquees')) and hits((
        'historique', 'historiques', 'patrimonial', 'patrimoniale', 'patrimoniales',
        'restauration', 'rehabilitation', 'conservation', 'sauvegarde'))
    topo = hits(TOPOGRAPHY_ONLY)
    direct_built = bool((built_assets or fabric) and work) or bool(
        patrimonial_architecture or religious_heritage or historic_structure)
    broader_heritage = bool(broad_context and broad_work and not direct_built)
    heritage_facility = hits(('centre d interpretation', 'centre interpretation',
        'espace d interpretation', 'espace visiteurs', 'centre de visiteurs',
        'equipement culturel')) and bool(broad_context or built_assets or fabric)
    broader_heritage = broader_heritage or bool(heritage_facility and not direct_built)
    explicit_intervention = bool(direct_work and (built_assets or fabric)) or bool(
        fabric and (hits(ARCHITECTURE_RESCUE) or hits(ARCHITECTURAL_SCOPE) or
                    hits(('etude', 'etudes', 'diagnostic', 'maitrise d oeuvre'))))
    reason = None
    if negative or asset_management:
        reason = 'non_patrimonial_purchase'
    elif natural_only:
        reason = 'natural_heritage_only'
    elif topo:
        if not direct_built or not hits(ARCHITECTURE_RESCUE):
            reason = 'topography_only'
    if not reason and not (direct_built or broader_heritage):
        reason = 'no_heritage_scope'
    if not reason and generic and not explicit_intervention and not heritage_facility:
        reason = 'generic_construction_or_infrastructure'
    if not reason and generic and fabric and not assets and not explicit_intervention:
        reason = 'generic_work_in_historic_location'
    # Soft P2 only for weak adjacency. Clear patrimonial *studies* (étude/diagnostic/…) stay P1.
    adjacent = bool(fabric and not built_assets and not direct_work and not explicit_intervention) or bool(
        hits(('bati ancien', 'batis anciens', 'tissu ancien', 'tissus anciens')) and
        not assets and not direct_work and not explicit_intervention)
    if fabric and hits(('espace public', 'espaces publics', 'etude urbaine', 'etudes urbaines')):
        adjacent = True
    if topo:
        adjacent = True
    if heritage_facility and not direct_built:
        adjacent = True
    if broader_heritage and not hits((
            'etude', 'etudes', 'diagnostic', 'diagnostics', 'strategie', 'expertise',
            'inventaire', 'documentation', 'interpretation', 'plan de conservation',
            'plan de sauvegarde')):
        adjacent = True
    priority = 3 if reason else 2 if adjacent else 1
    signals = {key: value for key, value in (
        ('HERITAGE_STRONG', built_assets), ('HERITAGE_BROAD', broad_context),
        ('OLD_FABRIC', fabric), ('HERITAGE_WORK', direct_work),
        ('NEGATIVE', negative), ('GENERIC_WORK', generic)) if value}
    return dict(score=-5 if reason else 4 if adjacent else 5, priority=priority,
        signals=signals, decision='reject' if reason else 'review' if adjacent else 'keep',
        rejection_reason=reason, architecture_scope=not bool(reason))


def _evaluate_heritage(title, groups=None, scope=None):
    return _evaluate_heritage_signals(_corpus(title, scope))


def _decision(decision, *, business_category, rejection_reason=None, reason_code=None,
              architecture_scope=True, business_tracks=None, signals=None, score=None, priority=None):
    if reason_code is None and rejection_reason:
        reason_code = _REASON_FROM_LEGACY.get(rejection_reason, REASON_REJECT_IRRELEVANT)
    if reason_code is None and decision == 'keep':
        reason_code = {
            'P1_HERITAGE': REASON_ACCEPT_HERITAGE,
            'P1_CONCOURS': REASON_ACCEPT_CONCOURS,
            'P1_MAJOR_ARCH': REASON_ACCEPT_MAJOR,
        }.get(business_category)
    if reason_code is None and decision == 'review':
        reason_code = REASON_REVIEW
    if priority is None:
        priority = 1 if decision == 'keep' else 2 if decision == 'review' else 3
    if score is None:
        score = 5 if decision == 'keep' else 3 if decision == 'review' else -5
    return dict(score=score, priority=priority, signals=signals or {},
                decision=decision, rejection_reason=rejection_reason, reason_code=reason_code,
                architecture_scope=architecture_scope, business_category=business_category,
                business_tracks=business_tracks or [],
                role_fit=None, domain_fit=None)


def evaluate_relevance(title, groups=None, scope=None, *, estimated_amount=None,
                       amount_verified=False, procedure_type=None,
                       threshold_mad=DEFAULT_MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD):
    """ARCHERITAGE business tracks only: heritage, competition, major architecture.

    Order: pure execution → unrelated → infrastructure → heritage → concours →
    major → generic architecture reject → no role → no domain.

    Architectural role wording (études architecturales, …) is necessary but not
    sufficient: the project must be heritage, competition, or major/strategic.
    """
    text = _corpus(title, scope)
    professional = has_professional_service_role(text)
    arch_role = has_strong_architectural_scope(text) or bool(_hits(text, ARCHITECTURAL_SCOPE))

    # 1. Pure execution
    if is_pure_execution(text, procedure_type=procedure_type, professional=professional):
        works = _hits(text, PURE_WORKS) or _hits(text, EXECUTION_ACTIONS) or [
            folded(procedure_type) or text.split(' ', 1)[0]]
        result = _decision('reject', business_category='REJECT',
                           rejection_reason='pure_execution_works', reason_code=REASON_REJECT_EXECUTION,
                           architecture_scope=False, signals={'PURE_WORKS': works})
        result['role_fit'] = False
        result['domain_fit'] = False
        return result

    heritage = _evaluate_heritage_signals(text)
    heritage_ok = heritage['decision'] != 'reject'
    competition = is_architectural_competition(text, procedure_type=procedure_type)
    major_proven, major_review, major_signals = is_major_architectural_service(
        text, estimated_amount=estimated_amount, amount_verified=amount_verified,
        threshold_mad=threshold_mad)
    major_signals = {k: v for k, v in major_signals.items() if v}

    unrelated = _hits(text, KEYWORDS['NEGATIVE']) or _hits(text, ASSET_MANAGEMENT_CONTEXT)
    if unrelated:
        result = _decision('reject', business_category='REJECT',
                           rejection_reason='non_architectural_purchase',
                           reason_code=REASON_REJECT_IRRELEVANT, architecture_scope=False,
                           signals={**heritage['signals'], 'UNRELATED': unrelated})
        result['role_fit'] = bool(professional)
        result['domain_fit'] = False
        return result

    # 2. Ordinary infrastructure without heritage / major public-space rescue
    if is_out_of_scope_infrastructure(text, heritage_keep=heritage_ok):
        reason = 'topography_only' if heritage.get('rejection_reason') == 'topography_only' else \
            'infrastructure_without_architecture'
        result = _decision('reject', business_category='REJECT', rejection_reason=reason,
                           reason_code=REASON_REJECT_INFRA, architecture_scope=False,
                           signals={**heritage['signals'],
                                    'INFRASTRUCTURE': _hits(text, INFRASTRUCTURE_ONLY) or _hits(text, TOPOGRAPHY_ONLY)})
        result['role_fit'] = bool(professional)
        result['domain_fit'] = False
        return result

    # 3. Track A — Heritage / patrimonial professional service
    if heritage_ok:
        category = 'P1_HERITAGE' if heritage['decision'] == 'keep' else 'P2_REVIEW'
        result = {**heritage, 'business_category': category, 'business_tracks': ['HERITAGE'],
                  'reason_code': REASON_ACCEPT_HERITAGE if category == 'P1_HERITAGE' else REASON_REVIEW,
                  'role_fit': bool(professional) or category == 'P2_REVIEW',
                  'domain_fit': True}
        return result

    # 4. Track B — Architectural competition / consultation
    if competition:
        result = _decision('keep', business_category='P1_CONCOURS', reason_code=REASON_ACCEPT_CONCOURS,
                           business_tracks=['CONCOURS'], signals={**major_signals, 'COMPETITION': True})
        result['role_fit'] = True
        result['domain_fit'] = True
        return result

    # 5. Track C — Major / strategic architectural project (needs professional role)
    if professional and major_proven:
        result = _decision('keep', business_category='P1_MAJOR_ARCH', reason_code=REASON_ACCEPT_MAJOR,
                           business_tracks=['MAJOR_ARCH'], signals=major_signals)
        result['role_fit'] = True
        result['domain_fit'] = True
        return result
    if professional and major_review:
        # Plausible major asset without verified scale — human review only.
        result = _decision('review', business_category='P2_REVIEW', reason_code=REASON_REVIEW,
                           business_tracks=['MAJOR_ARCH'], signals=major_signals, score=3, priority=2)
        result['role_fit'] = True
        result['domain_fit'] = True
        return result

    # 6. Architectural role without an approved project family → generic reject
    if professional and arch_role:
        result = _decision(
            'reject', business_category='REJECT',
            rejection_reason='generic_architecture_not_strategic',
            reason_code=REASON_REJECT_GENERIC, architecture_scope=True,
            signals={**heritage['signals'], **major_signals,
                     'ARCHITECTURAL_ROLE': _hits(text, ARCHITECTURAL_ROLE_SIGNALS) or _hits(text, ARCHITECTURAL_SCOPE)})
        result['role_fit'] = True
        result['domain_fit'] = False
        return result

    # 7. No professional role
    if not professional:
        result = _decision('reject', business_category='REJECT',
                           rejection_reason='no_architectural_role',
                           reason_code=REASON_REJECT_NO_ROLE, architecture_scope=False,
                           signals={**heritage['signals'], **major_signals})
        result['role_fit'] = False
        result['domain_fit'] = False
        return result

    # 8. Professional role without heritage / architecture project context
    legacy = heritage.get('rejection_reason') or 'no_heritage_scope'
    result = _decision('reject', business_category='REJECT', rejection_reason=legacy,
                       reason_code=_REASON_FROM_LEGACY.get(legacy, REASON_REJECT_NO_DOMAIN),
                       architecture_scope=False, signals={**heritage['signals'], **major_signals})
    result['role_fit'] = True
    result['domain_fit'] = False
    return result


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


def decide_relevance(title, *, scope=None, estimated_amount=None, amount_verified=False,
                     procedure_type=None, threshold_mad=20_000_000):
    """Single obvious Radar 1 business-relevance entrypoint."""
    return evaluate_relevance(
        title, scope=scope, estimated_amount=estimated_amount,
        amount_verified=amount_verified, procedure_type=procedure_type,
        threshold_mad=threshold_mad)
