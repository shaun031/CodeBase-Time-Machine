import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
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

from app.db.base import Base, Timestamps


class EvidenceDocument(Timestamps, Base):
    __tablename__ = "evidence_documents"
    __table_args__ = (
        UniqueConstraint("repository_id", "document_key", name="uq_evidence_document_key"),
        Index("ix_evidence_documents_repo_type", "repository_id", "evidence_type"),
        Index("ix_evidence_documents_repo_commit", "repository_id", "commit_sha"),
        Index("ix_evidence_documents_repo_lineage", "repository_id", "symbol_lineage_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    document_key: Mapped[str] = mapped_column(String(255))
    evidence_type: Mapped[str] = mapped_column(String(40), index=True)
    source_table: Mapped[str] = mapped_column(String(80))
    source_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    file_path: Mapped[str | None] = mapped_column(Text)
    symbol_lineage_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    pull_request_number: Mapped[int | None] = mapped_column(Integer, index=True)
    issue_number: Mapped[int | None] = mapped_column(Integer, index=True)
    created_source_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)


class EvidenceEmbedding(Base):
    __tablename__ = "evidence_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "evidence_document_id", "embedding_model", name="uq_evidence_embedding_doc_model"
        ),
        Index(
            "ix_evidence_embeddings_repo_model_dimension",
            "repository_id",
            "embedding_model",
            "embedding_dimension",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    evidence_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_documents.id", ondelete="CASCADE"), index=True
    )
    embedding: Mapped[list[float]] = mapped_column(Vector())
    embedding_model: Mapped[str] = mapped_column(String(255), index=True)
    embedding_dimension: Mapped[int] = mapped_column(Integer)
    embedding_version: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AIIndexState(Base):
    __tablename__ = "ai_index_states"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_indexed", index=True)
    progress: Mapped[float | None] = mapped_column(Float)
    current_step: Mapped[str | None] = mapped_column(String(100))
    documents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    embedded_documents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_version: Mapped[str | None] = mapped_column(String(64))
    last_indexed_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AIAnswerCache(Base):
    __tablename__ = "ai_answer_cache"
    __table_args__ = (
        UniqueConstraint("repository_id", "cache_key", name="uq_ai_answer_cache_repo_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
