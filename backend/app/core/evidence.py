"""Build bounded, structured evidence for the rare ambiguous AI decision."""
import json
import re

KEYWORDS = (
    'architecture', 'patrimoine', 'urban', 'réhabilitation', 'rehabilitation',
    'convention', 'financement', 'budget', 'nommé', 'nomination', 'directeur',
    'loi', 'décret', 'decret', 'adopté', 'vigueur', 'consultation', 'eligible',
    'procurement', 'beneficiary', 'morocco', 'maroc',
)


def relevant_snippets(text, *, max_chars=2400, snippet_chars=500, max_items=4):
    """Rank sentence-sized evidence by relevant terms instead of prefix truncation."""
    clean = re.sub(r'\s+', ' ', text or '').strip()
    if not clean:
        return []
    sections = [part.strip() for part in re.split(r'(?<=[.!?;])\s+|\s*[|•]\s*', clean) if part.strip()]
    ranked = sorted(enumerate(sections), key=lambda pair: (
        -sum(term in pair[1].casefold() for term in KEYWORDS), pair[0]))
    chosen, total = [], 0
    for _, section in ranked:
        value = section[:snippet_chars]
        if not value or total + len(value) > max_chars:
            continue
        chosen.append(value); total += len(value)
        if len(chosen) >= max_items:
            break
    return chosen


def compact_candidate(candidate, *, max_chars=2400, snippet_chars=500, max_items=4):
    """Exclude full page text and large metadata while retaining material fields."""
    verbose = {'raw_text', 'metadata', 'architecture_heritage_relevance', 'recent_activity',
               'responsibility_scope', 'scope', 'summary', 'business_implications',
               'business_relevance', 'morocco_relevance', 'potential_procurement',
               'eligibility', 'status_evidence', 'evidence_summary', 'signal_evidence'}
    dumped = candidate.model_dump(mode='json', exclude_none=True)
    fields = {key: (value[:snippet_chars] if isinstance(value, str) else value)
              for key, value in dumped.items() if key not in verbose}
    evidence = [str(dumped.get(key) or '') for key in verbose if key != 'metadata']
    metadata = candidate.metadata or {}
    for key in ('evidence', 'excerpt', 'description', 'content', 'text'):
        value = metadata.get(key)
        if isinstance(value, str):
            evidence.append(value)
    payload = {
        'candidate': fields,
        'signal_keywords': sorted({term for term in KEYWORDS if term in ' '.join(evidence).casefold()}),
        'evidence_snippets': relevant_snippets(' '.join(evidence), max_chars=max_chars,
            snippet_chars=snippet_chars, max_items=max_items),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
