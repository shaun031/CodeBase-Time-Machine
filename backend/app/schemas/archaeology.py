from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ArchaeologyStatus(BaseModel):
    status: str
    progress: float | None
    step: str | None
    files_processed: int
    symbols_processed: int
    rewrites_detected: int
    copy_candidates: int
    contributors: int
    last_indexed_sha: str | None
    stale: bool
    error: str | None
    job_id: UUID | None
    completed_at: datetime | None


class ArchaeologyTarget(BaseModel):
    entity_type: Literal["file", "symbol"]
    entity_id: UUID
    current_file_id: UUID | None = None
    name: str
    path: str | None
    kind: str | None
    status: str
    introduced_at: datetime | None
    last_modified_at: datetime | None
    age_days: int
    days_since_last_change: int
    change_count: int
    churn: int
    contributor_count: int
    rename_count: int
    move_count: int
    rewrite_count: int
    changes_last_30_days: int
    changes_last_90_days: int
    changes_last_180_days: int
    volatility: float
    stability: float
    classification: str
    metadata: dict[str, Any]


class ArchaeologyOverview(BaseModel):
    repository_age_days: int | None
    total_historical_files: int
    current_files: int
    deleted_files: int
    current_symbols: int
    deleted_symbols: int
    renamed_symbols: int
    moved_symbols: int
    major_rewrites: int
    contributors: int
    median_symbol_age_days: float | None
    median_file_age_days: float | None
    most_changed_files: list[ArchaeologyTarget]
    oldest_current_symbols: list[ArchaeologyTarget]
    recently_rewritten_symbols: list[ArchaeologyTarget]
    age_buckets: dict[str, int]
    volatility_formula: str
    stability_formula: str
    canonical_date: str
    merge_commit_policy: str
    knowledge_concentration: dict[str, Any]


class VolatilityResponse(BaseModel):
    level: Literal["file", "symbol"]
    items: list[ArchaeologyTarget]
    volatility_formula: str
    stability_formula: str


class ContributorRead(BaseModel):
    identity_key: str
    display_name: str
    commit_count: int
    files_touched: int = 0
    symbols_touched: int = 0
    lines_changed: int = 0
    first_activity: datetime
    last_activity: datetime
    knowledge_score: float | None = None
    contribution_share: float | None = None
    introduced: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class ContributorResponse(BaseModel):
    items: list[ContributorRead]
    concentration: dict[str, Any]
    interpretation: str


class TargetRequest(BaseModel):
    file_id: UUID | None = None
    symbol_id: UUID | None = None
    lineage_id: UUID | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "TargetRequest":
        if sum(value is not None for value in (self.file_id, self.symbol_id, self.lineage_id)) != 1:
            raise ValueError("Exactly one target is required")
        return self


class ProvenanceResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    origin: dict[str, Any]
    current_identity: dict[str, Any]
    status: str
    timeline: list[dict[str, Any]]
    renames: list[dict[str, Any]]
    moves: list[dict[str, Any]]
    rewrites: list[dict[str, Any]]
    contributors: list[ContributorRead]


class HistoricalSearchItem(BaseModel):
    entity_type: str
    entity_id: UUID | None
    name: str
    historical_name: str | None
    kind: str | None
    file_path: str | None
    commit_sha: str | None
    commit_id: UUID | None
    status: str
    lineage_id: UUID | None
    version_id: UUID | None
    matched_reason: str
    match_type: Literal["exact", "lexical", "semantic"]
    source_available: bool = False


class HistoricalSearchResponse(BaseModel):
    items: list[HistoricalSearchItem]
    page: int
    page_size: int
    total: int


class RewriteRead(BaseModel):
    id: UUID
    lineage_id: UUID
    symbol: str
    file_path: str
    commit_id: UUID
    commit_sha: str
    committed_at: datetime
    similarity: float
    lines_added: int
    lines_deleted: int
    reason: str
    evidence: dict[str, Any]
    old_version_id: UUID
    new_version_id: UUID


class RelatedCodeRead(BaseModel):
    candidate_lineage_id: UUID
    candidate_name: str
    candidate_path: str
    commit_sha: str
    similarity: float
    relationship: str
    confidence: float
    evidence: dict[str, Any]
    status: str


class DossierResponse(BaseModel):
    target: ArchaeologyTarget
    provenance: ProvenanceResponse
    activity: dict[str, Any]
    contributors: ContributorResponse
    development_context: dict[str, Any]
    dependencies: dict[str, Any]
    related_code: list[RelatedCodeRead]
    limitations: list[str]


class DossierExplainResponse(BaseModel):
    summary: str
    citations: list[dict[str, str]]
    ai_enriched: bool
    limitation: str | None = None
