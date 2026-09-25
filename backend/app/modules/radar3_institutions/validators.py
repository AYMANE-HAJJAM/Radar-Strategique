from app.core.validation import ValidationDecision, review_unless, today_in_morocco
from .constants import MAX_ROLE_VERIFICATION_AGE_DAYS


def verified(candidate, as_of=None):
    as_of = as_of or today_in_morocco()
    return bool(candidate.role_verified and candidate.official_source and candidate.role_verified_at
                and (candidate.person or candidate.person_name) and (candidate.position or candidate.role_title)
                and 0 <= (as_of - candidate.role_verified_at).days <= MAX_ROLE_VERIFICATION_AGE_DAYS)


def validate(candidate, as_of=None):
    from app.core.business_relevance import evaluate_business_relevance
    business = evaluate_business_relevance(candidate.title, candidate.mission,
        candidate.architecture_heritage_relevance, candidate.recent_activity,
        ' '.join(candidate.current_programs + candidate.recent_projects))
    if business['decision'] == 'reject':
        return ValidationDecision(False, reasons=(business['reason'],), allow_ai=False)
    from app.modules.radar3_institutions.policy import rejection_reason
    reason = rejection_reason(candidate.title, candidate.recent_activity)
    if reason:
        return ValidationDecision(False, reasons=(reason,), allow_ai=False)
    if not candidate.public_professional_only:
        return ValidationDecision(False, reasons=('private_personal_data',), allow_ai=False)
    if not candidate.institution_relevant:
        return ValidationDecision(False, reasons=('institution_not_business_relevant',), allow_ai=False)
    if candidate.obsolete_holder:
        return ValidationDecision(False, reasons=('obsolete_role_holder',), allow_ai=False)
    if candidate.person_name and candidate.current_status=='OBSOLETE':
        return ValidationDecision(False, reasons=('obsolete_role_holder',), allow_ai=False)
    if candidate.person_name and candidate.current_status in {'VERIFIED_CURRENT','PROBABLY_CURRENT'}:
        if candidate.current_status == 'VERIFIED_CURRENT' and not verified(candidate, as_of):
            return ValidationDecision(False, reasons=('current_role_evidence_missing_or_stale',), allow_ai=False)
        return ValidationDecision(needs_manual_review=candidate.current_status!='VERIFIED_CURRENT',allow_ai=False,
            reasons=('current_role_not_confirmed',) if candidate.current_status!='VERIFIED_CURRENT' else ())
    if candidate.person:
        if verified(candidate, as_of):
            return ValidationDecision(allow_ai=False)
        return ValidationDecision(False, reasons=('unverified_or_obsolete_named_profile',), allow_ai=False)
    if candidate.official_source and candidate.mission and candidate.metadata.get('official_profile_evidence'):
        return ValidationDecision(allow_ai=False)
    if candidate.official_source and candidate.recent_activity and candidate.recent_activity_date:
        return ValidationDecision(allow_ai=False)
    return ValidationDecision(needs_manual_review=True, reasons=('institutional_relevance_requires_review',), allow_ai=True)


def classify(candidate, analysis, as_of=None):
    return analysis.model_copy(update={'current_position_verified': verified(candidate, as_of)})
