from app.core.radar_agent_base import BaseRadarAgent
from .constants import RULES, SOURCES, CONDITIONS
from .prompts import PROMPT
from .schemas import MarketCandidate, MarketAnalysis
from . import validators


class MarketsRadarAgent(BaseRadarAgent):
    rules_version = '10'
    workflow_enabled = True
    analysis_limit_setting = 'RADAR1_MAX_AI_ANALYSES'
    code, number, emoji = 'RADAR_1_MARKETS', 1, '🔎'
    name = 'Marchés'
    description = 'Marchés et commande publique au Maroc.'
    rules, source_strategy, prompt = RULES, SOURCES, PROMPT
    conditions = CONDITIONS
    candidate_schema, analysis_schema = MarketCandidate, MarketAnalysis

    def validate_specific(self, candidate, *, as_of=None):
        return validators.validate(candidate, as_of)

    def classify_result(self, candidate, analysis, *, as_of=None):
        return validators.classify(candidate, super().classify_result(candidate, analysis), as_of)

    def validate_candidate(self, candidate, *, as_of=None):
        from dataclasses import replace
        decision = super().validate_candidate(candidate, as_of=as_of)
        return replace(decision, reasons=tuple(dict.fromkeys(validators.review_code(r) for r in decision.reasons)))

    def review_analysis(self, reasons):
        return super().review_analysis(tuple(validators.review_code(reason) for reason in reasons))

    def candidate_review_analysis(self, candidate, reasons):
        return self.classify_result(candidate, self.review_analysis(reasons))

    def validated_analysis(self, candidate, analysis, *, as_of=None, confidence_rules=None):
        result = super().validated_analysis(candidate, analysis, as_of=as_of, confidence_rules=confidence_rules)
        rules = confidence_rules or self.conditions.confidence_rules
        decision = self.validate_candidate(candidate, as_of=as_of)
        business = validators.business_relevance(candidate)
        if decision.accepted and (not result.relevant or business['decision'] == 'review'):
            reasons = list(decision.reasons) + ['BUSINESS_FIT_REQUIRES_HUMAN_REVIEW']
            result = self.classify_result(candidate, result).model_copy(update={
                'relevant': True, 'needs_manual_review': True, 'review_reason': '; '.join(reasons)})
            return result
        if (result.relevant and rules.manual_review <= result.confidence < rules.auto_accept
                and not decision.needs_manual_review and validators.strong_official_evidence(candidate, as_of)
                and not analysis.needs_manual_review):
            result = result.model_copy(update={'needs_manual_review': False, 'review_reason': None})
        elif result.needs_manual_review:
            result = result.model_copy(update={'review_reason': '; '.join(dict.fromkeys(
                validators.review_code(part.strip()) for part in (result.review_reason or 'AI_REVIEW_REQUESTED').split(';')))})
        return result
