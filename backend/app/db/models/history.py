import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
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

from app.db.base import Base, Timestamps


class FileLineage(Timestamps, Base):
    __tablename__ = "file_lineages"
    __table_args__ = (Index("ix_file_lineages_repository", "repository_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("file_lineage_id", "commit_id"),
        Index("ix_file_versions_lineage_commit", "file_lineage_id", "commit_id"),
        Index("ix_file_versions_repository_path", "repository_id", "path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    file_lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("file_lineages.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text)
    blob_sha: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(50))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    line_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    change_type: Mapped[str] = mapped_column(String(20))
    previous_file_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_versions.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SymbolLineage(Timestamps, Base):
    __tablename__ = "symbol_lineages"
    __table_args__ = (Index("ix_symbol_lineages_repository_name", "repository_id", "current_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    symbol_kind: Mapped[str] = mapped_column(String(30), index=True)
    current_name: Mapped[str | None] = mapped_column(Text)
    current_qualified_name: Mapped[str | None] = mapped_column(Text)
    current_file_path: Mapped[str | None] = mapped_column(Text)
    introduced_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commits.id", ondelete="SET NULL"), index=True
    )
    last_seen_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commits.id", ondelete="SET NULL"), index=True
    )
    deleted_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commits.id", ondelete="SET NULL"), index=True
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class SymbolVersion(Base):
    __tablename__ = "symbol_versions"
    __table_args__ = (
        UniqueConstraint("lineage_id", "commit_id"),
        Index("ix_symbol_versions_lineage_commit", "lineage_id", "commit_id"),
        Index("ix_symbol_versions_repository_path", "repository_id", "file_path"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="CASCADE"), index=True
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    file_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("file_versions.id", ondelete="SET NULL"), index=True
    )
    file_path: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(Text)
    qualified_name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))
    signature: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    start_column: Mapped[int] = mapped_column(Integer)
    end_column: Mapped[int] = mapped_column(Integer)
    body_hash: Mapped[str | None] = mapped_column(String(64))
    normalized_body_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    signature_hash: Mapped[str | None] = mapped_column(String(64))
    structure_hash: Mapped[str | None] = mapped_column(String(64))
    source_text: Mapped[str | None] = mapped_column(Text)
    source_truncated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    documentation: Mapped[str | None] = mapped_column(Text)
    parent_lineage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="SET NULL"), index=True
    )
    match_type: Mapped[str] = mapped_column(String(30))
    match_confidence: Mapped[float] = mapped_column(Float)
    matching_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SymbolChangeEvent(Base):
    __tablename__ = "symbol_change_events"
    __table_args__ = (
        UniqueConstraint("lineage_id", "commit_id", "event_type"),
        Index("ix_symbol_change_events_lineage_commit", "lineage_id", "commit_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    lineage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="SET NULL")
    )
    new_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbol_versions.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    summary_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
