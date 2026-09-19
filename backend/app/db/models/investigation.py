import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = (Index("ix_investigations_repo_created", "repository_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    input_type: Mapped[str] = mapped_column(String(40))
    stack_trace: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    known_good_commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    known_bad_commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    file_path: Mapped[str | None] = mapped_column(Text)
    line: Mapped[int | None] = mapped_column(Integer)
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="SET NULL"), index=True
    )
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BisectSession(Base):
    __tablename__ = "bisect_sessions"
    __table_args__ = (Index("ix_bisect_sessions_repo_updated", "repository_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    good_commit_sha: Mapped[str] = mapped_column(String(40))
    bad_commit_sha: Mapped[str] = mapped_column(String(40))
    current_candidate_sha: Mapped[str | None] = mapped_column(String(40))
    remaining_commits: Mapped[list[str]] = mapped_column(JSONB, default=list)
    classifications: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    remaining_commit_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InvestigationCandidateFeedback(Base):
    __tablename__ = "investigation_candidate_feedback"
    __table_args__ = (
        UniqueConstraint("investigation_id", "commit_sha", name="uq_investigation_feedback"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    result: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

