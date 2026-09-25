from app.core.radar_agent_base import BaseRadarAgent
from .constants import RULES, SOURCES, CONDITIONS
from .prompts import PROMPT
from .schemas import FundingCandidate, FundingAnalysis
from . import validators


class FundingRadarAgent(BaseRadarAgent):
    code, number, emoji = 'RADAR_5_FUNDING', 5, '💰'
    name = 'Financements'
    description = 'Financements, bailleurs et programmes de soutien.'
    rules, source_strategy, prompt = RULES, SOURCES, PROMPT
    conditions = CONDITIONS
    candidate_schema, analysis_schema = FundingCandidate, FundingAnalysis
    rules_version='5-business-alignment'
    workflow_enabled=True
    analysis_limit_setting='RADAR5_AI_MAX_CALLS'
    def normalize_candidate(self,item):
        if isinstance(item,dict):
            item=dict(item); modes={'direct_application':'DIRECT_ACCESS','consultant':'CONSULTANT_OPPORTUNITY',
                'beneficiary_contractor':'BENEFICIARY_PROCUREMENT','future_procurement':'PROJECT_PIPELINE',
                'monitor_only':'MONITORING_ONLY','unknown':'MONITORING_ONLY'}
            mode=modes.get(item.get('access_mode_evidence'),item.get('opportunity_type') or item.get('access_mode_evidence') or 'MONITORING_ONLY')
            status=item.get('reported_funding_status') or 'pipeline'
            if status=='unknown':status='pipeline'
            letter={'open':'A','active':'B','preparation':'C','pipeline':'D','closed':'E'}[status]
            program=item.get('program_name') or item.get('program') or item.get('title')
            item.update(program=program,program_name=program,country_scope=item.get('country_scope') or 'Morocco',
                morocco_relevance=item.get('morocco_relevance') or item.get('summary') or item.get('title'),opportunity_type=mode,
                access_mode_evidence=mode,funding_status=item.get('funding_status') or letter,reported_funding_status=status,
                official_url=item.get('official_url') or item.get('official_source') or item.get('url') or 'https://example.invalid/funding',
                summary=item.get('summary') or item.get('title'),business_relevance=item.get('business_relevance') or item.get('potential_procurement') or item.get('title'))
        return super().normalize_candidate(item)

    def validate_specific(self, candidate, *, as_of=None):
        return validators.validate(candidate, as_of)

    def classify_result(self, candidate, analysis, *, as_of=None):
        return validators.classify(candidate, super().classify_result(candidate, analysis), as_of)
    def candidate_review_analysis(self,candidate,reasons):
        return FundingAnalysis(relevant=True,priority=1 if candidate.funding_status=='A' else 2,score=85,
            category='grant' if candidate.opportunity_type=='GRANT' else 'technical_assistance' if candidate.opportunity_type=='TECHNICAL_ASSISTANCE' else 'investment',
            summary=candidate.summary,reason=candidate.business_relevance,confidence=.9,needs_manual_review=True,
            review_reason='; '.join(reasons) if reasons else None,funding_status=candidate.funding_status,access_mode=candidate.opportunity_type)
