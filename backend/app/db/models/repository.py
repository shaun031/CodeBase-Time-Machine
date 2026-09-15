import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps


class RepositoryStatus(enum.StrEnum):
    pending = "pending"
    cloning = "cloning"
    indexing_git = "indexing_git"
    indexing_code = "indexing_code"
    indexing_history = "indexing_history"
    indexing_github = "indexing_github"
    generating_embeddings = "generating_embeddings"
    ready = "ready"
    failed = "failed"


class Repository(Timestamps, Base):
    __tablename__ = "repositories"
    __table_args__ = (CheckConstraint("provider = 'github'", name="provider_github"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(20), default="github", server_default="github")
    owner: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(511), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status", native_enum=False, create_constraint=True),
        default=RepositoryStatus.pending,
        server_default="pending",
        index=True,
    )
    local_path: Mapped[str | None] = mapped_column(Text)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexing_error: Mapped[str | None] = mapped_column(Text)
    head_sha: Mapped[str | None] = mapped_column(String(40))
    commit_count: Mapped[int] = mapped_column(default=0, server_default="0")
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history_rewritten: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    history_index_status: Mapped[str] = mapped_column(
        String(30), default="not_indexed", server_default="not_indexed", index=True
    )
    history_indexed_through_sha: Mapped[str | None] = mapped_column(String(40))
    history_limited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    history_stale: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    history_indexed_commit_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    history_total_commit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
