"""Executable, typed business conditions shared by all radar configurations."""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from app.core.validation import ValidationDecision


class SourceQuality(StrEnum):
    OFFICIAL_PRIMARY = 'OFFICIAL_PRIMARY'
    OFFICIAL_SECONDARY = 'OFFICIAL_SECONDARY'
    RELIABLE_SECONDARY = 'RELIABLE_SECONDARY'
    DISCOVERY_ONLY = 'DISCOVERY_ONLY'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class Predicate:
    field: str
    operation: str
    value: object = True

    def matches(self, candidate):
        actual = getattr(candidate, self.field, None)
        if self.operation == 'equals':
            return actual == self.value
        if self.operation == 'present':
            return bool(actual)
        if self.operation == 'in':
            return actual in self.value
        raise ValueError('Unknown condition operation')


@dataclass(frozen=True)
class ConfidenceRules:
    auto_accept: float = 0.80
    manual_review: float = 0.55

    def __post_init__(self):
        if not 0 <= self.manual_review <= self.auto_accept <= 1:
            raise ValueError('Confidence thresholds must satisfy 0 <= review <= accept <= 1.')


@dataclass(frozen=True)
class StrictConditions:
    inclusion_rules: tuple[Predicate, ...]
    exclusion_rules: tuple[Predicate, ...]
    freshness_days: int
    geography_required: bool
    source_rules: tuple[str, ...]
    mandatory_fields: tuple[tuple[str, ...], ...]
    confidence_rules: ConfidenceRules = ConfidenceRules()
    priority_rules: tuple[tuple[str, int], ...] = ()
    manual_review_triggers: tuple[Predicate, ...] = ()
    freshness_field: str = 'publication_date'

    def evaluate(self, candidate, as_of: date):
        for rule in self.exclusion_rules:
            if rule.matches(candidate):
                return ValidationDecision(False, reasons=(f'excluded:{rule.field}',), allow_ai=False)
        if self.geography_required and candidate.morocco_related is False:
            return ValidationDecision(False, reasons=('outside_morocco',), allow_ai=False)
        reasons = []
        if self.inclusion_rules and not any(rule.matches(candidate) for rule in self.inclusion_rules):
            return ValidationDecision(False, reasons=('no_concrete_inclusion_signal',), allow_ai=False)
        for alternatives in self.mandatory_fields:
            if not any(getattr(candidate, field, None) for field in alternatives):
                reasons.append('missing:' + '|'.join(alternatives))
        if self.geography_required and candidate.morocco_related is not True:
            reasons.append('geography_ambiguous')
        if candidate.source_quality not in self.source_rules:
            reasons.append('official_or_reliable_source_missing')
        observed = getattr(candidate, self.freshness_field, None)
        if observed and observed > as_of:
            reasons.append('future_date_conflict')
        if observed and (as_of - observed).days > self.freshness_days and not candidate.current_evidence:
            return ValidationDecision(False, reasons=('old_without_current_evidence',), allow_ai=False)
        for rule in self.manual_review_triggers:
            if rule.matches(candidate):
                reasons.append('review:' + rule.field)
        return ValidationDecision(needs_manual_review=bool(reasons), reasons=tuple(reasons), allow_ai=not reasons)
