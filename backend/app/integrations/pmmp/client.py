from urllib.parse import urlsplit, parse_qs, urlencode, urlunsplit


def is_pmmp(url):
    host = (urlsplit(url).hostname or '').lower()
    return host == 'marchespublics.gov.ma' or host.endswith('.marchespublics.gov.ma')


def is_direct_notice(url):
    if not is_pmmp(url):
        return False
    path = urlsplit(url).path.rstrip('/').lower()
    if '/bdc/entreprise/consultation/show/' in path:
        return path.rsplit('/', 1)[-1].isdigit()
    query = parse_qs(urlsplit(url).query)
    return (any(page in {'entreprise.EntrepriseDetailConsultation', 'entreprise.EntrepriseDetailsConsultation'}
                for page in query.get('page', []))
            and any(value.isdigit() for value in query.get('refConsultation', [])))


def canonical_detail_url(url):
    """Canonical identity for an already verified PMMP detail (not evidence)."""
    if not is_direct_notice(url):
        return url
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    values = {'page': 'entreprise.EntrepriseDetailsConsultation',
              'refConsultation': query['refConsultation'][0]}
    if query.get('orgAcronyme'):
        values['orgAcronyme'] = query['orgAcronyme'][0]
    return urlunsplit(('https', 'www.marchespublics.gov.ma', '/index.php', urlencode(values), ''))


def detail_from_official_identity(url):
    """Resolve an observed official notice/document's consultation identity.

    This is only a GET target, never evidence of validity: callers must fetch and
    verify the actual detail page against the original reference before saving.
    No document download or form action is performed.
    """
    if not is_pmmp(url):
        return None
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    reference = next((value for value in query.get('refConsultation', []) if value.isdigit()), None)
    organization = next(iter(query.get('orgAcronyme', [])), None)
    if not reference or not organization or not organization.isalnum():
        return None
    if not any(page in {'entreprise.EntrepriseDownloadAvisJAL', 'entreprise.EntrepriseDetailConsultation',
                        'entreprise.EntrepriseDetailsConsultation'} for page in query.get('page', [])):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
        urlencode({'page': 'entreprise.EntrepriseDetailsConsultation', 'refConsultation': reference,
                   'orgAcronyme': organization}), ''))
