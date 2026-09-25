from app.core.validation import ValidationDecision


def validate(candidate, as_of=None):
    from app.core.business_relevance import evaluate_business_relevance
    business = evaluate_business_relevance(candidate.title, candidate.summary,
        candidate.business_relevance, candidate.sector, candidate.morocco_relevance)
    if business['decision'] == 'reject':
        return ValidationDecision(False, reasons=(business['reason'],), allow_ai=False)
    if candidate.reported_funding_status == 'closed' and not candidate.strategically_relevant:
        return ValidationDecision(False, reasons=('closed_without_strategic_relevance',), allow_ai=False)
    if candidate.morocco_related is False:
        return ValidationDecision(False, reasons=('funding_unrelated_to_morocco',))
    reasons = []
    if business['decision'] == 'review':
        reasons.append('business_relevance_requires_review')
    if candidate.morocco_related is None:
        reasons.append('morocco_scope_unverified')
    if candidate.access_mode_evidence == 'DIRECT_ACCESS' and not (
        candidate.direct_eligibility_confirmed and candidate.eligibility and candidate.official_source
    ):
        reasons.append('direct_eligibility_unverified')
    return ValidationDecision(needs_manual_review=bool(reasons), reasons=tuple(reasons), allow_ai=bool(reasons))


def classify(candidate, analysis, as_of=None):
    
    status = {'open': 'A', 'active': 'B', 'preparation': 'C', 'pipeline': 'D', 'closed': 'E'}.get(candidate.reported_funding_status, 'unknown')
    access = candidate.access_mode_evidence
    if access == 'DIRECT_ACCESS' and not (candidate.direct_eligibility_confirmed and candidate.eligibility and candidate.official_source):
        access = 'MONITORING_ONLY'
    return analysis.model_copy(update={'funding_status': status, 'access_mode': access})
