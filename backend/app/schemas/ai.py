from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AIStatus(BaseModel):
    provider: Literal["ollama"]
    available: bool
    base_url_safe: str
    llm_model: str
    llm_model_available: bool
    embedding_model: str
    embedding_model_available: bool
    message: str | None = None


class RepositoryAIStatus(BaseModel):
    status: str
    progress: float | None
    current_step: str | None
    documents: int
    embedded_documents: int
    embedding_model: str | None
    embedding_dimension: int | None
    last_indexed_sha: str | None
    index_stale: bool
    ollama_available: bool
    error: str | None
    job_id: UUID | None
    completed_at: str | None


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    lineage_id: UUID | None = None
    symbol_id: UUID | None = None
    file_path: str | None = Field(default=None, max_length=2000)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    commit_sha: str | None = Field(
        default=None, min_length=7, max_length=40, pattern=r"^[0-9a-fA-F]+$"
    )
    pull_request_number: int | None = Field(default=None, ge=1)
    issue_number: int | None = Field(default=None, ge=1)
    selected_source: str | None = Field(default=None, max_length=12000)
    conversation: list[dict[Literal["role", "content"], str]] = Field(
        default_factory=list, max_length=8
    )
    debug: bool = False

    @model_validator(mode="after")
    def validate_line_range(self) -> "AskRequest":
        if self.start_line and self.end_line and self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if (self.start_line or self.end_line) and not self.file_path:
            raise ValueError("file_path is required with a line range")
        return self


class EvidenceRead(BaseModel):
    id: str
    type: str
    title: str
    text: str
    source_id: str | None = None
    source_url: str | None = None
    commit_sha: str | None = None
    file_path: str | None = None
    symbol_lineage_id: str | None = None
    pr_number: int | None = None
    issue_number: int | None = None
    score: float
    relationship: str
    retrieval_reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundedClaim(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class AskResponse(BaseModel):
    answer: str
    claims: list[GroundedClaim]
    confidence: Literal["high", "medium", "low"]
    evidence_sufficiency: Literal["strong", "moderate", "weak", "insufficient"]
    evidence: list[EvidenceRead]
    limitations: list[str]
    cached: bool = False
    diagnostics: dict[str, Any] | None = None


class GeneratedAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=20000)
    claims: list[GroundedClaim] = Field(default_factory=list, max_length=30)
    confidence: Literal["high", "medium", "low"]
    limitations: list[str] = Field(default_factory=list, max_length=20)


class EvidenceSearchResponse(BaseModel):
    items: list[EvidenceRead]
    query_ms: float
