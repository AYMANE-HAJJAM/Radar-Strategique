from typing import Literal
from pydantic import Field, AwareDatetime
from app.core.agent_schemas import BaseCandidate, BaseAnalysis


class MarketCandidate(BaseCandidate):
    business_category: Literal['P1_HERITAGE', 'P1_MAJOR_ARCH', 'P1_CONCOURS', 'P2_REVIEW', 'REJECT'] | None = None
    resolution_state: Literal['VERIFIED_OFFICIAL', 'UNVERIFIED_BUT_CREDIBLE', 'UNRESOLVED'] = 'UNRESOLVED'
    resolution_attempted: bool = False
    resolution_error: str | None = None
    source_type: Literal['OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL', 'PROCUREMENT_AGGREGATOR', 'DISCOVERY_ONLY'] = 'DISCOVERY_ONLY'
    detail_verified: bool = False
    dce_available: bool = False
    dce_access_mode: Literal['DIRECT_DOWNLOAD', 'FORM_REQUIRED', 'ATTACHMENT_AVAILABLE', 'NOT_FOUND'] = 'NOT_FOUND'
    dce_size: str | None = None
    dce_url: str | None = None
    resolution_confidence: float = 0.0
    morocco_related: bool | None = None
    procedure_type: str | None = Field(default=None, max_length=100)
    budget: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, max_length=10)
    estimated_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estimated_currency: str | None = Field(default=None, max_length=10)
    estimated_amount_tax_mode: Literal['TTC', 'HT', 'UNKNOWN'] | None = None
    estimated_amount_source: str | None = Field(default=None, max_length=50)
    estimated_amount_verified: bool = False
    estimated_lots: list[dict] = Field(default_factory=list, max_length=50)
    provisional_bond_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provisional_bond_currency: str | None = Field(default=None, max_length=10)
    publication_date_source: str | None = Field(default=None, max_length=50)
    publication_date_verified: bool = False
    deadline_source: str | None = Field(default=None, max_length=50)
    deadline_verified: bool = False
    deadline_time: str | None = Field(default=None, pattern=r'^\d{2}:\d{2}$')
    document_types: list[str] = Field(default_factory=list, max_length=20)
    competition_prize_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    competition_prize_currency: str | None = Field(default=None, max_length=10)
    eligibility_conditions: str | None = Field(default=None, max_length=2000)
    competition_regulation_available: bool = False
    official_url: str | None = None
    official_url_status: Literal['VERIFIED_DIRECT', 'VERIFIED_INSTITUTIONAL', 'INDIRECT_PMMP', 'SECONDARY_ONLY', 'NOT_FOUND'] = 'NOT_FOUND'
    official_date_evidence: str | None = Field(default=None, max_length=500)
    location_evidence: str | None = Field(default=None, max_length=500)
    deadline_at: AwareDatetime | None = None
    access_mode: Literal['DIRECT_OFFICIAL', 'INDIRECT_PMMP_SEARCH', 'OFFICIAL_INSTITUTION', 'SECONDARY_DISCOVERY'] = 'SECONDARY_DISCOVERY'
    official_confirmation: bool = False

    def radar_fields(self):
        data = {**super().radar_fields(), 'morocco_related': self.morocco_related,
                'current_evidence': self.current_evidence}
        # Persist structured PMMP + decision explainability into Result.radar_metadata.
        for key in ('pmmp', 'business_relevance', 'detail_enrichment_status', 'preliminary_relevance'):
            if key in self.metadata and self.metadata[key] is not None:
                data[key] = self.metadata[key]
        return data


class MarketAnalysis(BaseAnalysis):
    priority: int = Field(ge=1, le=3)
    deadline_status: Literal['active', 'expired', 'unknown'] = 'unknown'
    commercial_fit: Literal['direct', 'potential', 'monitoring', 'unknown'] = 'unknown'
    procedure_type: str | None = Field(default=None, max_length=100)
    source_quality: Literal['OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY', 'RELIABLE_SECONDARY', 'DISCOVERY_ONLY', 'UNKNOWN'] = 'UNKNOWN'
