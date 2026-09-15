from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


@dataclass(slots=True)
class GitHubResponse:
    data: Any
    etag: str | None
    not_modified: bool = False


@dataclass(slots=True)
class GitHubPage:
    items: list[dict[str, Any]]
    limited: bool


@dataclass(frozen=True, slots=True)
class ParsedIssueReference:
    owner: str | None
    repository: str | None
    number: int
    reference_type: Literal["fixes", "closes", "resolves", "mentions"]
    raw_reference: str
    confidence: float


@dataclass(frozen=True, slots=True)
class HistoricalEvidence:
    type: Literal[
        "commit", "pull_request", "issue", "issue_comment", "pr_comment", "review_comment"
    ]
    source_id: str
    source_url: str | None
    title: str | None
    body: str | None
    author: str | None
    created_at: datetime
    relationship: str
    confidence: float
