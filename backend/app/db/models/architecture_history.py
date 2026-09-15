import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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

from app.db.base import Base


class ArchitectureSnapshot(Base):
    __tablename__ = "architecture_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "repository_id",
            "commit_sha",
            "snapshot_type",
            name="uq_architecture_snapshot_commit_type",
        ),
        Index("ix_architecture_snapshots_repo_date", "repository_id", "committed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(30), default="module_component")
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    node_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    edge_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    component_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    module_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cycle_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    metrics_json: Mapped[dict[str, Any]] = mapped_column("metrics", JSONB, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArchitectureSnapshotNode(Base):
    __tablename__ = "architecture_snapshot_nodes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "stable_key", name="uq_snapshot_node_stable_key"),
        Index("ix_snapshot_nodes_type", "snapshot_id", "node_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    stable_key: Mapped[str] = mapped_column(Text)
    node_type: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)
    component_type: Mapped[str | None] = mapped_column(String(30))
    layer: Mapped[str | None] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    metrics_json: Mapped[dict[str, Any]] = mapped_column("metrics", JSONB, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class ArchitectureSnapshotEdge(Base):
    __tablename__ = "architecture_snapshot_edges"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "source_node_id",
            "target_node_id",
            "edge_type",
            name="uq_snapshot_edge_relationship",
        ),
        Index("ix_snapshot_edges_type", "snapshot_id", "edge_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshot_nodes.id", ondelete="CASCADE"), index=True
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshot_nodes.id", ondelete="CASCADE"), index=True
    )
    edge_type: Mapped[str] = mapped_column(String(40), index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    resolution_type: Mapped[str] = mapped_column(String(30), default="exact")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)


class ArchitectureEvolutionEvent(Base):
    __tablename__ = "architecture_evolution_events"
    __table_args__ = (
        Index("ix_architecture_events_repo_date", "repository_id", "committed_at"),
        Index("ix_architecture_events_repo_type", "repository_id", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    target_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    source_stable_key: Mapped[str | None] = mapped_column(Text)
    target_stable_key: Mapped[str | None] = mapped_column(Text)
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArchitectureBaseline(Base):
    __tablename__ = "architecture_baselines"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_architecture_baseline_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ArchitectureRule(Base):
    __tablename__ = "architecture_rules"
    __table_args__ = (
        UniqueConstraint("repository_id", "name", name="uq_architecture_rule_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    rule_type: Mapped[str] = mapped_column(String(40), index=True)
    source_selector: Mapped[dict[str, Any]] = mapped_column(JSONB)
    target_selector: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArchitectureViolation(Base):
    __tablename__ = "architecture_violations"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "introduced_snapshot_id",
            "source_stable_key",
            "target_stable_key",
            name="uq_architecture_violation_interval",
        ),
        Index("ix_architecture_violations_repo_status", "repository_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), index=True
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_rules.id", ondelete="CASCADE"), index=True
    )
    introduced_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="CASCADE"), index=True
    )
    introduced_commit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("commits.id", ondelete="CASCADE"), index=True
    )
    introduced_commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    resolved_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("architecture_snapshots.id", ondelete="SET NULL"), index=True
    )
    resolved_commit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commits.id", ondelete="SET NULL"), index=True
    )
    resolved_commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    source_stable_key: Mapped[str] = mapped_column(Text)
    target_stable_key: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ArchitectureHistoryState(Base):
    __tablename__ = "architecture_history_states"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(30), default="not_indexed", index=True)
    progress: Mapped[float | None] = mapped_column(Float)
    current_step: Mapped[str | None] = mapped_column(String(100))
    commits_examined: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    snapshots_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    events_detected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cycles_detected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    violations_detected: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_indexed_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    limited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
