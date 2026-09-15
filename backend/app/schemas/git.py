from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.repository import RepositoryRead


class RepositorySubmit(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class SubmissionResponse(BaseModel):
    repository_id: UUID
    job_id: UUID | None
    status: Literal["queued", "running", "ready"]


class RepositoryDetail(RepositoryRead):
    head_sha: str | None
    commit_count: int
    last_refreshed_at: datetime | None
    history_rewritten: bool
    history_index_status: str
    history_indexed_through_sha: str | None
    history_limited: bool
    history_stale: bool
    history_indexed_commit_count: int
    history_total_commit_count: int
    active_job_id: UUID | None = None


class CommitSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sha: str
    short_sha: str
    message: str
    author_name: str
    authored_at: datetime
    committed_at: datetime
    is_merge_commit: bool
    insertions: int
    deletions: int
    files_changed: int


class FileChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    old_path: str | None
    new_path: str | None
    change_type: str
    additions: int | None
    deletions: int | None
    similarity_score: int | None


class CommitDetail(CommitSummary):
    parents: list[str]
    changes: list[FileChangeRead]


class CommitPage(BaseModel):
    items: list[CommitSummary]
    page: int
    page_size: int
    total: int


class DiffResponse(BaseModel):
    content: str
    truncated: bool


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    target_sha: str
    annotated: bool


class RepositoryStats(BaseModel):
    total_commits: int
    merge_commits: int
    contributors: int
    historical_paths: int
    insertions: int
    deletions: int
    first_commit_at: datetime | None
    latest_commit_at: datetime | None
