import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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


class ArchaeologyMetric(Base):
    __tablename__ = "archaeology_metrics"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "entity_type", "entity_id", name="uq_archaeology_metric_entity"
        ),
        Index("ix_archaeology_metrics_repo_type", "repository_id", "entity_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), index=True)
    introduced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    churn: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rename_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    move_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rewrite_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    volatility_score: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    stability_score: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    classification: Mapped[str] = mapped_column(String(40), index=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SymbolRewriteEvent(Base):
    __tablename__ = "symbol_rewrite_events"
    __table_args__ = (
        UniqueConstraint("old_version_id", "new_version_id", name="uq_symbol_rewrite_versions"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="CASCADE"), index=True
    )
    old_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="CASCADE")
    )
    new_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="CASCADE")
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    similarity: Mapped[float] = mapped_column(Float)
    lines_added: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lines_deleted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CopyMoveCandidate(Base):
    __tablename__ = "copy_move_candidates"
    __table_args__ = (
        UniqueConstraint("source_version_id", "target_version_id", name="uq_copy_move_versions"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="CASCADE"), index=True
    )
    target_lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="CASCADE")
    )
    target_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="CASCADE")
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    relationship: Mapped[str] = mapped_column(String(30), index=True)
    similarity: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ContributorEntityMetric(Base):
    __tablename__ = "contributor_entity_metrics"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "entity_type",
            "entity_id",
            "identity_key",
            name="uq_contributor_entity",
        ),
        Index("ix_contributor_entity_target", "repository_id", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    identity_key: Mapped[str] = mapped_column(String(64), index=True)
    display_name: Mapped[str] = mapped_column(Text)
    commit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lines_changed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_activity: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    knowledge_score: Mapped[float] = mapped_column(Float)
    contribution_share: Mapped[float] = mapped_column(Float)
    introduced: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class ArchaeologySyncState(Base):
    __tablename__ = "archaeology_sync_states"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default="not_indexed", server_default="not_indexed", index=True
    )
    progress: Mapped[float | None] = mapped_column(Float)
    current_step: Mapped[str | None] = mapped_column(String(100))
    files_processed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    symbols_processed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rewrites_detected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    copy_candidates: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    contributors: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_indexed_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
