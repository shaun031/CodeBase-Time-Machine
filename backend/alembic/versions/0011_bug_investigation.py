"""Add deterministic bug investigations and manual bisect sessions."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_bug_investigation"
down_revision = "0010_architecture_evolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL"), unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("input_type", sa.String(40), nullable=False),
        sa.Column("stack_trace", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("known_good_commit_sha", sa.String(40)),
        sa.Column("known_bad_commit_sha", sa.String(40)),
        sa.Column("file_path", sa.Text()),
        sa.Column("line", sa.Integer()),
        sa.Column("lineage_id", sa.Uuid(), sa.ForeignKey("symbol_lineages.id", ondelete="SET NULL")),
        sa.Column("result_summary", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    for column in ("repository_id", "job_id", "status", "known_good_commit_sha", "known_bad_commit_sha", "lineage_id"):
        op.create_index(f"ix_investigations_{column}", "investigations", [column])
    op.create_index("ix_investigations_repo_created", "investigations", ["repository_id", "created_at"])

    op.create_table(
        "bisect_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("good_commit_sha", sa.String(40), nullable=False),
        sa.Column("bad_commit_sha", sa.String(40), nullable=False),
        sa.Column("current_candidate_sha", sa.String(40)),
        sa.Column("remaining_commits", postgresql.JSONB(), nullable=False),
        sa.Column("classifications", postgresql.JSONB(), nullable=False),
        sa.Column("remaining_commit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bisect_sessions_repository_id", "bisect_sessions", ["repository_id"])
    op.create_index("ix_bisect_sessions_status", "bisect_sessions", ["status"])
    op.create_index("ix_bisect_sessions_repo_updated", "bisect_sessions", ["repository_id", "updated_at"])

    op.create_table(
        "investigation_candidate_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("investigation_id", sa.Uuid(), sa.ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("investigation_id", "commit_sha", name="uq_investigation_feedback"),
    )
    op.create_index("ix_investigation_candidate_feedback_investigation_id", "investigation_candidate_feedback", ["investigation_id"])
    op.create_index("ix_investigation_candidate_feedback_commit_sha", "investigation_candidate_feedback", ["commit_sha"])


def downgrade() -> None:
    op.drop_table("investigation_candidate_feedback")
    op.drop_table("bisect_sessions")
    op.drop_table("investigations")

