from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SerializeAsAny, field_validator


class RunStatus(StrEnum):
    INITIALIZED = 'initialized'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'


class Stage(StrEnum):
    INITIALIZING = 'INITIALIZING'
    COLLECTING = 'COLLECTING'
    NORMALIZING = 'NORMALIZING'
    DEDUPLICATING = 'DEDUPLICATING'
    ANALYZING = 'ANALYZING'
    VALIDATING = 'VALIDATING'
    SAVING = 'SAVING'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class ResultState(StrEnum):
    NEW = 'new'
    UPDATED = 'updated'
    UNCHANGED = 'unchanged'
    REJECTED = 'rejected'
    ARCHIVED = 'archived'
    MANUAL_REVIEW = 'manual_review'


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, revalidate_instances='always')
    title: str = Field(min_length=1, max_length=2000)
    url: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=255)
    institution: str | None = Field(default=None, max_length=255)
    publication_date: date | None = None
    deadline: date | None = None
    source_status: str | None = Field(default=None, max_length=100)
    raw_text: str = Field(default='', max_length=20000)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    morocco_related: bool | None = None
    source_quality: str = 'UNKNOWN'
    current_evidence: bool = False
    source_conflict: bool = False
    reference_conflict: bool = False

    def radar_fields(self):
        return self.model_dump(mode='json', exclude=set(Candidate.model_fields))

    @field_validator('url')
    @classmethod
    def validate_url(cls, value):
        if not value:
            return None
        from app.core.dedup import canonical_url
        return canonical_url(value)

    @field_validator('metadata')
    @classmethod
    def bounded_metadata(cls, value):
        import json
        from app.core.constants import MAX_CANDIDATE_METADATA_CHARS
        # ensure_ascii=False: French PMMP text must not be inflated by \\uXXXX escapes.
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(encoded) > MAX_CANDIDATE_METADATA_CHARS:
            raise ValueError(f'Metadata exceeds {MAX_CANDIDATE_METADATA_CHARS} characters')
        return value

    @field_validator('official_url', 'official_source', 'linkedin_url', check_fields=False)
    @classmethod
    def validate_evidence_url(cls, value):
        if value is None:
            return None
        if len(value) > 4000:
            raise ValueError('Evidence URL exceeds 4000 characters')
        from app.core.dedup import canonical_url
        return canonical_url(value)


class RadarContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    code: str
    name: str
    description: str
    relevance_rules: list[str]
    exclusion_rules: list[str]
    priority_rules: list[str]
    expected_categories: list[str]


class AgentAnalysis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    relevant: bool
    priority: int = Field(ge=1, le=5, description='1 is highest priority; 5 is lowest.')
    score: int = Field(ge=0, le=100)
    category: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    needs_manual_review: bool
    review_reason: str | None = Field(default=None, max_length=2000)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    available: bool = True


class AnalysisResponse(BaseModel):
    analysis: SerializeAsAny[AgentAnalysis]
    usage: TokenUsage
    model: str
    attempts: int = 1


class RunSummary(BaseModel):
    id: int
    radar_code: str
    agent_name: str | None = None
    status: RunStatus
    current_stage: Stage
    candidates_count: int = 0
    duplicate_count: int = 0
    analyzed_count: int = 0
    new_results_count: int = 0
    updated_results_count: int = 0
    rejected_count: int = 0
    manual_review_count: int = 0
    accepted_count: int = 0
    queries_executed: int = 0
    candidates_after_rules: int = 0
    run_metadata: dict = Field(default_factory=dict)
    candidate_errors_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    ai_calls: int = 0
    direct_fetches: int = 0
    search_calls: int = 0
    resolution_search_calls: int = 0
    estimated_ai_cost: Decimal | None = None
    error_kind: str | None = None
    error_message: str | None = None


# Stable Phase 2 imports plus explicit shared contracts for specialized schemas.
BaseCandidate = Candidate
BaseAnalysis = AgentAnalysis
