from dataclasses import dataclass, field
from typing import Protocol, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.core.agent_schemas import TokenUsage


class SearchHit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = ''
    url: str
    kind: Literal['unknown', 'discovery_page', 'tender'] = 'unknown'
    evidence: str = ''
    institution: str | None = None
    reference: str | None = None
    publication_date: str | None = None
    deadline: str | None = None
    deadline_at: str | None = None
    execution_country: str | None = None
    location: str | None = None
    status: str = 'unknown'
    procedure_type: str = 'unknown'
    official_date_evidence: str | None = None
    estimated_amount: str | None = None
    provisional_bond: str | None = None
    official_notice: bool = False
    source_conflict: bool = False


class SearchOutput(BaseModel):
    hits: list[SearchHit] = Field(max_length=20)


class DiscoveryHit(BaseModel):
    """Minimal extraction contract for Radars 2–5."""
    model_config = ConfigDict(extra='forbid')
    title: str = ''
    url: str
    evidence: str = ''
    institution: str | None = None
    publication_date: str | None = None
    location: str | None = None


class DiscoveryOutput(BaseModel):
    hits: list[DiscoveryHit] = Field(max_length=20)


@dataclass
class SearchResponse:
    hits: list[SearchHit]
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(available=False))
    model: str = ''
    web_search_calls: int = 0
    raw_results_count: int | None = None
    diagnostics: dict = field(default_factory=dict)


class SearchProviderError(RuntimeError):
    def __init__(self, kind='provider_error', response=None):
        super().__init__(kind)
        self.kind, self.response = kind, response


class SearchProvider(Protocol):
    def search(self, query: str, recency_days=None, domains=None) -> SearchResponse: ...
