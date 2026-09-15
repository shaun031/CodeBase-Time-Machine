from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.git import CommitSummary
from app.schemas.history import SymbolEventRead


class GitHubStatus(BaseModel):
    status: str
    progress: float | None
    current_step: str | None
    last_synced_at: datetime | None
    pull_requests_indexed: int
    issues_indexed: int
    comments_indexed: int
    review_comments_indexed: int
    rate_limit_remaining: int | None
    rate_limit_reset_at: datetime | None
    sync_error: str | None
    github_index_limited: bool
    job_id: UUID | None = None


class GitHubLabelRead(BaseModel):
    name: str
    description: str | None
    color: str | None


class GitHubCommentRead(BaseModel):
    id: UUID
    comment_type: str
    author_login: str | None
    body: str | None
    created_at: datetime
    updated_at: datetime
    html_url: str
    path: str | None
    commit_sha: str | None
    original_commit_sha: str | None
    line: int | None
    original_line: int | None
    side: str | None
    diff_hunk: str | None


class PullRequestSummary(BaseModel):
    id: UUID
    number: int
    title: str
    state: str
    draft: bool
    merged: bool
    author_login: str | None
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None
    closed_at: datetime | None
    html_url: str
    commits_count: int
    labels: list[GitHubLabelRead]


class PullRequestPage(BaseModel):
    items: list[PullRequestSummary]
    page: int
    page_size: int
    total: int


class IssueSummary(BaseModel):
    id: UUID
    number: int
    title: str
    state: str
    author_login: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    html_url: str
    milestone: str | None
    labels: list[GitHubLabelRead]


class IssuePage(BaseModel):
    items: list[IssueSummary]
    page: int
    page_size: int
    total: int


class AffectedSymbol(BaseModel):
    lineage_id: UUID
    name: str
    symbol_kind: str
    file_path: str | None
    event_type: str
    commit_sha: str


class IssueReferenceRead(BaseModel):
    issue: IssueSummary | None
    owner: str
    repository: str
    number: int
    reference_type: str
    raw_reference: str
    confidence: float
    external: bool


class PullRequestDetail(PullRequestSummary):
    body: str | None
    base_branch: str
    head_branch: str
    merge_commit_sha: str | None
    additions: int
    deletions: int
    changed_files: int
    comments_count: int
    review_comments_count: int
    commits: list[CommitSummary]
    commit_shas: list[str]
    linked_issues: list[IssueReferenceRead]
    comments: list[GitHubCommentRead]
    review_comments: list[GitHubCommentRead]
    affected_symbols: list[AffectedSymbol]


class RelatedPullRequest(BaseModel):
    pull_request: PullRequestSummary
    relationship: str
    confidence: float


class IssueDetail(IssueSummary):
    body: str | None
    comments_count: int
    comments: list[GitHubCommentRead]
    related_pull_requests: list[RelatedPullRequest]
    related_commits: list[CommitSummary]
    affected_symbols: list[AffectedSymbol]


class CommitContext(BaseModel):
    commit: CommitSummary
    associated_pull_requests: list[PullRequestSummary]
    referenced_issues: list[IssueReferenceRead]
    symbol_changes: list[SymbolEventRead]


class SymbolContextEvent(BaseModel):
    event: SymbolEventRead
    commit: CommitSummary
    pull_requests: list[PullRequestSummary]
    issues: list[IssueReferenceRead]
    comments: list[GitHubCommentRead]


class SymbolContext(BaseModel):
    lineage_id: UUID
    events: list[SymbolContextEvent]
