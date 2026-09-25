import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def normalize_text(value):
    return ' '.join(unicodedata.normalize('NFKC', value or '').casefold().split())


def normalized_source_title(value):
    value = unicodedata.normalize('NFKD', value or '').casefold()
    return ' '.join(re.sub(r'[^a-z0-9\u0600-\u06ff]+', ' ', ''.join(
        character for character in value if not unicodedata.combining(character))).split())


def source_content_fingerprint(candidate):
    body = normalize_text(getattr(candidate, 'raw_text', None))
    return digest([normalized_source_title(candidate.title), body])


def source_identity_metadata(candidate, radar_code):
    return {'first_seen_radar': radar_code, 'related_radars': [radar_code],
            'source_type': candidate.metadata.get('source_type') or candidate.source_quality,
            'global_title_key': normalized_source_title(candidate.title),
            'global_content_fingerprint': source_content_fingerprint(candidate),
            'radar_extractions': {radar_code: candidate.radar_fields()}}


def fingerprint(*, reference=None, institution=None, title=None, url=None):
    """Version 1: reference + institution, else URL, else title + institution.

    URL paths and queries remain case sensitive. Only fragments are removed.
    This detects exact normalized identities, not fuzzy or cross-source matches.
    """
    ref, org, heading = map(normalize_text, (reference, institution, title))
    if ref and org:
        identity = ['v1', 'reference', ref, org]
    elif url and url.strip():
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ('http', 'https') or not parts.netloc:
            raise ValueError('Expected an absolute HTTP(S) URL.')
        normalized = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))
        identity = ['v1', 'url', normalized]
    elif heading:
        identity = ['v1', 'title', heading, org]
    else:
        raise ValueError('A title, URL, or reference with institution is required.')
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()


def canonical_url(value):
    parts = urlsplit(value.strip())
    scheme = parts.scheme.lower()
    if scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password:
        raise ValueError('Expected an absolute HTTP(S) URL without credentials.')
    hostname = parts.hostname.lower().encode('idna').decode('ascii')
    if ':' in hostname:
        hostname = f'[{hostname}]'
    port = parts.port
    netloc = hostname if port is None or (scheme, port) in {('http', 80), ('https', 443)} else f'{hostname}:{port}'
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if not key.casefold().startswith('utm_') and key.casefold() not in {'fbclid', 'gclid', 'msclkid'}]
    # Preserve HTTP versus HTTPS, path/query case and query ordering: redirects are not assumed.
    return urlunsplit((scheme, netloc, parts.path.rstrip('/') or '/', urlencode(query), ''))


def digest(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def identity_keys(candidate):
    if getattr(candidate, 'program_name', None) and getattr(candidate, 'funder', None):
        key = digest([normalize_text(candidate.program_name), normalize_text(candidate.funder)])
        return (None, key, key)
    if getattr(candidate, 'legal_status', None) and getattr(candidate, 'document_type', None):
        reference = normalize_text(getattr(candidate, 'reference_number', None))
        base = re.sub(r'\b(projet|avant projet|adoption|adopte|entree en vigueur|mise en oeuvre)\b', '', normalize_text(candidate.title))
        key = digest([reference or base, normalize_text(candidate.institution)])
        return (None, key, key)
    if getattr(candidate, 'person', None) and getattr(candidate, 'institution_name', None):
        return (None, digest([normalize_text(candidate.person), normalize_text(candidate.institution_name)]),
                digest([normalize_text(candidate.person), normalize_text(candidate.institution_name)]))
    if getattr(candidate, 'institution_name', None):
        site = getattr(candidate, 'official_site', None) or candidate.url
        domain = urlsplit(site).hostname.lower() if site and urlsplit(site).hostname else ''
        key = digest([domain, normalize_text(candidate.institution_name)])
        return (None, key, key)
    reference = normalize_text(candidate.reference)
    institution = normalize_text(candidate.institution)
    fallback = getattr(candidate, 'resolution_state', None) == 'UNVERIFIED_BUT_CREDIBLE'
    # A supporting listing can describe many tenders. Its URL is not an offer ID.
    if fallback:
        from app.modules.radar1_markets.policy import folded
        reference = folded(candidate.reference)
    return (
        canonical_url(candidate.url) if candidate.url and not fallback else None,
        digest([reference, institution]) if reference and (institution or fallback) else None,
        digest([normalize_text(candidate.title), institution]),
    )


def meaningful_data(candidate):
    return {
        'title': normalize_text(candidate.title), 'institution': normalize_text(candidate.institution),
        'reference': normalize_text(candidate.reference), 'source': normalize_text(candidate.source),
        'publication_date': candidate.publication_date.isoformat() if candidate.publication_date else None,
        'deadline': candidate.deadline.isoformat() if candidate.deadline else None,
        'source_status': normalize_text(candidate.source_status), 'metadata': candidate.metadata,
        'raw_text': normalize_text(candidate.raw_text),
        'radar_fields': candidate.radar_fields(),
        'morocco_related': candidate.morocco_related, 'source_quality': candidate.source_quality,
        'current_evidence': candidate.current_evidence, 'source_conflict': candidate.source_conflict,
        'reference_conflict': candidate.reference_conflict,
    }


def content_hash(candidate):
    return digest(meaningful_data(candidate))


class DedupService:
    def find_global_source(self, radar_id, candidate):
        """Find the same source item in another radar without merging project-level events."""
        from app.db.extensions import db
        from app.db.models import Result
        candidate_url = canonical_url(candidate.url) if candidate.url else None
        title_key = normalized_source_title(candidate.title)
        content_key = source_content_fingerprint(candidate)
        body = normalize_text(getattr(candidate, 'raw_text', None))

        def _evaluate(row, *, same_url):
            metadata = row.radar_metadata or {}
            global_source = metadata.get('global_source') or {}
            row_content = global_source.get('global_content_fingerprint')
            if same_url:
                material = bool(row_content and row_content != content_key and body)
                return row, material
            row_title = global_source.get('global_title_key') or normalized_source_title(row.title)
            same_content = bool(body and row_content == content_key)
            if len(title_key) >= 25 and title_key == row_title and same_content:
                return row, False
            return None

        # Indexed url_key path — common cross-radar case; avoids full-table scan.
        if candidate_url:
            url_digest = digest([candidate_url])
            for row in db.session.scalars(db.select(Result).where(
                    Result.radar_id != radar_id, Result.url_key == url_digest)):
                row_url = canonical_url(row.url) if row.url else None
                if row_url == candidate_url:
                    return _evaluate(row, same_url=True)

        # Title/content mirror + legacy rows without url_key still need a scan.
        if len(title_key) < 25 and not candidate_url:
            return None, False
        for row in db.session.scalars(db.select(Result).where(Result.radar_id != radar_id)):
            if candidate_url:
                row_url = canonical_url(row.url) if row.url else None
                if row_url == candidate_url:
                    # Legacy row missing url_key (or digest mismatch) still matches by URL.
                    if row.url_key != digest([candidate_url]):
                        return _evaluate(row, same_url=True)
                    continue
            hit = _evaluate(row, same_url=False)
            if hit:
                return hit
        return None, False

    def find_existing(self, radar_id, candidate):
        from app.db.extensions import db
        from app.db.models import Result
        from app.core.agent_errors import InvalidCandidateError
        keys = identity_keys(candidate)
        matches = {}
        lookup_keys = (digest([keys[0]]) if keys[0] else None, keys[1], keys[2])
        for column, key in zip((Result.url_key, Result.reference_key, Result.identity_key), lookup_keys):
            if key is not None:
                for row in db.session.scalars(db.select(Result).where(Result.radar_id == radar_id, column == key)):
                    matches[row.id] = row
        # Legacy rows keep their Phase 1 fingerprint. Hydrate keys when rediscovered.
        legacy = db.session.scalars(db.select(Result).where(Result.radar_id == radar_id, Result.identity_key.is_(None)))
        for row in legacy:
            try:
                old_keys = identity_keys(row)
            except ValueError:
                continue
            if any(a is not None and a == b for a, b in zip(keys, old_keys)):
                matches[row.id] = row
        # Radar 1 fallback may acquire a buyer or an official URL later. Keep all
        # existing keys; reconcile a reference-only identity only when consistent.
        if getattr(candidate, 'resolution_state', None) and candidate.reference:
            from app.modules.radar1_markets.policy import folded
            rows = db.session.scalars(db.select(Result).where(
                Result.radar_id == radar_id, Result.reference.is_not(None)))
            for row in rows:
                if not (row.radar_metadata or {}).get('resolution_state'):
                    continue
                if folded(row.reference) != folded(candidate.reference):
                    continue
                same_buyer = bool(row.institution and candidate.institution and
                                  folded(row.institution) == folded(candidate.institution))
                partial_buyer = not row.institution or not candidate.institution
                same_title = folded(row.title) == folded(candidate.title)
                if same_buyer or (partial_buyer and same_title):
                    matches[row.id] = row
        if len(matches) > 1:
            raise InvalidCandidateError('Conflicting deterministic identities require manual reconciliation.')
        return next(iter(matches.values()), None)

    def unchanged(self, existing, candidate):
        return existing.content_hash is not None and existing.content_hash == content_hash(candidate)


def discovery_snapshot(candidate):
    return {key: (getattr(candidate, key).isoformat() if key in {'deadline', 'publication_date'} and getattr(candidate, key)
                  else normalize_text(getattr(candidate, key)))
            for key in ('title', 'reference', 'institution', 'deadline', 'publication_date', 'source_status', 'url')}
