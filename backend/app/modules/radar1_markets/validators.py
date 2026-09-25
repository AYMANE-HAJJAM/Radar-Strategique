from app.core.validation import ValidationDecision, today_in_morocco
from app.core.dedup import normalize_text
from app.modules.radar1_markets.policy import evaluate_relevance


def business_relevance(candidate):
    from flask import current_app, has_app_context
    groups = current_app.config.get("RADAR1_KEYWORD_GROUPS") if has_app_context() else None
    threshold = current_app.config.get('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000) if has_app_context() else 20_000_000
    context = ' '.join(filter(None, (candidate.raw_text, candidate.institution,
                                     candidate.location_evidence)))
    return evaluate_relevance(candidate.title, groups, scope=context,
        estimated_amount=candidate.estimated_amount,
        amount_verified=candidate.estimated_amount_verified,
        procedure_type=candidate.procedure_type, threshold_mad=threshold)


def review_code(reason):
    return {'morocco_scope_unverified': 'GEOGRAPHY_AMBIGUOUS', 'geography_ambiguous': 'GEOGRAPHY_AMBIGUOUS',
            'deadline_unknown': 'DEADLINE_UNCLEAR', 'official_confirmation_missing': 'OFFICIAL_URL_NOT_CONFIRMED',
            'missing:url': 'OFFICIAL_URL_NOT_CONFIRMED', 'status_unclear': 'STATUS_UNCLEAR',
            'official_or_reliable_source_missing': 'SECONDARY_SOURCE_ONLY',
            'review:reference_conflict': 'REFERENCE_CONFLICT', 'review:source_conflict': 'OFFICIAL_SOURCE_CONFLICT',
            'ai_confidence_requires_review': 'MEDIUM_AI_CONFIDENCE', 'medium_ai_confidence': 'MEDIUM_AI_CONFIDENCE',
            'procedure_unclear': 'PROCEDURE_UNCLEAR'}.get(reason, reason.upper().replace(':', '_'))


def strong_official_evidence(candidate, as_of=None):
    from app.integrations.pmmp.client import is_direct_notice
    return (candidate.morocco_related is True and bool(candidate.location_evidence) and
            candidate.official_confirmation and is_direct_notice(candidate.official_url or '') and
            candidate.source_status == 'open' and bool(candidate.reference) and
            candidate.deadline is not None and candidate.deadline > (as_of or today_in_morocco()) and
            candidate.procedure_type not in (None, 'unknown') and
            business_relevance(candidate)['decision'] == 'keep' and
            not candidate.source_conflict and not candidate.reference_conflict)


def validate(candidate, as_of=None):
    as_of = as_of or today_in_morocco()
    from flask import current_app, has_app_context
    from app.modules.radar1_markets.policy import relevant, aggregate_title, detail_url, source_role, DEFAULT_WHITELIST
    config = current_app.config if has_app_context() else {'RADAR1_SOURCE_WHITELIST': DEFAULT_WHITELIST}
    if aggregate_title(candidate.title) or business_relevance(candidate)['decision'] == 'reject':
        return ValidationDecision(False, reasons=('not_relevant_individual_procurement',), allow_ai=False)
    if candidate.publication_date and candidate.publication_date > as_of:
        return ValidationDecision(False, reasons=('future_publication',), allow_ai=False)
    if candidate.publication_date and (as_of - candidate.publication_date).days > 30 and not (candidate.deadline and candidate.deadline >= as_of):
        return ValidationDecision(False, reasons=('old_without_active_deadline',), allow_ai=False)
    from app.modules.radar1_markets.resolution import CREDIBLE, credible_fallback
    if candidate.resolution_state == CREDIBLE and candidate.resolution_attempted:
        if credible_fallback(candidate, config, as_of):
            return ValidationDecision(needs_manual_review=True,
                reasons=('official_url_not_confirmed',) + (('deadline_unknown',) if candidate.deadline is None else ()), allow_ai=False)
        return ValidationDecision(False, reasons=('unresolved_identity_or_stale_evidence',), allow_ai=False)
    if (
            not candidate.detail_verified or not candidate.official_confirmation or not detail_url(candidate.official_url) or
            source_role(candidate.official_url or '', config) not in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'} or
            candidate.morocco_related is False):
        return ValidationDecision(False, reasons=('unverified_procurement_detail',), allow_ai=False)
    if candidate.official_url and (not detail_url(candidate.official_url) or source_role(candidate.official_url, config) not in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}):
        return ValidationDecision(False, reasons=('not_a_detail_url',), allow_ai=False)
    if candidate.morocco_related is False:
        return ValidationDecision(False, reasons=('outside_morocco',))
    if (candidate.deadline and candidate.deadline < as_of) or (candidate.source_status or '').casefold() in {'expired', 'closed'}:
        return ValidationDecision(False, reasons=('expired_opportunity',))
    if candidate.deadline_at:
        from datetime import datetime, timezone
        if candidate.deadline_at < datetime.now(timezone.utc):
            return ValidationDecision(False, reasons=('expired_deadline_time',), allow_ai=False)
    missing = tuple(reason for condition, reason in (
        (business_relevance(candidate)['decision'] == 'review', 'business_fit_requires_human_review'),
        (candidate.morocco_related is None, 'morocco_scope_unverified'),
        (candidate.deadline is None, 'deadline_unknown'),
        (not candidate.official_confirmation or not candidate.official_url, 'official_confirmation_missing'),
        (candidate.source_status != 'open', 'status_unclear'),
        (candidate.procedure_type in (None, 'unknown'), 'procedure_unclear'),
    ) if condition)
    return ValidationDecision(needs_manual_review=bool(missing), reasons=missing,
                              allow_ai=business_relevance(candidate)['decision'] == 'keep' and
                              candidate.official_confirmation and bool(candidate.official_url) and candidate.source_status == 'open')


def classify(candidate, analysis, as_of=None):
    status = 'unknown' if candidate.deadline is None else ('expired' if candidate.deadline < (as_of or today_in_morocco()) else 'active')
    priority = business_relevance(candidate)['priority']
    return analysis.model_copy(update={'deadline_status': status, 'priority': priority,
                                       'commercial_fit': 'direct' if priority == 1 else 'potential' if priority == 2 else 'potential',
                                       'source_quality': candidate.source_quality,
                                       'procedure_type': candidate.procedure_type})
