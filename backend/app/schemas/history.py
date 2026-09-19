from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HistoryCommit(BaseModel):
    sha: str
    short_sha: str
    message: str
    author_name: str
    authored_at: datetime
    committed_at: datetime
    is_merge_commit: bool


class HistoryStatus(BaseModel):
    status: str
    progress: float | None
    current_step: str | None
    indexed_commits: int
    total_commits: int
    lineages: int
    versions: int
    events: int
    history_limited: bool
    history_stale: bool
    last_indexed_sha: str | None
    job_id: UUID | None = None


class SymbolVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    lineage_id: UUID
    file_path: str
    language: str | None
    name: str
    qualified_name: str
    kind: str
    signature: str | None
    start_line: int
    end_line: int
    start_column: int
    end_column: int
    documentation: str | None
    match_type: str
    match_confidence: float
    matching_metadata: dict[str, Any] | None
    source_truncated: bool
    commit: HistoryCommit


class SymbolVersionPage(BaseModel):
    items: list[SymbolVersionRead]
    page: int
    page_size: int
    total: int


class SymbolEventRead(BaseModel):
    id: UUID
    lineage_id: UUID
    event_type: str
    previous_version_id: UUID | None
    new_version_id: UUID | None
    summary_data: dict[str, Any] | None
    commit: HistoryCommit
    symbol_name: str
    symbol_kind: str
    file_path: str | None
    deterministic_label: str


class HistoryEventPage(BaseModel):
    items: list[SymbolEventRead]
    page: int
    page_size: int
    total: int


class SymbolLineageRead(BaseModel):
    id: UUID
    current_name: str | None
    current_qualified_name: str | None
    current_file_path: str | None
    symbol_kind: str
    is_deleted: bool
    introduced_commit: HistoryCommit | None
    last_seen_commit: HistoryCommit | None
    deleted_commit: HistoryCommit | None
    latest_version: SymbolVersionRead | None
    versions: list[SymbolVersionRead]
    events: list[SymbolEventRead]
    previous_names: list[str]
    file_paths: list[str]


class LineageSearchItem(BaseModel):
    lineage_id: UUID
    current_name: str | None
    current_qualified_name: str | None
    current_file_path: str | None
    symbol_kind: str
    is_deleted: bool
    previous_names: list[str]


class LineageSearchPage(BaseModel):
    items: list[LineageSearchItem]
    page: int
    page_size: int
    total: int


class HistoricalSymbolSource(BaseModel):
    version_id: UUID
    commit_sha: str
    file_path: str
    start_line: int
    end_line: int
    language: str | None
    source: str
    retrieved_from_git: bool


class SymbolVersionCompare(BaseModel):
    from_version: UUID
    to_version: UUID
    old_source: str
    new_source: str
    old_name: str
    new_name: str
    old_path: str
    new_path: str
    old_signature: str | None
    new_signature: str | None
    old_lines: tuple[int, int]
    new_lines: tuple[int, int]
    diff: str
    truncated: bool


class SymbolAtCommit(BaseModel):
    commit_sha: str
    exists_at_commit: bool
    version: SymbolVersionRead | None
    last_known_version: SymbolVersionRead | None


class FileVersionRead(BaseModel):
    id: UUID
    path: str
    blob_sha: str | None
    language: str | None
    size_bytes: int
    line_count: int
    change_type: str
    commit: HistoryCommit | None


class FileHistoryRead(BaseModel):
    lineage_id: UUID
    created: HistoryCommit | None
    current_path: str | None
    is_deleted: bool
    versions: list[FileVersionRead]


class HistoricalFileContent(BaseModel):
    path: str
    commit_sha: str
    content: str
    language: str | None
    total_lines: int
    historical: Literal[True] = True


class BlameLineRead(BaseModel):
    line: int
    commit_sha: str
    author: str
    author_time: datetime
    source: str
    original_line: int | None = None
    original_path: str | None = None


class SymbolBlameSummary(BaseModel):
    introduced_commit: HistoryCommit | None
    last_symbol_change_commit: HistoryCommit | None
    recent_line_authors: list[str]
    lines: list[BlameLineRead]
