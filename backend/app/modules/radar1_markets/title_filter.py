"""Cheap index selection; official evidence and the business policy decide acceptance."""
import re
import unicodedata


def normalize(value):
    value = unicodedata.normalize('NFKD', value or '').lower().replace('œ', 'oe')
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = value.translate(str.maketrans({'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ى': 'ي', 'ـ': ''}))
    return re.sub(r'[^\w]+', ' ', value).strip()


# Explicit Arabic equivalents feed the existing French policy without changing
# the stored title or inferring project scope from the buyer's name.
def policy_text(value):
    text = normalize(value)
    equivalents = {
        'دراسة': 'etude', 'دراسات': 'etudes', 'تقنية': 'technique',
        'تتبع': 'suivi', 'اشراف': 'suivi', 'معمارية': 'architecturale',
        'معماري': 'architectural', 'تصميم': 'conception', 'ترميم': 'restauration',
        'الهندسة المعمارية': 'architecture', 'تثمين': 'valorisation',
        'تاهيل': 'rehabilitation', 'المدينة العتيقة': 'ancienne medina',
        'التراث': 'patrimoine', 'الاسوار': 'remparts', 'القصبة': 'kasbah',
        'لقصر': 'ksar', 'القصر': 'ksar', 'القصور': 'ksour', 'متحف': 'musee',
        'مدرسة': 'ecole', 'مدارس': 'ecoles', 'ثانوية': 'lycee',
        'اشغال': 'travaux', 'التطهير': 'assainissement', 'الطرق': 'voirie',
    }
    additions = dict.fromkeys(french for arabic, french in equivalents.items()
                             if arabic in text and not re.search(r'\b' + re.escape(french) + r'\b', text))
    return ' '.join([text, *additions]).strip()


def select_title(title, procedure='', category=''):
    text = policy_text(title)
    procedure = normalize(procedure)
    service = bool(re.search(r'\b(etudes?|suivi|diagnostic|expertise|conception|maitrise d oeuvre|charte|plan d amenagement|sauvegarde|controle|assistance)\b', text))
    competition = ('architectur' in text + procedure and any(w in text + procedure for w in ('concours', 'consultation architectur', 'consultations architectur', 'مسابقة'))) or 'concours de conception' in text
    heritage = any(w in text for w in ('patrimoine', 'patrimonial', 'ancienne medina', 'medina', 'rempart', 'muraille', 'monument historique', 'kasbah', 'ksar', 'fortification', 'historique', 'القصور', 'القصر', 'لقصر'))
    major = any(w in text for w in ('musee', 'campus', 'universit', 'hospital', 'hopital', 'centre culturel', 'complexe culturel', 'grand complexe', 'siege', 'corniche'))
    unrelated = any(w in text for w in ('informatique', 'logiciel', 'sauvegarde des donnees', 'fournitures', 'gardiennage', 'nettoyage', 'restauration collective', 'repas', 'patrimoine foncier', 'conservation des eaux', 'conservation des sols', 'معلوماتي', 'لوازم', 'حراسة'))
    ordinary = bool(re.search(r'\bista\b', text)) or any(w in text for w in ('ecole', 'lycee', 'scolaire', 'ofppt', 'logement de fonction', 'logements de fonction', 'logements du personnel', 'logement du personnel', 'assainissement', 'voirie', 'route ', 'routes '))
    university = any(w in text for w in ('universit', 'campus', 'ecole superieure', 'enseignement superieur'))
    truncated = bool(re.search(r'(?:\.\.\.|…)\s*$', title or ''))
    mixed_scope = truncated and any(w in text for w in ('mosquee', 'mosquees', 'مسجد'))
    incomplete = not text.strip() or text.strip() in {'consultation pmmp', 'details', 'detail'} or len(normalize(title)) < 20
    # Truncation alone is not a licence to accept generic execution tenders.
    if unrelated:
        return dict(decision='reject', reason_code='unrelated_scope', priority=9)
    if normalize(category) == 'fournitures' and not service and not competition:
        return dict(decision='reject', reason_code='supply_purchase', priority=9)
    explicit_heritage = heritage and any(w in text for w in ('patrimonial', 'restauration', 'rempart', 'monument historique', 'sauvegarde'))
    if ordinary and not explicit_heritage and not university and not mixed_scope:
        return dict(decision='reject', reason_code='ordinary_facility_or_infrastructure', priority=9)
    if 'topograph' in text and not heritage and not major and not competition:
        return dict(decision='reject', reason_code='unrelated_topography', priority=9)
    execution = ('travaux' in text or normalize(category) == 'travaux') and not service and not competition
    if execution and not (truncated and heritage and not text.startswith('travaux')):
        return dict(decision='reject', reason_code='pure_execution', priority=9)
    if heritage and service:
        return dict(decision='continue', reason_code='A_heritage_service', priority=1)
    if competition:
        return dict(decision='continue', reason_code='C_architectural_competition', priority=2)
    if major and service:
        return dict(decision='continue', reason_code='D_major_architecture', priority=3)
    if incomplete or (truncated and (heritage or service or major)):
        return dict(decision='continue', reason_code='incomplete_scope_requires_detail', priority=4)
    if re.search(r'[\u0600-\u06ff]', title or ''):
        return dict(decision='continue', reason_code='arabic_scope_requires_detail', priority=4)
    return dict(decision='reject', reason_code='no_relevant_title_context', priority=9)
