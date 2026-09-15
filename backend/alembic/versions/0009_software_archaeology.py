"""Add deterministic software archaeology derived records."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009_software_archaeology"
down_revision = "0008_local_ai_rag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archaeology_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("kind", sa.String(30)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("introduced_at", sa.DateTime(timezone=True)),
        sa.Column("last_modified_at", sa.DateTime(timezone=True)),
        sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("churn", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contributor_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rename_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("move_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewrite_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("volatility_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stability_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "repository_id", "entity_type", "entity_id", name="uq_archaeology_metric_entity"
        ),
    )
    op.create_index(
        "ix_archaeology_metrics_repository_id", "archaeology_metrics", ["repository_id"]
    )
    op.create_index("ix_archaeology_metrics_entity_type", "archaeology_metrics", ["entity_type"])
    op.create_index("ix_archaeology_metrics_entity_id", "archaeology_metrics", ["entity_id"])
    op.create_index("ix_archaeology_metrics_status", "archaeology_metrics", ["status"])
    op.create_index(
        "ix_archaeology_metrics_classification", "archaeology_metrics", ["classification"]
    )
    op.create_index(
        "ix_archaeology_metrics_repo_type", "archaeology_metrics", ["repository_id", "entity_type"]
    )

    op.create_table(
        "symbol_rewrite_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "old_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "new_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("lines_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("old_version_id", "new_version_id", name="uq_symbol_rewrite_versions"),
    )
    for column in ("repository_id", "lineage_id", "commit_id"):
        op.create_index(f"ix_symbol_rewrite_events_{column}", "symbol_rewrite_events", [column])

    op.create_table(
        "copy_move_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("relationship", sa.String(30), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("source_version_id", "target_version_id", name="uq_copy_move_versions"),
    )
    for column in (
        "repository_id",
        "source_lineage_id",
        "target_lineage_id",
        "commit_id",
        "relationship",
    ):
        op.create_index(f"ix_copy_move_candidates_{column}", "copy_move_candidates", [column])

    op.create_table(
        "contributor_entity_metrics",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("commit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_activity", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=False),
        sa.Column("knowledge_score", sa.Float(), nullable=False),
        sa.Column("contribution_share", sa.Float(), nullable=False),
        sa.Column("introduced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB()),
        sa.UniqueConstraint(
            "repository_id",
            "entity_type",
            "entity_id",
            "identity_key",
            name="uq_contributor_entity",
        ),
    )
    op.create_index(
        "ix_contributor_entity_metrics_repository_id",
        "contributor_entity_metrics",
        ["repository_id"],
    )
    op.create_index(
        "ix_contributor_entity_metrics_identity_key", "contributor_entity_metrics", ["identity_key"]
    )
    op.create_index(
        "ix_contributor_entity_target",
        "contributor_entity_metrics",
        ["repository_id", "entity_type", "entity_id"],
    )

    op.create_table(
        "archaeology_sync_states",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_indexed"),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(100)),
        sa.Column("files_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewrites_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("copy_candidates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contributors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_sha", sa.String(40)),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL")),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    for column in ("status", "last_indexed_sha", "job_id"):
        op.create_index(f"ix_archaeology_sync_states_{column}", "archaeology_sync_states", [column])


def downgrade() -> None:
    op.drop_table("archaeology_sync_states")
    op.drop_table("contributor_entity_metrics")
    op.drop_table("copy_move_candidates")
    op.drop_table("symbol_rewrite_events")
    op.drop_table("archaeology_metrics")
