"""Deterministic, cost-free interpretation of professional targeted-search briefs."""
import calendar
import re
import unicodedata
from datetime import date, timedelta

MONTHS = {'janvier':1,'fevrier':2,'mars':3,'avril':4,'mai':5,'juin':6,'juillet':7,
          'aout':8,'septembre':9,'octobre':10,'novembre':11,'decembre':12}
MODE_TERMS = {
    'PROCUREMENT': ('marche','appel d offres','consultation','cps','dce','bpu','dqe','reglement de concours','صفقة','طلب عروض'),
    'PROJECTS': ('projet en gestation','projets en gestation','projet en preparation','projets en preparation','chantier','etude','annonce de projet','مشروع','دراسة'),
    'INSTITUTIONS': ('qui dirige','institution','responsable','directeur','nomination'),
    'POLICIES': ('loi','decret','reglementation','strategie publique','politique publique','texte'),
    'FUNDING': ('bailleur','financement','finance','subvention','don','pret','fonds','تمويل','منحة'),
    'ARTICLES': ('article','presse','actualite','annonce'),
}
EXPANSIONS = {
    'muraille': ('remparts','fortifications','enceintes','bastions','portes historiques','murs historiques','restauration','conservation','confortement','rehabilitation patrimoniale'),
    'valorisation patrimoniale': ('mise en valeur','sauvegarde','conservation','heritage valorisation','patrimoine culturel','patrimoine historique','circuit patrimonial'),
    'patrimoine': ('heritage','patrimoine culturel','patrimoine historique','sauvegarde','conservation'),
    'etude territoriale': ('ingenierie territoriale','diagnostic territorial','strategie territoriale','planification territoriale'),
}
DOCUMENTS = ('CPS','RC','DCE','BPU','DQE','PLANS','ANNEXES')
PLACE_ALIASES = {
    'El Jadida': ('el jadida', 'mazagan', 'cite portugaise', 'medina d el jadida'),
    'Fès': ('fes', 'medina de fes', 'fes el bali', 'fes bali', 'fes jdid'),
    'Safi': ('safi', 'ksar el bahr', 'chateau de mer'),
    'Marrakech': ('marrakech', 'medina de marrakech'),
    'Tiznit': ('tiznit', 'medina de tiznit'),
    'Dakhla': ('dakhla',), 'Rabat': ('rabat',), 'Casablanca': ('casablanca',),
    'Essaouira': ('essaouira', 'mogador', 'medina d essaouira'),
    'Meknès': ('meknes', 'medina de meknes'), 'Tanger': ('tanger', 'tangier'),
    'Ouarzazate': ('ouarzazate',), 'Taroudant': ('taroudant', 'medina de taroudant'),
    'Agadir': ('agadir',), 'Tétouan': ('tetouan',), 'Chefchaouen': ('chefchaouen',),
    'Béni Mellal': ('beni mellal',), 'Laâyoune': ('laayoune',), 'Nador': ('nador',),
    'Oujda': ('oujda',), 'Kénitra': ('kenitra',), 'Salé': ('sale',),
    'Maroc': ('maroc', 'morocco'),
}


def fold(value):
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.sub(r'[^a-z0-9\u0600-\u06ff]+',' ',''.join(c for c in value if not unicodedata.combining(c))).split())


def _dates(text, today):
    value = fold(text); start = end = None; mode = 'DEFAULT'
    years = re.search(r'\b(20\d{2})(?:\s+a\s+|\s+au\s+|\s+)(20\d{2})\b', value)
    between = re.search(r'\bentre\s+(\d{1,2})(?:er)?\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\s+et\s+(\d{1,2})(?:er)?\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\b',value)
    exact = re.search(r'\b(depuis|avant)?\s*(?:le\s+)?(\d{1,2})(?:er)?\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\b', value)
    month = re.search(r'\b(depuis|avant)?\s*('+'|'.join(MONTHS)+r')\s+(20\d{2})\b', value)
    if between:
        start=date(int(between[3]),MONTHS[between[2]],int(between[1]));end=date(int(between[6]),MONTHS[between[5]],int(between[4]));mode='EXPLICIT'
    elif years:
        start=date(int(years[1]),1,1); end=date(int(years[2]),12,31); mode='ARCHIVE'
    elif exact:
        point=date(int(exact[4]),MONTHS[exact[3]],int(exact[2])); start=point
        if exact[1]=='avant': start=None; end=point
        elif exact[1]!='depuis':end=point
        mode='EXPLICIT'
    elif month:
        year,number=int(month[3]),MONTHS[month[2]]
        if month[1]=='avant': end=date(year,number,calendar.monthrange(year,number)[1])
        elif month[1]=='depuis': start=date(year,number,1)
        else:
            start=date(year,number,1); end=date(year,number,calendar.monthrange(year,number)[1])
        mode='EXPLICIT'
    elif 'aujourd hui' in value:
        start=end=today; mode='CURRENT'
    elif 'cette semaine' in value:
        start=today-timedelta(days=today.weekday()); end=today; mode='CURRENT'
    elif 'recent' in value:
        start=today-timedelta(days=90); mode='RECENT'
    if 'archive' in value: mode='ARCHIVE'
    return start,end,mode


def contains_phrase(text, phrase):
    return f' {fold(phrase)} ' in f' {text} '


def _geography(prompt, normalized):
    for place, aliases in PLACE_ALIASES.items():
        if any(contains_phrase(normalized, alias) for alias in aliases):
            return place, list(dict.fromkeys((place, *aliases)))
    match = re.search(r'(?:\bà|\bau|\baux|\bdans|\bsur)\s+([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ’\' -]{1,60})', prompt)
    if match:
        literal = re.split(r'[,.;]|\b(?:depuis|avant|entre|avec|sans|pour)\b',
                           match.group(1), maxsplit=1, flags=re.I)[0].strip(' -')
        if literal:
            return literal, [literal]
    return None, []


def interpret_brief(prompt, user_id, today=None):
    if not isinstance(prompt,str) or not 3 <= len(prompt.strip()) <= 4000:
        raise ValueError('Le brief doit contenir entre 3 et 4000 caractères.')
    today=today or date.today(); normalized=fold(prompt)
    modes=[mode for mode,terms in MODE_TERMS.items() if any(term in normalized for term in terms)]
    mode=modes[0] if len(modes)==1 else 'MIXED' if modes else 'ARTICLES'
    geography, geography_aliases = _geography(prompt, normalized)
    documents=[doc for doc in DOCUMENTS if re.search(r'\b'+re.escape(fold(doc))+r'\b',normalized)]
    topics=[]
    for key in EXPANSIONS:
        if key in normalized or (key=='muraille' and 'rempart' in normalized): topics.append(key)
    related=[]
    for topic in topics: related.extend(EXPANSIONS[topic])
    start,end,recency=_dates(prompt,today)
    negative=[]
    exclusion=re.search(r'\b(?:exclus|exclure|sans)\s+(.+)',normalized)
    if exclusion: negative.append(exclusion[1][:200])
    title=' — '.join(filter(None,(geography, (topics[0].title() if topics else next(iter(modes), 'Recherche ciblée').title()))))
    ambiguities=[]
    if ('patrimoine' in normalized or 'heritage' in normalized) and not modes:
        ambiguities.append('Type de recherche à préciser : marchés, projets ou les deux.')
    return {'search_title':title[:255] or 'Recherche ciblée','original_prompt':prompt.strip(),
        'interpreted_intent':prompt.strip(),'search_mode':mode,'pipeline_modes':modes or ['ARTICLES'],
        'topics':topics or [prompt.strip()[:120]],'related_concepts':list(dict.fromkeys(related)),
        'geography':[geography] if geography else [],'geography_aliases':geography_aliases,
        'date_from':start.isoformat() if start else None,
        'date_to':end.isoformat() if end else None,'recency_mode':recency,
        'opportunity_types':modes,'content_types':['ARTICLES'] if mode in {'ARTICLES','PROJECTS','MIXED'} else [],
        'source_preferences':['OFFICIAL','INSTITUTIONAL','CREDIBLE_MEDIA'],
        'document_requirements':documents,'status_requirements':['OPEN','CURRENT'] if mode=='PROCUREMENT' and recency!='ARCHIVE' else [],
        'positive_signals':list(dict.fromkeys(topics+related)),'negative_signals':negative,
        'business_context':'ARCHERITAGE_INNOVA_PRIOR','result_priority':'BRIEF_FIT',
        'language_hints':['fr','ar'],'ambiguities':ambiguities,'created_by_user_id':user_id}


def refine_brief(previous, refinement, user_id, today=None):
    delta=interpret_brief(refinement,user_id,today)
    normalized=fold(refinement)
    explicit_concepts=[concept for values in EXPANSIONS.values() for concept in values
                       if fold(concept) in normalized]
    delta['positive_signals']=list(dict.fromkeys(delta['positive_signals']+explicit_concepts))
    merged=dict(previous); merged['interpreted_intent']=previous['interpreted_intent']+'\nAffinement: '+refinement.strip()
    for key in ('related_concepts','positive_signals','negative_signals','document_requirements'):
        merged[key]=list(dict.fromkeys((previous.get(key) or [])+(delta.get(key) or [])))
    for key in ('geography','geography_aliases','date_from','date_to','recency_mode','search_mode','pipeline_modes','status_requirements'):
        value=delta.get(key)
        if value and value not in ([], 'DEFAULT', 'ARTICLES'): merged[key]=value
    merged['created_by_user_id']=user_id
    merged['ambiguities']=delta.get('ambiguities',[])
    return merged
