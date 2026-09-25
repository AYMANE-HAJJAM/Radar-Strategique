"""Plain-text result presentation. Never interpolate data into HTML/Markdown."""
from datetime import date
from urllib.parse import urlsplit

REASONS = {
    'OFFICIAL_URL_NOT_CONFIRMED': 'Lien officiel à confirmer',
    'MISSING_URL': 'Lien officiel à confirmer',
    'OFFICIAL_SOURCE_CONFLICT': 'Sources officielles contradictoires',
    'STATUS_UNCLEAR': 'Statut à confirmer',
    'MISSING_SOURCE_STATUS': 'Statut à confirmer',
    'DEADLINE_UNCLEAR': 'Échéance à confirmer',
    'GEOGRAPHY_AMBIGUOUS': 'Localisation à confirmer',
    'MEDIUM_AI_CONFIDENCE': 'Pertinence à confirmer',
    'SECONDARY_SOURCE_ONLY': 'Source secondaire',
    'REFERENCE_CONFLICT': 'Références contradictoires',
    'MISSING_PUBLICATION_DATE': 'Date de publication à confirmer',
    'MISSING_PUBLICATION_DATE|OFFICIAL_DATE_EVIDENCE': 'Date de publication à confirmer',
    'MISSING_INSTITUTION': 'Organisme à confirmer',
    'MISSING_LOCATION_EVIDENCE': 'Localisation à confirmer',
    'PROCEDURE_UNCLEAR': 'Type de procédure à confirmer',
    'FUTURE_DATE_CONFLICT': 'Date de publication à confirmer',
    'AI_REVIEW_REQUESTED': 'Pertinence à confirmer',
    'ANALYSIS_LIMIT_REACHED': 'Analyse complémentaire nécessaire',
    'DRY_RUN_NO_ANALYSIS': 'Analyse complémentaire nécessaire',
}
STATUS = {'open': 'Ouvert', 'closed': 'Clôturé', 'expired': 'Expiré', 'awarded': 'Attribué',
          'cancelled': 'Annulé', 'unknown': 'À confirmer'}
PROCEDURES = {'tender': 'Appel d’offres', 'consultation': 'Consultation',
    'architectural_consultation': 'Consultation architecturale', 'competition': 'Concours',
    'purchase_order': 'Bon de commande', 'study': 'Étude', 'intellectual_services': 'Prestation intellectuelle',
    'amo': 'Assistance à maîtrise d’ouvrage', 'moe': 'Maîtrise d’œuvre',
    'expression_of_interest': 'Appel à manifestation d’intérêt'}
LINKS = {'VERIFIED_DIRECT': 'Annonce officielle PMMP', 'VERIFIED_INSTITUTIONAL': 'Page officielle de l’institution',
    'INDIRECT_PMMP': 'Accès indirect par PMMP', 'SECONDARY_ONLY': 'Source secondaire', 'NOT_FOUND': 'Lien à confirmer',
    'officiel PMMP': 'Annonce officielle PMMP', 'institutionnel officiel': 'Page officielle de l’institution',
    'PMMP indirect': 'Accès indirect par PMMP', 'secondaire (non confirmé)': 'Source secondaire',
    'indisponible': 'Lien à confirmer'}
CATEGORIES = {'P1_HERITAGE': '🏛 Patrimoine', 'P1_MAJOR_ARCH': '🏗 Grand projet',
              'P1_CONCOURS': '🏆 Concours architectural', 'P2_REVIEW': '🔎 À qualifier'}


def clean(value):
    text = ' '.join(str(value or '').split())
    return '' if text.casefold() in {'', '—', '-', 'unknown', 'none', 'null', 'n/a'} else text


def truncate(value, limit=115):
    text = clean(value)
    if len(text) <= limit:
        return text
    prefix = text[:limit-1]
    # Prefer word boundaries to splitting references and place names.
    if ' ' in prefix:
        prefix = prefix.rsplit(' ', 1)[0]
    return prefix.rstrip(' ,;—-') + '…'


def bounded(text):
    # Telegram entity offsets use UTF-16; this also bounds emoji-heavy source text.
    encoded = text.encode('utf-16-le')
    return text if len(encoded) <= 8000 else encoded[:7998].decode('utf-16-le', errors='ignore').rstrip() + '…'


def date_label(value):
    value = clean(value)
    if not value:
        return ''
    try:
        return date.fromisoformat(value).strftime('%d/%m/%Y')
    except ValueError:
        return ''


def amount_label(amount, currency=None, tax_mode=None):
    if amount is None:
        return ''
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ''
    number = f'{value:,.2f}'.replace(',', ' ').replace('.00', '')
    suffix = ' '.join(part for part in (clean(currency), clean(tax_mode) if tax_mode != 'UNKNOWN' else '') if part)
    return number + (f' {suffix}' if suffix else '')


def review_reasons(value):
    codes = [part.strip().upper() for part in (value or '').split(';') if part.strip()]
    ordered = [code for code in REASONS if code in codes] + [code for code in codes if code not in REASONS]
    return list(dict.fromkeys(REASONS.get(code, 'Informations complémentaires à contrôler') for code in ordered))


def format_review_reason(value):
    reasons = review_reasons(value)
    return reasons[0] if reasons else ''


def format_source_label(item):
    source = clean(item.get('source'))
    raw = item.get('url') or source
    host = (urlsplit(raw if '://' in raw else 'https://' + raw).hostname or '').lower()
    if host == 'marchespublics.gov.ma' or host.endswith('.marchespublics.gov.ma'):
        return 'PMMP'
    if host in {'casa-amenagement.ma', 'www.casa-amenagement.ma'}:
        return 'Casablanca Aménagement'
    if item.get('link_label') == 'institutionnel officiel' and clean(item.get('institution')):
        return truncate(item['institution'], 120)
    if '://' in source or '/' in source:
        return truncate(host.removeprefix('www.'), 80)
    return truncate(source or host.removeprefix('www.'), 80)


def format_result_card(item, number, mode):
    lines = [f'[{number}] {truncate(item.get("title"))}']
    category = CATEGORIES.get(item.get('business_category'))
    if category:
        lines.append(category)
    if mode == 'pending' and item.get('discovery_status') == 'UPDATED':
        lines.append('🔄 Mise à jour')
    for field, label in (('institution', '🏛️'), ('city', '📍'), ('reference', '📄 Réf :')):
        if clean(item.get(field)):
            lines.append(f'{label} {truncate(item[field], 100)}')
    if 'estimated_amount' in item:
        estimate = amount_label(item.get('estimated_amount'), item.get('estimated_currency'),
                                item.get('estimated_amount_tax_mode'))
        lines.append(f'💰 Estimation : {estimate}' if estimate else '💰 Estimation : non vérifiée')
        if estimate and not item.get('estimated_amount_verified'):
            lines.append('⚠️ Source secondaire — à confirmer')
    publication = date_label(item.get('publication'))
    if publication:
        lines.append(f'📅 Publication : {publication}')
    deadline = date_label(item.get('deadline'))
    if deadline:
        time = clean(item.get('deadline_time'))
        lines.append(f'⏳ Échéance : {deadline}' + (f' à {time}' if time else ''))
    elif mode == 'pending' and 'DEADLINE_UNCLEAR' in (item.get('reason') or ''):
        lines.append('⏳ Échéance : à confirmer')
    document_label = 'Règlement / DCE' if item.get('business_category') == 'P1_CONCOURS' else 'DCE'
    if item.get('dce_available'):
        lines.append(f'📎 {document_label} : disponible' + (' — téléchargement manuel' if item.get('dce_access_mode') == 'FORM_REQUIRED' else ''))
    else:
        lines.append(f'📎 {document_label} : non vérifié')
    if item.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE':
        lines.append('⚠️ Lien officiel à confirmer')
    source = format_source_label(item)
    if source:
        lines.append(f'🔗 Source : {source}')
    if mode == 'pending':
        reason = format_review_reason(item.get('reason'))
        lines.append('⚠️ À vérifier' + (f' : {reason[0].lower() + reason[1:]}' if reason else ''))
    else:
        label = STATUS.get(item.get('status'))
        if label and label != 'À confirmer':
            lines.append(f'✅ Statut : {label}')
    return bounded('\n'.join(lines))


def format_result_details(item):
    lines = [clean(item.get('title'))]
    category = CATEGORIES.get(item.get('business_category'))
    if category:
        lines.append(category)
    for field, label in (('institution', 'Institution'), ('city', 'Ville / région'), ('reference', 'Référence')):
        if clean(item.get(field)):
            lines.append(f'{label} : {truncate(item[field], 220)}')
    procedure = PROCEDURES.get(item.get('procedure'))
    if procedure:
        lines.append(f'Type : {procedure}')
    estimate = amount_label(item.get('estimated_amount'), item.get('estimated_currency'),
                            item.get('estimated_amount_tax_mode'))
    if estimate:
        provenance = clean(item.get('estimated_amount_source'))
        confidence = 'vérifiée' if item.get('estimated_amount_verified') else 'à confirmer'
        lines.append(f'Estimation : {estimate} — {confidence}' + (f' ({provenance})' if provenance else ''))
    else:
        lines.append('Estimation : non vérifiée')
    lots = item.get('estimated_lots') or []
    for lot in lots:
        value = amount_label(lot.get('amount'), lot.get('currency'), lot.get('tax_mode'))
        if value:
            lines.append(f'Lot {clean(lot.get("lot"))} : {value}')
    bond = amount_label(item.get('provisional_bond_amount'), item.get('provisional_bond_currency'))
    if bond:
        lines.append(f'Caution provisoire : {bond}')
    prize = amount_label(item.get('competition_prize_amount'), item.get('competition_prize_currency'))
    if prize:
        lines.append(f'Prime / indemnité : {prize}')
    if clean(item.get('eligibility_conditions')):
        lines.append('Éligibilité : ' + truncate(item['eligibility_conditions'], 500))
    for field, label in (('publication', 'Publication'), ('deadline', 'Échéance')):
        if date_label(item.get(field)):
            suffix = f' à {item.get("deadline_time")}' if field == 'deadline' and clean(item.get('deadline_time')) else ''
            lines.append(f'{label} : {date_label(item[field])}{suffix}')
    if item.get('document_types'):
        lines.append('Documents : ' + ', '.join(item['document_types']))
    for field, label in (
        ('announcement_type', 'Type d’annonce'),
        ('main_category', 'Catégorie'),
        ('qualifications', 'Qualifications'),
        ('withdrawal_mode', 'Retrait'),
        ('deposit_mode', 'Dépôt'),
        ('opening_place', 'Ouverture des plis'),
    ):
        if clean(item.get(field)):
            lines.append(f'{label} : {truncate(item[field], 220)}')
    domains = item.get('activity_domains') or []
    if domains:
        lines.append('Domaines d’activité : ' + truncate(', '.join(domains), 220))
    if item.get('sme_reserved') is True:
        lines.append('Réservé TPE/PME : oui')
    plan = item.get('plan_price')
    if isinstance(plan, dict) and plan.get('amount') is not None:
        lines.append('Prix des plans : ' + amount_label(plan.get('amount'), plan.get('currency')))
    elif clean(plan):
        lines.append('Prix des plans : ' + truncate(plan, 80))
    if item.get('status') in STATUS:
        lines.append(f'Statut : {STATUS[item["status"]]}')
    source = format_source_label(item)
    if item.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE':
        source = ('Agrégateur de marchés publics' if item.get('source_type') == 'PROCUREMENT_AGGREGATOR'
                  else 'Liste institutionnelle') + (f' ({source})' if source else '')
        lines.append('Vérification officielle : À confirmer')
    if source:
        lines.append(f'Source : {source}')
    lines.append('📎 DCE : disponible' if item.get('dce_available') else '📎 DCE : non vérifié')
    lines.append('Lien : ' + LINKS.get(item.get('link_label'), 'Lien à confirmer'))
    reasons = review_reasons(item.get('reason'))
    if reasons:
        lines.append('À contrôler : ' + '; '.join(reasons))
    return bounded('\n'.join(lines))
