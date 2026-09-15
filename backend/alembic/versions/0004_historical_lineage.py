"""Add deterministic historical file and symbol lineage storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_historical_lineage"
down_revision = "0003_static_analysis"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.execute(
        "ALTER TABLE repositories DROP CONSTRAINT IF EXISTS ck_repositories_repository_status"
    )
    op.execute("ALTER TABLE repositories DROP CONSTRAINT IF EXISTS repository_status")
    op.create_check_constraint(
        "repository_status",
        "repositories",
        "status IN ('pending','cloning','indexing_git','indexing_code','indexing_history',"
        "'indexing_github','generating_embeddings','ready','failed')",
    )
    op.add_column(
        "repositories",
        sa.Column(
            "history_index_status", sa.String(30), nullable=False, server_default="not_indexed"
        ),
    )
    op.add_column("repositories", sa.Column("history_indexed_through_sha", sa.String(40)))
    op.add_column(
        "repositories",
        sa.Column("history_limited", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "repositories",
        sa.Column("history_stale", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "repositories",
        sa.Column("history_indexed_commit_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "repositories",
        sa.Column("history_total_commit_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_repositories_history_index_status", "repositories", ["history_index_status"]
    )

    op.create_table(
        "file_lineages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *timestamps(),
    )
    op.create_index("ix_file_lineages_repository_id", "file_lineages", ["repository_id"])
    op.create_index("ix_file_lineages_repository", "file_lineages", ["repository_id"])

    op.create_table(
        "file_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "file_lineage_id",
            sa.Uuid(),
            sa.ForeignKey("file_lineages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commit_id",
            sa.Uuid(),
            sa.ForeignKey("commits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("blob_sha", sa.String(64)),
        sa.Column("language", sa.String(50)),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("line_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column(
            "previous_file_version_id",
            sa.Uuid(),
            sa.ForeignKey("file_versions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("file_lineage_id", "commit_id"),
    )
    for name in ["file_lineage_id", "repository_id", "commit_id", "previous_file_version_id"]:
        op.create_index(f"ix_file_versions_{name}", "file_versions", [name])
    op.create_index(
        "ix_file_versions_lineage_commit", "file_versions", ["file_lineage_id", "commit_id"]
    )
    op.create_index("ix_file_versions_repository_path", "file_versions", ["repository_id", "path"])

    op.create_table(
        "symbol_lineages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol_kind", sa.String(30), nullable=False),
        sa.Column("current_name", sa.Text()),
        sa.Column("current_qualified_name", sa.Text()),
        sa.Column("current_file_path", sa.Text()),
        sa.Column(
            "introduced_commit_id",
            sa.Uuid(),
            sa.ForeignKey("commits.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "last_seen_commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="SET NULL")
        ),
        sa.Column("deleted_commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="SET NULL")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        *timestamps(),
    )
    for name in [
        "repository_id",
        "symbol_kind",
        "introduced_commit_id",
        "last_seen_commit_id",
        "deleted_commit_id",
    ]:
        op.create_index(f"ix_symbol_lineages_{name}", "symbol_lineages", [name])
    op.create_index(
        "ix_symbol_lineages_repository_name", "symbol_lineages", ["repository_id", "current_name"]
    )

    op.create_table(
        "symbol_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commit_id",
            sa.Uuid(),
            sa.ForeignKey("commits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "file_version_id",
            sa.Uuid(),
            sa.ForeignKey("file_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(50)),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("signature", sa.Text()),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_column", sa.Integer(), nullable=False),
        sa.Column("end_column", sa.Integer(), nullable=False),
        sa.Column("body_hash", sa.String(64)),
        sa.Column("normalized_body_hash", sa.String(64)),
        sa.Column("signature_hash", sa.String(64)),
        sa.Column("structure_hash", sa.String(64)),
        sa.Column("source_text", sa.Text()),
        sa.Column("source_truncated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("documentation", sa.Text()),
        sa.Column(
            "parent_lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="SET NULL"),
        ),
        sa.Column("match_type", sa.String(30), nullable=False),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("matching_metadata", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("lineage_id", "commit_id"),
    )
    for name in [
        "lineage_id",
        "repository_id",
        "commit_id",
        "file_version_id",
        "normalized_body_hash",
        "parent_lineage_id",
    ]:
        op.create_index(f"ix_symbol_versions_{name}", "symbol_versions", [name])
    op.create_index(
        "ix_symbol_versions_lineage_commit", "symbol_versions", ["lineage_id", "commit_id"]
    )
    op.create_index(
        "ix_symbol_versions_repository_path", "symbol_versions", ["repository_id", "file_path"]
    )

    op.create_table(
        "symbol_change_events",
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
            "commit_id",
            sa.Uuid(),
            sa.ForeignKey("commits.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "previous_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "new_version_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_versions.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("summary_data", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("lineage_id", "commit_id", "event_type"),
    )
    for name in ["repository_id", "lineage_id", "commit_id", "event_type"]:
        op.create_index(f"ix_symbol_change_events_{name}", "symbol_change_events", [name])
    op.create_index(
        "ix_symbol_change_events_lineage_commit",
        "symbol_change_events",
        ["lineage_id", "commit_id"],
    )

    op.add_column(
        "code_symbols",
        sa.Column(
            "lineage_id",
            sa.Uuid(),
            sa.ForeignKey("symbol_lineages.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_code_symbols_lineage_id", "code_symbols", ["lineage_id"])


def downgrade() -> None:
    op.drop_index("ix_code_symbols_lineage_id", table_name="code_symbols")
    op.drop_column("code_symbols", "lineage_id")
    for table in [
        "symbol_change_events",
        "symbol_versions",
        "symbol_lineages",
        "file_versions",
        "file_lineages",
    ]:
        op.drop_table(table)
    op.drop_index("ix_repositories_history_index_status", table_name="repositories")
    for column in [
        "history_total_commit_count",
        "history_indexed_commit_count",
        "history_stale",
        "history_limited",
        "history_indexed_through_sha",
        "history_index_status",
    ]:
        op.drop_column("repositories", column)
    op.execute("UPDATE repositories SET status = 'ready' WHERE status = 'indexing_history'")
    op.drop_constraint("repository_status", "repositories", type_="check")
    op.create_check_constraint(
        "repository_status",
        "repositories",
        "status IN ('pending','cloning','indexing_git','indexing_code','indexing_github',"
        "'generating_embeddings','ready','failed')",
    )
