import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
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


class RepositoryFile(Timestamps, Base):
    __tablename__ = "repository_files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path"),
        Index("ix_repository_files_repository_path", "repository_id", "path"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    path: Mapped[str] = mapped_column(Text, index=True)
    filename: Mapped[str] = mapped_column(Text)
    extension: Mapped[str] = mapped_column(String(50), default="", server_default="")
    language: Mapped[str | None] = mapped_column(String(50), index=True)
    blob_sha: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    line_count: Mapped[int | None] = mapped_column(Integer)
    is_binary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    parse_status: Mapped[str] = mapped_column(String(30), index=True)
    syntax_error_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    indexed_commit_sha: Mapped[str] = mapped_column(String(40), index=True)


class CodeSymbol(Timestamps, Base):
    __tablename__ = "code_symbols"
    __table_args__ = (
        Index("ix_code_symbols_repository_name", "repository_id", "name"),
        Index("ix_code_symbols_repository_qualified", "repository_id", "qualified_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_files.id", ondelete="CASCADE"), index=True
    )
    parent_symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("code_symbols.id", ondelete="CASCADE"), index=True
    )
    lineage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("symbol_lineages.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    qualified_name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    signature: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    start_column: Mapped[int] = mapped_column(Integer)
    end_column: Mapped[int] = mapped_column(Integer)
    visibility: Mapped[str | None] = mapped_column(String(30))
    is_async: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_static: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    documentation: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class CodeImport(Base):
    __tablename__ = "code_imports"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_files.id", ondelete="CASCADE"), index=True
    )
    target_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_files.id", ondelete="SET NULL"), index=True
    )
    module: Mapped[str] = mapped_column(Text)
    imported_name: Mapped[str | None] = mapped_column(Text)
    alias: Mapped[str | None] = mapped_column(Text)
    import_type: Mapped[str] = mapped_column(String(30))
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FileParseError(Base):
    __tablename__ = "file_parse_errors"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_files.id", ondelete="CASCADE"), index=True
    )
    error_type: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
