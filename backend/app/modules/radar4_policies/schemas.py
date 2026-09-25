from datetime import date
from typing import Literal
from pydantic import Field
from app.core.agent_schemas import BaseCandidate, BaseAnalysis

LegalStatus = Literal['ADOPTED', 'PUBLISHED', 'IN_FORCE', 'IMPLEMENTATION', 'DRAFT', 'UNDER_PREPARATION',
                      'PUBLIC_CONSULTATION', 'POLICY_SIGNAL', 'ANNOUNCED']


class PolicyCandidate(BaseCandidate):
    adoption_date: date | None = None
    verification_date: date | None = None
    status_source_url: str | None = None
    status_source_type: str | None = None
    status_confidence: float | None = Field(default=None,ge=0,le=1)
    bo_number: str | None = None
    publication_verified: bool = False
    publication_check: str = 'NOT_CHECKED'
    document_type: Literal['LAW', 'DRAFT_LAW', 'DECREE', 'ORDER', 'CIRCULAR', 'STRATEGY',
        'PROGRAM', 'PUBLIC_STUDY', 'POLICY_STUDY', 'REGULATORY_REFORM',
        'PUBLIC_CONSULTATION', 'OFFICIAL_GUIDELINE']
    legal_status: LegalStatus
    reported_status: LegalStatus
    reference_number: str | None = Field(default=None, max_length=255)
    effective_date: date | None = None
    scope: str = Field(min_length=1, max_length=2000)
    official_url: str = Field(max_length=4000)
    official_document_url: str | None = Field(default=None, max_length=4000)
    summary: str = Field(min_length=1, max_length=2000)
    business_implications: str = Field(min_length=1, max_length=2000)
    reliable_status_evidence: bool = False
    official_source: str | None = None
    status_evidence: str | None = Field(default=None, max_length=2000)
    outdated_without_relevance: bool = False


class PolicyAnalysis(BaseAnalysis):
    policy_status: Literal['A', 'B', 'C', 'D'] = 'D'
    legal_status: LegalStatus = 'POLICY_SIGNAL'
    what_changed: str | None = Field(default=None, max_length=2000)
    affected_parties: list[str] = Field(default_factory=list, max_length=20)
    potential_projects: list[str] = Field(default_factory=list, max_length=20)
