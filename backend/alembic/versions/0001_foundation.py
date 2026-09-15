"""Create the Phase 0 schema and make pgvector available."""

import sqlalchemy as sa

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False, server_default="github"),
        sa.Column("owner", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(511), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(255)),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "cloning",
                "indexing_git",
                "indexing_code",
                "indexing_github",
                "generating_embeddings",
                "ready",
                "failed",
                name="repository_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("local_path", sa.Text()),
        sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("indexing_error", sa.Text()),
        sa.CheckConstraint("provider = 'github'", name="provider_github"),
        *timestamps(),
    )
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"], unique=True)
    op.create_index("ix_repositories_status", "repositories", ["status"])
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="SET NULL")
        ),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        *timestamps(),
    )
    op.create_index("ix_analysis_jobs_repository_id", "analysis_jobs", ["repository_id"])
    op.create_index("ix_analysis_jobs_status", "analysis_jobs", ["status"])


def downgrade() -> None:
    op.drop_table("analysis_jobs")
    op.drop_table("repositories")
    # The extension is database-wide; preserve it for other local consumers.
