import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GitHubRepositoryMetadata(Base):
    __tablename__ = "github_repository_metadata"
    __table_args__ = (
        UniqueConstraint("repository_id", name="uq_github_repository_metadata_repository_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    github_repository_id: Mapped[int] = mapped_column(BigInteger, index=True)
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(511))
    description: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    html_url: Mapped[str] = mapped_column(Text)
    homepage: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(100))
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    open_issues_count: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    fork: Mapped[bool] = mapped_column(Boolean, default=False)
    github_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    github_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubUser(Base):
    __tablename__ = "github_users"
    __table_args__ = (UniqueConstraint("github_user_id", name="uq_github_users_github_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    github_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    login: Mapped[str] = mapped_column(String(255), index=True)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    html_url: Mapped[str | None] = mapped_column(Text)
    user_type: Mapped[str] = mapped_column(String(50), default="User")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GitHubPullRequest(Base):
    __tablename__ = "github_pull_requests"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "github_pr_id", name="uq_github_pull_requests_repo_github_id"
        ),
        UniqueConstraint("repository_id", "number", name="uq_github_pull_requests_repo_number"),
        Index("ix_github_pull_requests_repo_state", "repository_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    github_pr_id: Mapped[int] = mapped_column(BigInteger)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), index=True)
    draft: Mapped[bool] = mapped_column(Boolean, default=False)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_users.id", ondelete="SET NULL"), index=True
    )
    author_login: Mapped[str | None] = mapped_column(String(255), index=True)
    merge_commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    base_branch: Mapped[str] = mapped_column(Text)
    head_branch: Mapped[str] = mapped_column(Text)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, default=0)
    commits_count: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    review_comments_count: Mapped[int] = mapped_column(Integer, default=0)
    html_url: Mapped[str] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubIssue(Base):
    __tablename__ = "github_issues"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "github_issue_id", name="uq_github_issues_repo_github_id"
        ),
        UniqueConstraint("repository_id", "number", name="uq_github_issues_repo_number"),
        Index("ix_github_issues_repo_state", "repository_id", "state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    github_issue_id: Mapped[int] = mapped_column(BigInteger)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_users.id", ondelete="SET NULL"), index=True
    )
    author_login: Mapped[str | None] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    html_url: Mapped[str] = mapped_column(Text)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    milestone: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubLabel(Base):
    __tablename__ = "github_labels"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "github_label_id", name="uq_github_labels_repo_github_id"
        ),
        UniqueConstraint("repository_id", "name", name="uq_github_labels_repo_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    github_label_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(12))


class GitHubPRLabel(Base):
    __tablename__ = "github_pr_labels"
    __table_args__ = (UniqueConstraint("pull_request_id", "label_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_pull_requests.id", ondelete="CASCADE"), index=True
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_labels.id", ondelete="CASCADE"), index=True
    )


class GitHubIssueLabel(Base):
    __tablename__ = "github_issue_labels"
    __table_args__ = (UniqueConstraint("issue_id", "label_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_issues.id", ondelete="CASCADE"), index=True
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_labels.id", ondelete="CASCADE"), index=True
    )


class GitHubComment(Base):
    __tablename__ = "github_comments"
    __table_args__ = (
        UniqueConstraint("repository_id", "github_comment_id", "comment_type"),
        Index("ix_github_comments_pr_type", "pull_request_id", "comment_type"),
        Index("ix_github_comments_issue_type", "issue_id", "comment_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    github_comment_id: Mapped[int] = mapped_column(BigInteger)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_issues.id", ondelete="CASCADE"), index=True
    )
    pull_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_pull_requests.id", ondelete="CASCADE"), index=True
    )
    comment_type: Mapped[str] = mapped_column(String(30), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_users.id", ondelete="SET NULL"), index=True
    )
    author_login: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    html_url: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    original_commit_sha: Mapped[str | None] = mapped_column(String(40))
    line: Mapped[int | None] = mapped_column(Integer)
    original_line: Mapped[int | None] = mapped_column(Integer)
    side: Mapped[str | None] = mapped_column(String(10))
    diff_hunk: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubPRCommit(Base):
    __tablename__ = "github_pr_commits"
    __table_args__ = (UniqueConstraint("pull_request_id", "commit_sha"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_pull_requests.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CommitPRLink(Base):
    __tablename__ = "commit_pr_links"
    __table_args__ = (UniqueConstraint("commit_id", "pull_request_id", "link_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    pull_request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("github_pull_requests.id", ondelete="CASCADE"), index=True
    )
    link_type: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GitHubIssueReference(Base):
    __tablename__ = "github_issue_references"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "source_type",
            "source_id",
            "target_owner",
            "target_repository",
            "target_number",
            "reference_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(index=True)
    target_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("github_issues.id", ondelete="CASCADE"), index=True
    )
    target_owner: Mapped[str] = mapped_column(String(255))
    target_repository: Mapped[str] = mapped_column(String(255))
    target_number: Mapped[int] = mapped_column(Integer)
    reference_type: Mapped[str] = mapped_column(String(30), index=True)
    raw_reference: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)


class GitHubSyncState(Base):
    __tablename__ = "github_sync_state"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_synced", index=True)
    progress: Mapped[float | None] = mapped_column(Float)
    current_step: Mapped[str | None] = mapped_column(String(255))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_pr_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_issue_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    repository_etag: Mapped[str | None] = mapped_column(Text)
    pull_requests_indexed: Mapped[int] = mapped_column(Integer, default=0)
    issues_indexed: Mapped[int] = mapped_column(Integer, default=0)
    comments_indexed: Mapped[int] = mapped_column(Integer, default=0)
    review_comments_indexed: Mapped[int] = mapped_column(Integer, default=0)
    github_index_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    rate_limit_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
