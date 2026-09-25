from app.core.radar_agent_base import BaseRadarAgent
from .constants import RULES, SOURCES, CONDITIONS
from .prompts import PROMPT
from .schemas import ProjectCandidate, ProjectAnalysis
from . import validators
from app.core.validation import today_in_morocco


class ProjectsRadarAgent(BaseRadarAgent):
    code, number, emoji = 'RADAR_2_PROJECTS', 2, '🏗️'
    name = 'Projets en gestation'
    description = 'Projets en préparation et opportunités à venir.'
    rules, source_strategy, prompt = RULES, SOURCES, PROMPT
    conditions = CONDITIONS
    candidate_schema, analysis_schema = ProjectCandidate, ProjectAnalysis
    rules_version = '5-business-alignment'
    workflow_enabled = True
    analysis_limit_setting = 'RADAR2_AI_MAX_CALLS'

    def normalize_candidate(self, item):
        # Upgrade the former Radar 2 scaffold payload at its boundary; the stored schema stays explicit.
        if isinstance(item, dict):
            item = dict(item)
            legacy = item.get('signal_type')
            signal = ({'study': 'STUDY_LAUNCHED', 'convention': 'CONVENTION_SIGNED',
                       'partner': 'PARTNER_SELECTED', 'budget': 'BUDGET_ALLOCATED'}.get(legacy, legacy)
                      or ('FINANCING_APPROVED' if item.get('financing_secured') else
                          'PROGRAM_APPROVED' if item.get('program_approved') else
                          'PROJECT_ANNOUNCED' if item.get('officially_announced') else 'PROJECT_ANNOUNCED'))
            maturity = ('A' if signal in {'FINANCING_APPROVED', 'PROGRAM_APPROVED', 'BUDGET_ALLOCATED'} else
                        'B' if signal in {'PROJECT_ANNOUNCED', 'CONVENTION_SIGNED', 'PARTNER_SELECTED'} else 'C')
            title, url = item.get('title', ''), item.get('url') or 'https://example.invalid/project'
            item.update(project_name=item.get('project_name') or title, signal_type=signal,
                maturity=item.get('maturity') or maturity, project_scope=item.get('project_scope') or title,
                announcement_date=item.get('announcement_date') or item.get('publication_date') or today_in_morocco(),
                source_url=item.get('source_url') or url, relevance_priority=item.get('relevance_priority') or 2,
                evidence_summary=item.get('evidence_summary') or item.get('signal_evidence') or title,
                signal_evidence=item.get('signal_evidence') or title, url=url,
                publication_date=item.get('publication_date') or today_in_morocco(),
                morocco_related=True if item.get('morocco_related') is None else item.get('morocco_related'),
                current_evidence=True if item.get('current_evidence') is None else item.get('current_evidence'))
        return super().normalize_candidate(item)

    def validate_specific(self, candidate, *, as_of=None):
        return validators.validate(candidate, as_of)

    def classify_result(self, candidate, analysis, *, as_of=None):
        return validators.classify(candidate, super().classify_result(candidate, analysis), as_of)

    def candidate_review_analysis(self, candidate, reasons):
        return ProjectAnalysis(relevant=True, priority=candidate.relevance_priority, score=85,
            category='project_preparation', summary=candidate.evidence_summary,
            reason='Concrete pre-procurement signal supported by the cited source.', confidence=0.9,
            needs_manual_review=True, review_reason='; '.join(reasons) if reasons else None,
            maturity=candidate.maturity, monitor_now_reason='Potential architecture or territorial mission is forming.')
