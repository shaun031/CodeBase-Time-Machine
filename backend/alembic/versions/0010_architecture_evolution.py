"""Add deterministic historical architecture snapshots, rules, and violations."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_architecture_evolution"
down_revision = "0009_software_archaeology"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "architecture_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
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
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("snapshot_type", sa.String(30), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edge_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("component_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("module_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "repository_id",
            "commit_sha",
            "snapshot_type",
            name="uq_architecture_snapshot_commit_type",
        ),
    )
    for column in ("repository_id", "commit_id", "commit_sha", "committed_at"):
        op.create_index(f"ix_architecture_snapshots_{column}", "architecture_snapshots", [column])
    op.create_index(
        "ix_architecture_snapshots_repo_date",
        "architecture_snapshots",
        ["repository_id", "committed_at"],
    )

    op.create_table(
        "architecture_snapshot_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stable_key", sa.Text(), nullable=False),
        sa.Column("node_type", sa.String(30), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text()),
        sa.Column("component_type", sa.String(30)),
        sa.Column("layer", sa.String(40)),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "stable_key", name="uq_snapshot_node_stable_key"),
    )
    for column in ("snapshot_id", "node_type", "layer"):
        op.create_index(f"ix_architecture_snapshot_nodes_{column}", "architecture_snapshot_nodes", [column])
    op.create_index(
        "ix_snapshot_nodes_type", "architecture_snapshot_nodes", ["snapshot_id", "node_type"]
    )

    op.create_table(
        "architecture_snapshot_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_node_id",
            sa.Uuid(),
            sa.ForeignKey("architecture_snapshot_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.Uuid(),
            sa.ForeignKey("architecture_snapshot_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("edge_type", sa.String(40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("resolution_type", sa.String(30), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_snapshot_edge_relationship",
        ),
    )
    for column in ("snapshot_id", "source_node_id", "target_node_id", "edge_type"):
        op.create_index(f"ix_architecture_snapshot_edges_{column}", "architecture_snapshot_edges", [column])
    op.create_index(
        "ix_snapshot_edges_type", "architecture_snapshot_edges", ["snapshot_id", "edge_type"]
    )

    op.create_table(
        "architecture_evolution_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE")),
        sa.Column("target_snapshot_id", sa.Uuid(), sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_stable_key", sa.Text()),
        sa.Column("target_stable_key", sa.Text()),
        sa.Column("old_value", postgresql.JSONB()),
        sa.Column("new_value", postgresql.JSONB()),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("repository_id", "commit_id", "commit_sha", "committed_at", "event_type", "source_snapshot_id", "target_snapshot_id"):
        op.create_index(f"ix_architecture_evolution_events_{column}", "architecture_evolution_events", [column])
    op.create_index("ix_architecture_events_repo_date", "architecture_evolution_events", ["repository_id", "committed_at"])
    op.create_index("ix_architecture_events_repo_type", "architecture_evolution_events", ["repository_id", "event_type"])

    op.create_table(
        "architecture_baselines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "name", name="uq_architecture_baseline_name"),
    )
    op.create_index("ix_architecture_baselines_repository_id", "architecture_baselines", ["repository_id"])
    op.create_index("ix_architecture_baselines_snapshot_id", "architecture_baselines", ["snapshot_id"])

    op.create_table(
        "architecture_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("rule_type", sa.String(40), nullable=False),
        sa.Column("source_selector", postgresql.JSONB(), nullable=False),
        sa.Column("target_selector", postgresql.JSONB()),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "name", name="uq_architecture_rule_name"),
    )
    for column in ("repository_id", "rule_type", "severity"):
        op.create_index(f"ix_architecture_rules_{column}", "architecture_rules", [column])

    op.create_table(
        "architecture_violations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.Uuid(), sa.ForeignKey("architecture_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("introduced_snapshot_id", sa.Uuid(), sa.ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("introduced_commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("introduced_commit_sha", sa.String(40), nullable=False),
        sa.Column("resolved_snapshot_id", sa.Uuid(), sa.ForeignKey("architecture_snapshots.id", ondelete="SET NULL")),
        sa.Column("resolved_commit_id", sa.Uuid(), sa.ForeignKey("commits.id", ondelete="SET NULL")),
        sa.Column("resolved_commit_sha", sa.String(40)),
        sa.Column("source_stable_key", sa.Text(), nullable=False),
        sa.Column("target_stable_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "introduced_snapshot_id", "source_stable_key", "target_stable_key", name="uq_architecture_violation_interval"),
    )
    for column in ("repository_id", "rule_id", "introduced_snapshot_id", "introduced_commit_id", "introduced_commit_sha", "resolved_snapshot_id", "resolved_commit_id", "resolved_commit_sha", "status"):
        op.create_index(f"ix_architecture_violations_{column}", "architecture_violations", [column])
    op.create_index("ix_architecture_violations_repo_status", "architecture_violations", ["repository_id", "status"])

    op.create_table(
        "architecture_history_states",
        sa.Column("repository_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_indexed"),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(100)),
        sa.Column("commits_examined", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshots_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycles_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("violations_detected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_sha", sa.String(40)),
        sa.Column("limited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error", sa.Text()),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("status", "last_indexed_sha", "job_id"):
        op.create_index(f"ix_architecture_history_states_{column}", "architecture_history_states", [column])


def downgrade() -> None:
    op.drop_table("architecture_history_states")
    op.drop_table("architecture_violations")
    op.drop_table("architecture_rules")
    op.drop_table("architecture_baselines")
    op.drop_table("architecture_evolution_events")
    op.drop_table("architecture_snapshot_edges")
    op.drop_table("architecture_snapshot_nodes")
    op.drop_table("architecture_snapshots")
