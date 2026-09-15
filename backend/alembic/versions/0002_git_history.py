"""Add deterministic Git history persistence."""

import sqlalchemy as sa

from alembic import op

revision = "0002_git_history"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("head_sha", sa.String(40)))
    op.add_column(
        "repositories", sa.Column("commit_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("repositories", sa.Column("last_refreshed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "repositories",
        sa.Column("history_rewritten", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_table(
        "commits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sha", sa.String(40), nullable=False),
        sa.Column("short_sha", sa.String(12), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("author_name", sa.Text(), nullable=False),
        sa.Column("author_email", sa.Text(), nullable=False),
        sa.Column("committer_name", sa.Text(), nullable=False),
        sa.Column("committer_email", sa.Text(), nullable=False),
        sa.Column("authored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_merge_commit", sa.Boolean(), nullable=False),
        sa.Column("insertions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.Column("files_changed", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("repository_id", "sha"),
    )
    for name in ["repository_id", "sha", "committed_at"]:
        op.create_index(f"ix_commits_{name}", "commits", [name])
    op.create_table(
        "commit_parents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("parent_sha", sa.String(40), nullable=False),
        sa.Column("parent_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("commit_id", "parent_order"),
    )
    op.create_index("ix_commit_parents_commit_id", "commit_parents", ["commit_id"])
    op.create_table(
        "file_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("change_order", sa.Integer(), nullable=False),
        sa.Column("old_path", sa.Text()),
        sa.Column("new_path", sa.Text()),
        sa.Column("change_type", sa.String(20), nullable=False),
        sa.Column("additions", sa.Integer()),
        sa.Column("deletions", sa.Integer()),
        sa.Column("similarity_score", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("commit_id", "change_order"),
    )
    op.create_index("ix_file_changes_repository_id", "file_changes", ["repository_id"])
    op.create_index("ix_file_changes_commit_id", "file_changes", ["commit_id"])
    op.create_table(
        "tags",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("target_sha", sa.String(40), nullable=False),
        sa.Column("annotated", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("repository_id", "name"),
    )
    op.create_index("ix_tags_repository_id", "tags", ["repository_id"])
    op.create_index(
        "uq_analysis_jobs_active_repository",
        "analysis_jobs",
        ["repository_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_analysis_jobs_active_repository", table_name="analysis_jobs")
    for table in ["tags", "file_changes", "commit_parents", "commits"]:
        op.drop_table(table)
    for column in ["history_rewritten", "last_refreshed_at", "commit_count", "head_sha"]:
        op.drop_column("repositories", column)
