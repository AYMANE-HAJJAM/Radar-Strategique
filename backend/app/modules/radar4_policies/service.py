from app.core.radar_agent_base import BaseRadarAgent
from .constants import RULES, SOURCES, CONDITIONS
from .prompts import PROMPT
from .schemas import PolicyCandidate, PolicyAnalysis
from . import validators


class PoliciesRadarAgent(BaseRadarAgent):
    code, number, emoji = 'RADAR_4_POLICIES', 4, '📜'
    name = 'Politiques publiques'
    description = 'Politiques publiques et programmes nationaux.'
    rules, source_strategy, prompt = RULES, SOURCES, PROMPT
    conditions = CONDITIONS
    candidate_schema, analysis_schema = PolicyCandidate, PolicyAnalysis
    rules_version = '6-business-alignment'
    workflow_enabled = True
    analysis_limit_setting = 'RADAR4_AI_MAX_CALLS'

    def normalize_candidate(self, item):
        if isinstance(item, dict):
            item = dict(item)
            types = {'law':'LAW','draft_law':'DRAFT_LAW','decree':'DECREE','order':'ORDER','circular':'CIRCULAR',
                'standard':'OFFICIAL_GUIDELINE','strategy':'STRATEGY','program':'PROGRAM','reform':'REGULATORY_REFORM',
                'study':'POLICY_STUDY','planning_document':'PUBLIC_STUDY','announcement':'OFFICIAL_GUIDELINE','other':'OFFICIAL_GUIDELINE'}
            statuses = {'adopted':'ADOPTED','in_force':'IN_FORCE','implementation':'IMPLEMENTATION',
                'preparation':'UNDER_PREPARATION','signal':'POLICY_SIGNAL','unknown':'POLICY_SIGNAL'}
            dtype = types.get(item.get('document_type'), item.get('document_type') or 'OFFICIAL_GUIDELINE')
            status = statuses.get(item.get('reported_status'), item.get('legal_status') or item.get('reported_status') or 'POLICY_SIGNAL')
            item.update(document_type=dtype, legal_status=status, reported_status=status,
                scope=item.get('scope') or item.get('title'), official_url=item.get('official_url') or item.get('official_source') or item.get('url') or 'https://example.invalid/policy',
                summary=item.get('summary') or item.get('status_evidence') or item.get('title'),
                business_implications=item.get('business_implications') or item.get('title'))
        return super().normalize_candidate(item)

    def validate_specific(self, candidate, *, as_of=None):
        return validators.validate(candidate, as_of)

    def classify_result(self, candidate, analysis, *, as_of=None):
        return validators.classify(candidate, super().classify_result(candidate, analysis), as_of)

    def candidate_review_analysis(self, candidate, reasons):
        return PolicyAnalysis(relevant=True, priority=1 if candidate.legal_status in {'ADOPTED','IN_FORCE'} else 2,
            score=85, category='law' if candidate.document_type == 'LAW' else 'draft_law' if candidate.document_type == 'DRAFT_LAW' else 'other',
            summary=candidate.summary, reason=candidate.business_implications, confidence=.92,
            needs_manual_review=True, review_reason='; '.join(reasons) if reasons else None,
            legal_status=candidate.legal_status, what_changed=candidate.status_evidence)
