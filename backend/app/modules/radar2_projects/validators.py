from app.core.validation import ValidationDecision


def validate(candidate, as_of=None):
    from app.core.business_relevance import evaluate_business_relevance
    business = evaluate_business_relevance(candidate.title, candidate.project_scope,
        candidate.evidence_summary, candidate.signal_evidence, candidate.location)
    if business['decision'] == 'reject':
        return ValidationDecision(False, reasons=(business['reason'],), allow_ai=False)
    if candidate.published_tender:
        return ValidationDecision(False, reasons=('already_published_tender',))
    if candidate.project_completed and not candidate.new_phase_confirmed:
        return ValidationDecision(False, reasons=('completed_without_new_phase',))
    if candidate.maturity == 'D' or candidate.vague_statement:
        return ValidationDecision(False, reasons=('weak_or_vague_signal',), allow_ai=False)
    if not candidate.signal_evidence:
        return ValidationDecision(needs_manual_review=True, reasons=('signal_evidence_missing',), allow_ai=True)
    ambiguous = (candidate.maturity == 'C' and candidate.source_quality == 'RELIABLE_SECONDARY') or business['decision'] == 'review'
    return ValidationDecision(needs_manual_review=ambiguous,
        reasons=('ambiguous_secondary_signal',) if ambiguous else (), allow_ai=ambiguous)


def classify(candidate, analysis, as_of=None):
    return analysis.model_copy(update={'maturity': candidate.maturity})
