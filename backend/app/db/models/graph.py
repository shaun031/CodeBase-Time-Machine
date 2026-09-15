import uuid
from datetime import datetime
from typing import Any

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


class DependencyNode(Timestamps, Base):
    __tablename__ = "dependency_nodes"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "node_type",
            "qualified_name",
            name="uq_dependency_nodes_repo_type_qualified",
        ),
        Index("ix_dependency_nodes_repo_type", "repository_id", "node_type"),
        Index("ix_dependency_nodes_repo_file", "repository_id", "file_id"),
        Index("ix_dependency_nodes_repo_symbol", "repository_id", "symbol_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    node_type: Mapped[str] = mapped_column(String(40), index=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_files.id", ondelete="CASCADE"), index=True
    )
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("code_symbols.id", ondelete="CASCADE"), index=True
    )
    external_name: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    qualified_name: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column("metrics", JSONB)


class DependencyEdge(Timestamps, Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_dependency_edges_repo_source_target_type",
        ),
        Index("ix_dependency_edges_repo_type", "repository_id", "edge_type"),
        Index("ix_dependency_edges_source_type", "source_node_id", "edge_type"),
        Index("ix_dependency_edges_target_type", "target_node_id", "edge_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependency_nodes.id", ondelete="CASCADE"), index=True
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependency_nodes.id", ondelete="CASCADE"), index=True
    )
    edge_type: Mapped[str] = mapped_column(String(40), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    resolution_type: Mapped[str] = mapped_column(String(30), default="exact")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class ArchitectureComponent(Timestamps, Base):
    __tablename__ = "architecture_components"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "path", name="uq_architecture_components_repository_path"
        ),
        Index("ix_architecture_components_repo_layer", "repository_id", "layer"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)
    component_type: Mapped[str] = mapped_column(String(40), default="directory")
    layer: Mapped[str | None] = mapped_column(String(40), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class ComponentMember(Base):
    __tablename__ = "component_members"
    __table_args__ = (
        UniqueConstraint("component_id", "node_id", name="uq_component_members_component_node"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    component_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_components.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dependency_nodes.id", ondelete="CASCADE"), index=True
    )


class GraphIndexState(Base):
    __tablename__ = "graph_index_states"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_indexed", index=True)
    progress: Mapped[float | None] = mapped_column(Float)
    current_step: Mapped[str | None] = mapped_column(String(100))
    nodes: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    edges: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cycles: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    components: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_indexed_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    graph_limited: Mapped[bool] = mapped_column(default=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
