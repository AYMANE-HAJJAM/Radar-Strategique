from app.core.radar_agent_base import BaseRadarAgent
from .constants import RULES, SOURCES, CONDITIONS
from .prompts import PROMPT
from .schemas import InstitutionCandidate, InstitutionAnalysis
from . import validators


class InstitutionsRadarAgent(BaseRadarAgent):
    code, number, emoji = 'RADAR_3_INSTITUTIONS', 3, '🏛️'
    name = 'Décideurs & Institutions'
    description = 'Décideurs et institutions liés aux opportunités.'
    rules, source_strategy, prompt = RULES, SOURCES, PROMPT
    conditions = CONDITIONS
    candidate_schema, analysis_schema = InstitutionCandidate, InstitutionAnalysis
    rules_version = '6-business-alignment'
    workflow_enabled = True
    analysis_limit_setting = 'RADAR3_AI_MAX_CALLS'

    def normalize_candidate(self, item):
        if isinstance(item, dict):
            item = dict(item)
            institution = item.get('institution_name') or item.get('institution') or item.get('title')
            item.update(institution_name=institution,
                architecture_heritage_relevance=item.get('architecture_heritage_relevance') or item.get('recent_activity') or item.get('title'),
                official_site=item.get('official_site') or item.get('official_source') or item.get('url'),
                verification_date=item.get('verification_date') or item.get('role_verified_at'))
        return super().normalize_candidate(item)

    def validate_specific(self, candidate, *, as_of=None):
        return validators.validate(candidate, as_of)

    def classify_result(self, candidate, analysis, *, as_of=None):
        return validators.classify(candidate, super().classify_result(candidate, analysis), as_of)

    def candidate_review_analysis(self, candidate, reasons):
        return InstitutionAnalysis(relevant=True, priority=1 if candidate.role_verified else 2, score=85,
            category='appointment' if candidate.activity_type in {'NEW_APPOINTMENT', 'LEADERSHIP_CHANGE'} else 'institutional_activity',
            summary=candidate.recent_activity or candidate.architecture_heritage_relevance,
            reason='Public professional institutional evidence.', confidence=.9, needs_manual_review=True,
            review_reason='; '.join(reasons) if reasons else None,
            current_position_verified=validators.verified(candidate), meaningful_change=candidate.activity_type != 'CURRENT_PROFILE')
