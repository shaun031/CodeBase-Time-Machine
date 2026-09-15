"""Add local AI evidence, vector embeddings, and index state."""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_local_ai_rag"
down_revision = "0007_graph_timestamp_constraints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "evidence_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_key", sa.String(255), nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("source_table", sa.String(80), nullable=False),
        sa.Column("source_id", sa.Uuid()),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("file_path", sa.Text()),
        sa.Column("symbol_lineage_id", sa.Uuid()),
        sa.Column("pull_request_number", sa.Integer()),
        sa.Column("issue_number", sa.Integer()),
        sa.Column("created_source_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("repository_id", "document_key", name="uq_evidence_document_key"),
    )
    for name in (
        "repository_id",
        "evidence_type",
        "source_id",
        "commit_sha",
        "symbol_lineage_id",
        "pull_request_number",
        "issue_number",
        "content_hash",
    ):
        op.create_index(f"ix_evidence_documents_{name}", "evidence_documents", [name])
    op.create_index(
        "ix_evidence_documents_repo_type", "evidence_documents", ["repository_id", "evidence_type"]
    )
    op.create_index(
        "ix_evidence_documents_repo_commit", "evidence_documents", ["repository_id", "commit_sha"]
    )
    op.create_index(
        "ix_evidence_documents_repo_lineage",
        "evidence_documents",
        ["repository_id", "symbol_lineage_id"],
    )

    op.create_table(
        "evidence_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "evidence_document_id",
            sa.Uuid(),
            sa.ForeignKey("evidence_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("embedding_version", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "evidence_document_id", "embedding_model", name="uq_evidence_embedding_doc_model"
        ),
    )
    for name in ("repository_id", "evidence_document_id", "embedding_model", "content_hash"):
        op.create_index(f"ix_evidence_embeddings_{name}", "evidence_embeddings", [name])
    op.create_index(
        "ix_evidence_embeddings_repo_model_dimension",
        "evidence_embeddings",
        ["repository_id", "embedding_model", "embedding_dimension"],
    )

    op.create_table(
        "ai_index_states",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_indexed"),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(100)),
        sa.Column("documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(255)),
        sa.Column("embedding_dimension", sa.Integer()),
        sa.Column("embedding_version", sa.String(64)),
        sa.Column("last_indexed_sha", sa.String(40)),
        sa.Column("error", sa.Text()),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    for name in ("status", "last_indexed_sha", "job_id"):
        op.create_index(f"ix_ai_index_states_{name}", "ai_index_states", [name])

    op.create_table(
        "ai_answer_cache",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("response_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("repository_id", "cache_key", name="uq_ai_answer_cache_repo_key"),
    )
    op.create_index("ix_ai_answer_cache_repository_id", "ai_answer_cache", ["repository_id"])
    op.create_index("ix_ai_answer_cache_cache_key", "ai_answer_cache", ["cache_key"])


def downgrade() -> None:
    op.drop_table("ai_answer_cache")
    op.drop_table("ai_index_states")
    op.drop_table("evidence_embeddings")
    op.drop_table("evidence_documents")
