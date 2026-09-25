from app.core.validation import ValidationDecision
from app.core.agent_errors import InvalidCandidateError


def reliable(candidate):
    return bool(candidate.reliable_status_evidence and candidate.official_source and candidate.status_evidence)


def validate(candidate, as_of=None):
    from app.core.business_relevance import evaluate_business_relevance
    business = evaluate_business_relevance(candidate.title, candidate.scope,
        candidate.summary, candidate.business_implications)
    if business['decision'] == 'reject':
        return ValidationDecision(False, reasons=(business['reason'],), allow_ai=False)
    from app.modules.radar4_policies.status_verification import official_bo
    from app.core.validation import today_in_morocco
    status = str(candidate.reported_status).upper()
    document_type = str(candidate.document_type).upper()
    claimed_law = status in {'ADOPTED', 'PUBLISHED', 'IN_FORCE'}
    if status in {'PUBLISHED','IN_FORCE'} and not (candidate.publication_verified and official_bo(candidate.status_source_url or '')):
        return ValidationDecision(False,reasons=('publication_not_verified',),allow_ai=False)
    if status == 'IN_FORCE' and (not candidate.effective_date or candidate.effective_date > (as_of or today_in_morocco())):
        return ValidationDecision(False,reasons=('effective_date_not_verified',),allow_ai=False)
    if claimed_law and document_type in {'DRAFT_LAW', 'PUBLIC_CONSULTATION'}:
        return ValidationDecision(False, reasons=('contradictory_legal_status',))
    if claimed_law and not reliable(candidate):
        return ValidationDecision(False, reasons=('legal_claim_without_reliable_status',))
    review = not reliable(candidate) or status == 'POLICY_SIGNAL' or business['decision'] == 'review'
    return ValidationDecision(needs_manual_review=review, reasons=('policy_status_requires_review',) if review else (),
                              allow_ai=review)


def classify(candidate, analysis, as_of=None):
    reported = str(candidate.reported_status).upper()
    document_type = str(candidate.document_type).upper()
    if analysis.legal_status in {'ADOPTED', 'PUBLISHED', 'IN_FORCE'} and (
        not reliable(candidate) or document_type in {'DRAFT_LAW', 'PUBLIC_CONSULTATION'}
        or reported not in {'ADOPTED', 'PUBLISHED', 'IN_FORCE'}
        or (analysis.legal_status == 'PUBLISHED' and reported not in {'PUBLISHED','IN_FORCE'})
        or (analysis.legal_status == 'IN_FORCE' and reported != 'IN_FORCE')
    ):
        # Reject the whole analysis: a downgraded enum alone would leave a misleading summary intact.
        raise InvalidCandidateError('Unsupported legal status in analysis.')
    # Source evidence caps the legal claim even if AI asserts a stronger status.
    legal = reported if reliable(candidate) else 'POLICY_SIGNAL'
    status = {'ADOPTED': 'A', 'PUBLISHED': 'A', 'IN_FORCE': 'A', 'IMPLEMENTATION': 'B', 'ANNOUNCED':'D',
              'DRAFT': 'C', 'UNDER_PREPARATION': 'C', 'PUBLIC_CONSULTATION': 'C'}.get(legal, 'D')
    return analysis.model_copy(update={'legal_status': legal, 'policy_status': status})
