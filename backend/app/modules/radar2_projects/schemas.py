from datetime import date
from typing import Literal
from pydantic import Field
from app.core.agent_schemas import BaseCandidate, BaseAnalysis


class ProjectCandidate(BaseCandidate):
    project_name: str = Field(min_length=1, max_length=2000)
    signal_type: Literal['PROJECT_ANNOUNCED', 'CONVENTION_SIGNED', 'FINANCING_APPROVED',
        'PROGRAM_APPROVED', 'STUDY_LAUNCHED', 'FEASIBILITY_PREPARATION',
        'DESIGN_PREPARATION', 'LAND_OR_SITE_PREPARATION', 'PARTNER_SELECTED',
        'BUDGET_ALLOCATED', 'IMPLEMENTATION_PREPARATION']
    maturity: Literal['A', 'B', 'C', 'D']
    location: str | None = Field(default=None, max_length=500)
    project_scope: str = Field(min_length=1, max_length=2000)
    estimated_budget: str | None = Field(default=None, max_length=255)
    partners: list[str] = Field(default_factory=list, max_length=30)
    announcement_date: date
    source_url: str = Field(max_length=4000)
    official_url: str | None = Field(default=None, max_length=4000)
    relevance_priority: int = Field(ge=1, le=3)
    evidence_summary: str = Field(min_length=1, max_length=2000)
    project_completed: bool = False
    new_phase_confirmed: bool = False
    published_tender: bool = False
    financing_secured: bool = False
    program_approved: bool = False
    officially_announced: bool = False
    signal_evidence: str | None = Field(default=None, max_length=2000)
    vague_statement: bool = False
    future_opportunity_uncertain: bool = False


class ProjectAnalysis(BaseAnalysis):
    maturity: Literal['A', 'B', 'C', 'D'] = 'C'
    future_opportunity_type: list[Literal['architecture', 'amo', 'study', 'territorial_strategy', 'restoration',
                                         'urban_planning', 'project_management', 'diagnostics', 'other']] = Field(default_factory=list)
    monitor_now_reason: str = Field(default='Evidence requires review.', max_length=2000)
