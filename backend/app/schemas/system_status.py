from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RepositorySubsystemStatus(BaseModel):
    """A compact, non-blocking state for one optional repository subsystem."""

    status: str
    indexed_sha: str | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    current_step: str | None = None
    error: str | None = None
    limited: bool = False
    job_id: UUID | None = None
    last_synced_at: datetime | None = None
    ollama_available: bool | None = None
    detail: str | None = None


class RepositorySystemStatus(BaseModel):
    repository: str
    active_job_id: UUID | None = None
    git: RepositorySubsystemStatus
    code: RepositorySubsystemStatus
    history: RepositorySubsystemStatus
    github: RepositorySubsystemStatus
    graph: RepositorySubsystemStatus
    ai: RepositorySubsystemStatus
    archaeology: RepositorySubsystemStatus
    architecture_history: RepositorySubsystemStatus
