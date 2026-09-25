"""Canonical PMMP / official procurement HTML parsing.

Listing and detail entrypoints live here. HTTP fetch is injected via a pages reader
(see app.integrations.http.html); this module does not open network connections.
"""
import re
from urllib.parse import urljoin, urlsplit

from app.modules.radar1_markets.policy import folded, detail_url, aggregate_title
from app.integrations.openai.base import SearchHit
from app.integrations.pmmp.client import is_direct_notice, is_pmmp
from app.integrations.http.html import Page


def extract_rows(page, discovery_url):
    """Each table row or linked detail is its own discovery; never emit the list title."""
    hits = []
    headers = None
    for index, row in enumerate(page.rows):
        cells = page.table_rows[index] if index < len(page.table_rows) else []
        labels = [field_name(cell) for cell in cells]
        if labels.count(None) < len(labels) and 'title' in labels and ('reference' in labels or 'institution' in labels):
            headers = labels
            continue
        fragment = Page('')
        fragment.texts = page.row_parts[index] if index < len(page.row_parts) else [row]
        labelled = labelled_fields(fragment)
        refs = [m for m in re.finditer(r'\b[A-Z0-9-]*\d+[A-Z0-9-]*(?:/[A-Z0-9-]+){1,4}\b', row, re.I)
                if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}|\d{4}/\d{1,2}/\d{1,2}', m.group())]
        links = page.row_links[index] if index < len(page.row_links) else []
        direct = next((urljoin(discovery_url, href) for href, _ in links
                       if is_direct_notice(urljoin(discovery_url, href))), None)
        if not direct and not refs and any('reference' in folded(cell) and 'objet' in folded(cell) for cell in cells):
            continue
        if not refs and not labelled.get('reference') and not direct:
            continue
        link = next(((urljoin(discovery_url, href), label) for href, label in links
                     if label.strip() and label.strip() in row and detail_url(urljoin(discovery_url, href))), None)
        values = {key: value for key, value in zip(headers or [], cells) if key and value}
        if values.get('title'):
            values['title'] = re.sub(r'^\s*\[[^\]]+\]\s*', '', values['title'])
        for key in ('deadline', 'publication_date'):
            if key in values:
                match = re.search(r'\b\d{2}/\d{2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b', values[key])
                if match:
                    values[key] = match.group()
        values = {**labelled, **values}
        if direct and is_pmmp(discovery_url) and len(cells) >= 5:
            code = re.match(r'\s*([.A-Z0-9_/-]+)', cells[2], re.I)
            if code and any(char.isdigit() for char in code.group(1)):
                values['reference'] = code.group(1)
            for field, cell in (('publication_date', cells[1]), ('deadline', cells[4])):
                stamp = re.search(r'\b\d{2}/\d{2}/\d{4}\b', cell)
                if stamp:
                    values[field] = stamp.group()
        # PMMP combines several labelled fields into one table cell. A detail
        # link with a numeric consultation ID remains usable even without a ref.
        if refs:
            values.setdefault('reference', refs[0].group())
        values.setdefault('title', (values.get('reference') or 'Consultation PMMP') if direct else ' '.join(row.split())[:2000])
        hits.append(SearchHit(**values, url=direct or (link[0] if link else discovery_url), kind='tender', evidence=row[:20000]))
    if not hits:
        for text, links in page.articles:
            detail = next((urljoin(discovery_url, href) for href, _ in links
                           if detail_url(urljoin(discovery_url, href))), None)
            if not detail:
                continue
            reference = re.match(r'\s*([.A-Z0-9_/-]*\d[.A-Z0-9_/-]*)\b', text, re.I)
            deadline = re.search(r'date limite\s*:\s*(\d{2}/\d{2}/\d{4})', text, re.I)
            label = next((label.strip() for href, label in links
                          if urljoin(discovery_url, href) == detail and len(label.strip()) > 20), '')
            before_deadline = re.split(r'date limite\s*:', text, flags=re.I)[0]
            buyer = before_deadline
            if label and label in buyer:
                buyer = buyer.split(label, 1)[1]
            buyer = re.sub(r'^\s*Services\s*', '', buyer).strip()
            hits.append(SearchHit(title=label or text[:2000], url=detail,
                reference=reference.group(1) if reference else None,
                institution=buyer[:255] or None,
                deadline=deadline.group(1) if deadline else None,
                status='open' if deadline else None, kind='tender', evidence=text[:20000]))
    if not hits:
        for href, label in page.links:
            url = urljoin(discovery_url, href)
            if detail_url(url) and (len(label.strip()) > 25 or is_direct_notice(url)):
                hits.append(SearchHit(title=label.strip()[:2000], url=url, evidence=label,
                                      kind='discovery_page' if len(label.strip()) <= 25 else 'tender'))
    return hits[:100]


LABELS = {
    'reference': ('ref', 'reference', 'reference de la consultation', 'numero'),
    'title': ('objet', 'objet de la consultation', 'intitule'),
    'institution': ('acheteur public', 'acheteur', 'organisme', 'maitre d ouvrage', 'institution'),
    'deadline': ('echeance', 'date et heure limite de remise des plis', 'date limite de remise des plis',
                 'date limite', 'date d ouverture des plis', 'date et heure limite'),
    'publication_date': ('date de publication', 'publie le'),
    'estimated_amount': ('estimation', 'estimation du cout des prestations', 'montant estimatif',
                         'estimation du marche', 'cout estimatif', 'budget estime',
                         'valeur estimee', 'montant ttc', 'estimation ttc'),
    'provisional_bond': ('caution provisoire', 'garantie provisoire', 'bid security'),
    'competition_prize': ('prime du concours', 'indemnite', 'indemnite du concours',
                          'honoraires', 'prix du concours'),
    'eligibility_conditions': ('conditions d eligibilite', 'conditions de participation',
                               'criteres d eligibilite'),
    'location': ('lieu d execution', 'lieux d execution', 'localisation', 'ville'),
    'procedure_type': ('procedure', 'type de procedure'),
    'status': ('statut', 'etat'),
    'announcement_type': ('type d annonce', 'type annonce', 'nature de l annonce'),
    'main_category': ('categorie principale', 'categorie', 'domaine principal'),
    'allotment': ('allotissement', 'alloti', 'marche alloti'),
    'sme_reserved': ('reserve aux tpe', 'reserve aux pme', 'reserve tpe pme', 'reserve aux tpe pme'),
    'activity_domains': ('domaines d activite', 'domaine d activite', 'secteurs d activite'),
    'withdrawal_mode': ('mode de retrait', 'retrait des dossiers', 'retrait du dossier',
                        'adresse de retrait', 'lieu de retrait'),
    'deposit_mode': ('mode de depot', 'depot des plis', 'adresse de depot', 'lieu de depot'),
    'opening_place': ('lieu d ouverture des plis', 'ouverture des plis', 'lieu d ouverture'),
    'plan_price': ('prix d acquisition des plans', 'prix des plans', 'prix du dossier',
                   'cout d acquisition'),
    'qualifications': ('qualifications', 'agrement', 'agrements', 'classe', 'classes',
                       'categories professionnelles'),
    'documents_notice': ('prospectus et notices', 'prospectus', 'notices', 'documents'),
    'meeting': ('reunion', 'reunion obligatoire', 'reunion de clarification'),
    'site_visit': ('visite des lieux', 'visite de site', 'visite'),
    'variant': ('variante', 'variantes'),
    'admin_contact': ('contact administratif', 'contact', 'personne a contacter',
                      'responsable administratif'),
}


def _amount(value):
    """Parse an explicitly labelled amount without guessing its currency.

    Must not fold the numeric text: fold_text replaces decimal commas with spaces
    and would turn ``28 400 000,00`` into ``2840000000``.
    """
    text = ' '.join(str(value or '').replace('\u00a0', ' ').split())
    if not text:
        return None, None
    scale_match = re.search(r'\b(milliards?|millions?|mmdh|mdh)\b', text, re.I)
    currency_match = re.search(r'\b(mad|dh|dhs|eur|usd)\b', text, re.I)
    # French thousands (spaces) + optional decimal comma/dot; or plain integer.
    number_match = re.search(
        r'(?<!\d)(\d{1,3}(?:[ ]\d{3})+|\d+)(?:([.,])(\d{1,2}))?(?!\d)',
        text)
    if not number_match:
        return None, None
    whole, _sep, fraction = number_match.group(1), number_match.group(2), number_match.group(3)
    digits = whole.replace(' ', '')
    normalized = digits + (('.' + fraction) if fraction is not None else '')
    try:
        amount = float(normalized)
    except ValueError:
        return None, None
    scale = scale_match.group(1).lower() if scale_match else None
    multiplier = (1_000_000_000 if scale in {'milliard', 'milliards', 'mmdh'} else
                  1_000_000 if scale in {'million', 'millions', 'mdh'} else 1)
    currency_token = currency_match.group(1).lower() if currency_match else None
    currency = ('MAD' if currency_token in {'mad', 'dh', 'dhs'} or scale in {'mdh', 'mmdh'}
                else currency_token.upper() if currency_token else None)
    return amount * multiplier, currency


def _amount_context_hints(label_text, value_text):
    """Merge TTC/HT/MAD hints from the PMMP label into the value for downstream parse."""
    hint = folded(label_text or '')
    value = str(value_text or '').strip()
    if not value:
        return value
    extras = []
    combined = folded(value)
    if 'ttc' in hint and 'ttc' not in combined:
        extras.append('TTC')
    if re.search(r'\bht\b', hint) and not re.search(r'\bht\b', combined):
        extras.append('HT')
    if any(token in hint for token in ('dhs', 'mad')) and not re.search(
            r'\b(mad|dh|dhs|eur|usd)\b', combined, re.I):
        extras.append('MAD')
    if ' dh' in f' {hint}' and not re.search(r'\b(mad|dh|dhs|eur|usd)\b', combined, re.I):
        extras.append('MAD')
    return (value + ' ' + ' '.join(dict.fromkeys(extras))).strip() if extras else value


def procurement_metadata(page, url):
    """Extract procurement facts; a bond/security label can never become budget."""
    fields = labelled_fields(page, procurement=False)
    official = is_direct_notice(url) or is_pmmp(url)
    source = ('PMMP' if is_pmmp(url) else 'OFFICIAL_INSTITUTION' if official else
              'MARCHE_FACILE' if 'marchefacile' in (urlsplit(url).hostname or '').lower() else 'SECONDARY')
    result = {}
    estimate_text = fields.get('estimated_amount')
    if estimate_text:
        amount, currency = _amount(estimate_text)
        if amount is not None:
            tax = ('TTC' if re.search(r'\bttc\b', folded(estimate_text)) else
                   'HT' if re.search(r'\bht\b', folded(estimate_text)) else 'UNKNOWN')
            if currency is None and re.search(r'\b(mad|dh|dhs)\b', folded(estimate_text)):
                currency = 'MAD'
            result.update(estimated_amount=amount, estimated_currency=currency or ('MAD' if official else None),
                          estimated_amount_tax_mode=tax,
                          estimated_amount_source=source, estimated_amount_verified=official)
    bond_text = fields.get('provisional_bond')
    if bond_text is not None and str(bond_text).strip() != '':
        amount, currency = _amount(bond_text)
        if amount is not None:
            if currency is None and official:
                currency = 'MAD'
            result.update(provisional_bond_amount=amount, provisional_bond_currency=currency)
    prize_text = fields.get('competition_prize')
    if prize_text:
        amount, currency = _amount(prize_text)
        if amount is not None:
            result.update(competition_prize_amount=amount, competition_prize_currency=currency)
    if fields.get('eligibility_conditions'):
        result['eligibility_conditions'] = fields['eligibility_conditions']
    lots = []
    for match in re.finditer(r'\blot\s*(?:n[o°]?\s*)?(\d+)\s*[:\-]\s*([^;|]{1,100})', page.text, re.I):
        amount, currency = _amount(match.group(2))
        if amount is not None:
            lots.append({'lot': match.group(1), 'amount': amount, 'currency': currency,
                         'tax_mode': 'TTC' if 'ttc' in folded(match.group(2)) else
                         'HT' if re.search(r'\bht\b', folded(match.group(2))) else 'UNKNOWN'})
    if lots:
        result['estimated_lots'] = lots
    documents = [name.upper() for name in ('dce', 'cps', 'rc', 'bpu', 'dqe', 'plans', 'annexes')
                 if re.search(rf'\b{re.escape(name)}\b', folded(page.text))]
    if documents:
        result['document_types'] = list(dict.fromkeys(documents))
    result['competition_regulation_available'] = bool(
        re.search(r'reglement (?:du |de )?concours', folded(page.text)))
    if result['competition_regulation_available']:
        result['document_types'] = list(dict.fromkeys([*(result.get('document_types') or []), 'REGLEMENT']))
    # Extra official PMMP labels (structured later in build_pmmp_detail).
    for key in ('announcement_type', 'main_category', 'allotment', 'sme_reserved',
                'activity_domains', 'withdrawal_mode', 'deposit_mode', 'opening_place',
                'plan_price', 'qualifications', 'documents_notice', 'meeting', 'site_visit',
                'variant', 'admin_contact'):
        if fields.get(key):
            result[key] = fields[key]
    if fields.get('plan_price'):
        amount, currency = _amount(fields['plan_price'])
        if amount is not None:
            result['plan_price_amount'] = amount
            result['plan_price_currency'] = currency
    return result


def build_pmmp_detail(fields, url, page_text=''):
    """Structured official PMMP snapshot for radar_metadata (no migration)."""
    docs = fields.get('document_types') or []
    text = folded(page_text)
    sme = fields.get('sme_reserved')
    sme_flag = None
    if sme:
        sme_flag = not any(token in folded(sme) for token in ('non', 'aucune', 'pas'))
    elif re.search(r'reserve(?:e)? (?:aux )?tpe|reserve(?:e)? (?:aux )?pme', text):
        sme_flag = True
    estimate = None
    if fields.get('estimated_amount') is not None:
        estimate = {
            'amount': fields.get('estimated_amount'),
            'currency': fields.get('estimated_currency'),
            'tax_basis': fields.get('estimated_amount_tax_mode'),
            'verified': bool(fields.get('estimated_amount_verified')),
            'source': fields.get('estimated_amount_source'),
        }
    bond = None
    if fields.get('provisional_bond_amount') is not None:
        bond = {
            'amount': fields.get('provisional_bond_amount'),
            'currency': fields.get('provisional_bond_currency'),
        }
    deadline = None
    if fields.get('deadline') or fields.get('deadline_time'):
        deadline = {
            'date': str(fields['deadline']) if fields.get('deadline') else None,
            'time': fields.get('deadline_time'),
        }
    domains = fields.get('activity_domains')
    if isinstance(domains, str):
        domains = [part.strip() for part in re.split(r'[;|/]| - ', domains) if part.strip()][:20]
    return {
        'reference': fields.get('reference'),
        'buyer': fields.get('institution'),
        'object': fields.get('title'),
        'announcement_type': fields.get('announcement_type'),
        'procedure': fields.get('procedure_type'),
        'main_category': fields.get('main_category'),
        'execution_location': fields.get('location_evidence') or fields.get('location'),
        'estimate': estimate,
        'deadline': deadline,
        'provisional_guarantee': bond,
        'activity_domains': domains or [],
        'sme_reserved': sme_flag,
        'allotment': fields.get('allotment'),
        'withdrawal_mode': fields.get('withdrawal_mode'),
        'deposit_mode': fields.get('deposit_mode'),
        'opening_place': fields.get('opening_place'),
        'plan_price': ({'amount': fields.get('plan_price_amount'),
                        'currency': fields.get('plan_price_currency')}
                       if fields.get('plan_price_amount') is not None else fields.get('plan_price')),
        'qualifications': fields.get('qualifications'),
        'documents_notice': fields.get('documents_notice'),
        'meeting': fields.get('meeting'),
        'site_visit': fields.get('site_visit'),
        'variant': fields.get('variant'),
        'admin_contact': fields.get('admin_contact'),
        'documents': {
            'dce': 'DCE' in docs,
            'cps': 'CPS' in docs,
            'rc': 'RC' in docs,
            'bpu_dqe': bool({'BPU', 'DQE'} & set(docs)),
            'plans': 'PLANS' in docs,
            'annexes': 'ANNEXES' in docs,
            'types': list(docs),
        },
        'official_url': url,
        'detail_enriched': True,
    }


def field_name(label):
    """Map a PMMP visible label to a field key.

    Exact match first, then longest prefix match so
    ``Estimation (en Dhs TTC)`` resolves to ``estimated_amount``.
    Short aliases like ``ref`` are exact-only so values such as ``REF-1 …``
    are never treated as labels.
    """
    value = folded(label)
    if not value:
        return None
    for key, labels in LABELS.items():
        if value in labels:
            return key
    best_key, best_len = None, -1
    for key, labels in LABELS.items():
        for candidate in labels:
            if len(candidate) < 8:
                continue
            if value.startswith(candidate + ' ') or value.startswith(candidate + '('):
                if len(candidate) > best_len:
                    best_key, best_len = key, len(candidate)
    return best_key


def labelled_fields(page, procurement=True):
    """Read visible labelled facts; never invent a missing buyer or deadline."""
    fields = {}
    parts = [part.strip() for part in page.texts if part.strip()]
    for index, part in enumerate(parts):
        label, sep, value = part.partition(':')
        key = field_name(label if sep else part)
        if key:
            label_text = label if sep else part
            if not value.strip() and index + 1 < len(parts) and not field_name(parts[index + 1]):
                value = parts[index + 1]
            if value.strip():
                if key in {'estimated_amount', 'provisional_bond', 'competition_prize', 'plan_price'}:
                    value = _amount_context_hints(label_text, value)
                fields[key] = value.strip()[:2000 if key == 'title' else
                                            2000 if key == 'eligibility_conditions' else
                                            1000 if key in {'estimated_amount', 'provisional_bond', 'competition_prize'} else 255]
    for key in ('deadline', 'publication_date'):
        if key in fields:
            match = re.search(r'\b(?:\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})\b', fields[key])
            if match:
                fields[key] = match.group()
            else:
                fields.pop(key)
    if 'status' in fields:
        fields['status'] = {'ouverte': 'open', 'ouvert': 'open', 'en cours': 'open',
            'annule': 'cancelled', 'annulee': 'cancelled', 'cloture': 'closed',
            'attribue': 'awarded'}.get(folded(fields['status']), 'unknown')
    if 'procedure_type' in fields:
        value = folded(fields['procedure_type'])
        fields['procedure_type'] = ('purchase_order' if 'bon de commande' in value else
                                    'competition' if 'concours' in value else
                                    'architectural_consultation' if 'architectur' in value else
                                    'moe' if 'maitrise d oeuvre' in value else
                                    'amo' if 'assistance a maitrise d ouvrage' in value else
                                    'tender' if 'offre' in value else 'consultation' if 'consultation' in value else 'unknown')
    return fields


def enrich_detail(candidate, pages):
    """Fetch even incomplete detail discoveries, then fill fields before verification."""
    from app.modules.radar1_markets.parser import parse_date
    from app.core.validation import today_in_morocco
    url, page = pages.get(candidate.official_url or candidate.url or candidate.metadata['discovery_url'])
    if not detail_url(url):
        raise ValueError('not_detail_page')
    fields = labelled_fields(page)
    fields.update(procurement_metadata(page, url))
    if candidate.reference and fields.get('reference') and folded(candidate.reference) != folded(fields['reference']):
        raise ValueError('detail_reference_mismatch')
    for key in ('publication_date', 'deadline'):
        if key in fields:
            fields[key] = parse_date(fields[key])
    deadline_times = re.findall(
        r'(?:date(?: et heure)? limite(?: de remise des plis)?|[ée]ch[ée]ance|date d[’\']ouverture des plis)'
        r'[^:]{0,30}:?\s*\d{2}[/-]\d{2}[/-]\d{4}(?:\s+[àa])?\s+([012]\d:[0-5]\d)',
        page.text, re.I)
    if deadline_times:
        fields['deadline_time'] = deadline_times[-1]
    official_source = 'PMMP' if is_pmmp(url) else 'OFFICIAL_INSTITUTION'
    if fields.get('publication_date'):
        fields.update(publication_date_source=official_source, publication_date_verified=True)
    if fields.get('deadline'):
        fields.update(deadline_source=official_source, deadline_verified=True)
    if 'location' in fields:
        fields['location_evidence'] = fields.pop('location')
    deadline = fields.get('deadline', candidate.deadline)
    if 'status' not in fields and candidate.source_status in {None, 'unknown'} and deadline and deadline >= today_in_morocco():
        fields['status'] = 'open'
    if 'status' in fields:
        fields['source_status'] = fields.pop('status')
    if fields.get('location_evidence') and (is_direct_notice(url) or 'maroc' in folded(page.text)):
        fields['morocco_related'] = True
    if candidate.morocco_related is False:
        fields['morocco_related'] = False
    pmmp = build_pmmp_detail({**fields, 'institution': fields.get('institution') or candidate.institution,
                              'title': fields.get('title') or candidate.title,
                              'reference': fields.get('reference') or candidate.reference}, url, page.text)
    fields.update(url=url, official_url=url, official_confirmation=True,
                  official_url_status='VERIFIED_DIRECT' if is_direct_notice(url) else 'VERIFIED_INSTITUTIONAL',
                  source_quality='OFFICIAL_PRIMARY' if is_direct_notice(url) else 'OFFICIAL_SECONDARY',
                  current_evidence=bool(deadline and deadline >= today_in_morocco()),
                  metadata={**candidate.metadata, 'pmmp': pmmp, 'detail_enrichment_status': 'enriched'})
    # Drop keys that are not MarketCandidate fields (kept inside metadata.pmmp).
    for key in ('announcement_type', 'main_category', 'allotment', 'sme_reserved', 'activity_domains',
                'withdrawal_mode', 'deposit_mode', 'opening_place', 'plan_price', 'qualifications',
                'plan_price_amount', 'plan_price_currency', 'detail_enrichment_status',
                'documents_notice', 'meeting', 'site_visit', 'variant', 'admin_contact'):
        fields.pop(key, None)
    return candidate.model_copy(update=fields)


def dce_metadata(page, url):
    text = folded(page.text)
    available = bool(re.search(r'\b(dce|cps|rc|bpu|dqe|annexes|plans)\b|dossier de consultation|reglement (?:du |de )?concours', text))
    links = [(urljoin(url, href), label) for href, label in page.links
             if re.search(r'\.(zip|pdf)(?:\?|$)', href, re.I) and
             re.search(r'\b(dce|cps|rc|bpu|dqe|plans|annexes)\b|dossier|reglement.*concours', folded(label + ' ' + href))]
    form = available and (page.has_form or any(term in text for term in ('identification', 'renseigner', 'formulaire')))
    size = re.search(r'\b\d+(?:[.,]\d+)?\s*(?:Mo|Ko|MB|KB)\b', page.text, re.I)
    return dict(dce_available=available or bool(links), dce_size=size.group() if size else None,
                dce_access_mode='FORM_REQUIRED' if form else 'DIRECT_DOWNLOAD' if links else
                    'ATTACHMENT_AVAILABLE' if available else 'NOT_FOUND',
                dce_url=links[0][0] if links and not form and urlsplit(links[0][0]).scheme in {'http', 'https'} else None)


def verify_detail(candidate, pages):
    url, page = pages.get(candidate.official_url or candidate.url)
    text = folded(page.text)
    identity = candidate.reference or candidate.title
    # Require independent page evidence for identity, buyer, and active deadline.
    dates = (candidate.deadline.isoformat(), candidate.deadline.strftime('%d/%m/%Y'),
             candidate.deadline.strftime('%d-%m-%Y')) if candidate.deadline else ()
    # An institutional listing may contain a matching row. Multiple independent
    # references or a generic listing heading are not evidence of a detail page.
    row_refs = {match.group() for row in page.rows for match in
                re.finditer(r'\b[A-Z0-9-]*\d+[A-Z0-9-]*(?:/[A-Z0-9-]+){1,4}\b', row, re.I)
                if not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', match.group())}
    generic_heading = any(folded(heading) in {'appels d offres', 'marches publics', 'consultations',
                                              'avis d appels d offres'} for heading in page.headings)
    if not is_direct_notice(url) and (len(row_refs) > 1 or generic_heading):
        raise ValueError('Institutional container is not an individual offer')
    if (not detail_url(url) or not identity or folded(identity) not in text or
            aggregate_title(' '.join(page.headings)) or
            folded(candidate.title) not in text or
            not candidate.institution or folded(candidate.institution) not in text or
            not any(folded(value) in text for value in dates)):
        raise ValueError('Detail identity/buyer/deadline not verified')
    if re.search(r'\b(annule|attribue|cloture)\b', text):
        raise ValueError('Closed procurement notice')
    return candidate.model_copy(update={**dce_metadata(page, url), 'url': url, 'official_url': url,
        'detail_verified': True, 'resolution_confidence': 1.0,
        'metadata': {**candidate.metadata, 'detail_verified': True, 'official_url': url}})
