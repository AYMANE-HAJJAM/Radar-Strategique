from datetime import date
from typing import Literal
from pydantic import Field
from app.core.agent_schemas import BaseCandidate, BaseAnalysis

AccessMode = Literal['DIRECT_ACCESS', 'CONSULTANT_OPPORTUNITY', 'BENEFICIARY_PROCUREMENT',
                     'PROJECT_PIPELINE', 'TECHNICAL_ASSISTANCE', 'GRANT', 'MONITORING_ONLY']


class FundingCandidate(BaseCandidate):
    morocco_related: bool | None = None
    funder: str | None = Field(default=None, max_length=255)
    program: str | None = Field(default=None, max_length=500)
    program_name: str = Field(min_length=1, max_length=500)
    country_scope: str = Field(min_length=1, max_length=255)
    morocco_relevance: str = Field(min_length=1, max_length=2000)
    opportunity_type: AccessMode
    funding_status: Literal['A','B','C','D','E']
    beneficiary: str | None = Field(default=None, max_length=255)
    amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, max_length=10)
    reported_funding_status: Literal['open', 'active', 'preparation', 'pipeline', 'closed']
    territory: str | None = Field(default=None, max_length=255)
    sector: str | None = Field(default=None, max_length=255)
    eligibility: str | None = Field(default=None, max_length=2000)
    direct_eligibility_confirmed: bool = False
    access_mode_evidence: AccessMode
    potential_procurement: str | None = Field(default=None, max_length=2000)
    official_source: str | None = None
    general_donor_page: bool = False
    strategically_relevant: bool = False
    approval_date: date | None = None
    closing_date: date | None = None
    official_url: str = Field(max_length=4000)
    procurement_url: str | None = Field(default=None, max_length=4000)
    summary: str = Field(min_length=1,max_length=2000)
    business_relevance: str = Field(min_length=1,max_length=2000)


class FundingAnalysis(BaseAnalysis):
    funding_status: Literal['A', 'B', 'C', 'D', 'E'] = 'D'
    beneficiary_type: Literal['public', 'private', 'nonprofit', 'mixed', 'unknown'] = 'unknown'
    access_mode: AccessMode = 'MONITORING_ONLY'
