from datetime import date
from typing import Literal
from pydantic import Field
from app.core.agent_schemas import BaseCandidate, BaseAnalysis


class InstitutionCandidate(BaseCandidate):
    person_name: str | None = None
    role_title: str | None = None
    evidence_date: date | None = None
    role_source_url: str | None = None
    role_source_type: str | None = None
    current_status: Literal['VERIFIED_CURRENT','PROBABLY_CURRENT','UNVERIFIED','OBSOLETE'] = 'UNVERIFIED'
    role_evidence: list[dict] = Field(default_factory=list)
    result_type: Literal['INSTITUTION_PROFILE', 'CURRENT_DECISION_MAKER', 'NEW_APPOINTMENT',
        'ROLE_CHANGE', 'NEW_PROGRAM', 'NEW_PARTNERSHIP', 'NEW_STRATEGIC_ACTIVITY'] = 'INSTITUTION_PROFILE'
    leadership_limitation: str | None = None
    verification_confidence: float | None = Field(default=None, ge=0, le=1)
    profile_type: Literal['INSTITUTION', 'PERSON'] = 'INSTITUTION'
    institution_name: str = Field(min_length=1, max_length=500)
    institution_type: str | None = Field(default=None, max_length=255)
    city_region: str | None = Field(default=None, max_length=255)
    mission: str | None = Field(default=None, max_length=2000)
    architecture_heritage_relevance: str = Field(min_length=1, max_length=2000)
    current_programs: list[str] = Field(default_factory=list, max_length=30)
    recent_projects: list[str] = Field(default_factory=list, max_length=30)
    decision_makers: list[str] = Field(default_factory=list, max_length=30)
    official_site: str | None = Field(default=None, max_length=4000)
    recent_activity_date: date | None = None
    activity_type: Literal['NEW_APPOINTMENT', 'LEADERSHIP_CHANGE', 'NEW_RESPONSIBILITY',
        'NEW_INSTITUTION', 'PROGRAM_LAUNCH', 'RESTRUCTURING', 'PARTNERSHIP',
        'INVESTMENT_FOCUS', 'CURRENT_PROFILE'] = 'CURRENT_PROFILE'
    person: str | None = Field(default=None, max_length=255)
    position: str | None = Field(default=None, max_length=255)
    role_type: Literal['STRATEGIC_DECISION_MAKER', 'OPERATIONAL_MANAGER', 'PROJECT_DIRECTOR',
        'TECHNICAL_MANAGER', 'HERITAGE_MANAGER', 'URBANISM_MANAGER', 'PROCUREMENT_MANAGER',
        'PARTNERSHIP_MANAGER', 'PROGRAM_MANAGER'] | None = None
    responsibility_scope: str | None = Field(default=None, max_length=2000)
    professional_source: str | None = Field(default=None, max_length=4000)
    verification_date: date | None = None
    public_professional_only: bool = True
    territory: str | None = Field(default=None, max_length=255)
    recent_activity: str | None = Field(default=None, max_length=2000)
    project_signals: list[str] = Field(default_factory=list, max_length=20)
    official_source: str | None = None
    linkedin_url: str | None = None
    role_verified: bool = False
    role_verified_at: date | None = None
    institution_relevant: bool = False
    obsolete_holder: bool = False
    nomination_unconfirmed: bool = False


class InstitutionAnalysis(BaseAnalysis):
    decision_role: Literal['strategic', 'technical', 'project_preparation', 'procurement', 'partnership_funding', 'unknown'] = 'unknown'
    current_position_verified: bool = False
    commercial_relevance: str = Field(default='Relevant institutional activity.', max_length=2000)
    meaningful_change: bool = False
