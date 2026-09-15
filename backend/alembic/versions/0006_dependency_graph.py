"""Add deterministic current dependency graph storage."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_dependency_graph"
down_revision = "0005_github_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dependency_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("repository_files.id", ondelete="CASCADE"),
        ),
        sa.Column("symbol_id", sa.Uuid(), sa.ForeignKey("code_symbols.id", ondelete="CASCADE")),
        sa.Column("external_name", sa.Text()),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("metrics", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "repository_id",
            "node_type",
            "qualified_name",
            name="uq_dependency_nodes_repo_type_qualified",
        ),
    )
    op.create_index("ix_dependency_nodes_repository_id", "dependency_nodes", ["repository_id"])
    op.create_index("ix_dependency_nodes_node_type", "dependency_nodes", ["node_type"])
    op.create_index("ix_dependency_nodes_file_id", "dependency_nodes", ["file_id"])
    op.create_index("ix_dependency_nodes_symbol_id", "dependency_nodes", ["symbol_id"])
    op.create_index(
        "ix_dependency_nodes_repo_type", "dependency_nodes", ["repository_id", "node_type"]
    )
    op.create_index(
        "ix_dependency_nodes_repo_file", "dependency_nodes", ["repository_id", "file_id"]
    )
    op.create_index(
        "ix_dependency_nodes_repo_symbol", "dependency_nodes", ["repository_id", "symbol_id"]
    )

    op.create_table(
        "dependency_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_node_id",
            sa.Uuid(),
            sa.ForeignKey("dependency_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_node_id",
            sa.Uuid(),
            sa.ForeignKey("dependency_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("edge_type", sa.String(40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("resolution_type", sa.String(30), nullable=False, server_default="exact"),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "repository_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_dependency_edges_repo_source_target_type",
        ),
    )
    for column in ("repository_id", "source_node_id", "target_node_id", "edge_type"):
        op.create_index(f"ix_dependency_edges_{column}", "dependency_edges", [column])
    op.create_index(
        "ix_dependency_edges_repo_type", "dependency_edges", ["repository_id", "edge_type"]
    )
    op.create_index(
        "ix_dependency_edges_source_type", "dependency_edges", ["source_node_id", "edge_type"]
    )
    op.create_index(
        "ix_dependency_edges_target_type", "dependency_edges", ["target_node_id", "edge_type"]
    )

    op.create_table(
        "architecture_components",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("component_type", sa.String(40), nullable=False, server_default="directory"),
        sa.Column("layer", sa.String(40)),
        sa.Column("confidence", sa.Float()),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "repository_id", "path", name="uq_architecture_components_repository_path"
        ),
    )
    op.create_index(
        "ix_architecture_components_repository_id", "architecture_components", ["repository_id"]
    )
    op.create_index("ix_architecture_components_layer", "architecture_components", ["layer"])
    op.create_index(
        "ix_architecture_components_repo_layer",
        "architecture_components",
        ["repository_id", "layer"],
    )

    op.create_table(
        "component_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "component_id",
            sa.Uuid(),
            sa.ForeignKey("architecture_components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.Uuid(),
            sa.ForeignKey("dependency_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("component_id", "node_id", name="uq_component_members_component_node"),
    )
    op.create_index("ix_component_members_component_id", "component_members", ["component_id"])
    op.create_index("ix_component_members_node_id", "component_members", ["node_id"])

    op.create_table(
        "graph_index_states",
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="not_indexed"),
        sa.Column("progress", sa.Float()),
        sa.Column("current_step", sa.String(100)),
        sa.Column("nodes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("edges", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cycles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("components", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_sha", sa.String(40)),
        sa.Column("graph_limited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("error", sa.Text()),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("analysis_jobs.id", ondelete="SET NULL")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_graph_index_states_status", "graph_index_states", ["status"])
    op.create_index(
        "ix_graph_index_states_last_indexed_sha", "graph_index_states", ["last_indexed_sha"]
    )
    op.create_index("ix_graph_index_states_job_id", "graph_index_states", ["job_id"])


def downgrade() -> None:
    op.drop_table("graph_index_states")
    op.drop_table("component_members")
    op.drop_table("architecture_components")
    op.drop_table("dependency_edges")
    op.drop_table("dependency_nodes")
