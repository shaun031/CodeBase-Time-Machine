"""Align graph timestamp nullability with the shared model contract."""

from alembic import op

revision = "0007_graph_timestamp_constraints"
down_revision = "0006_dependency_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("dependency_nodes", "dependency_edges", "architecture_components"):
        op.alter_column(table, "created_at", nullable=False)
        op.alter_column(table, "updated_at", nullable=False)
    op.alter_column("graph_index_states", "updated_at", nullable=False)


def downgrade() -> None:
    op.alter_column("graph_index_states", "updated_at", nullable=True)
    for table in ("architecture_components", "dependency_edges", "dependency_nodes"):
        op.alter_column(table, "updated_at", nullable=True)
        op.alter_column(table, "created_at", nullable=True)
