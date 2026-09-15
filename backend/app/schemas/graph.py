from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GraphStatus(BaseModel):
    status: str
    progress: float | None
    current_step: str | None
    nodes: int
    edges: int
    cycles: int
    components: int
    last_indexed_sha: str | None
    graph_stale: bool
    graph_limited: bool
    error: str | None
    job_id: UUID | None
    completed_at: datetime | None


class GraphNodeRead(BaseModel):
    id: UUID
    node_type: str
    name: str
    qualified_name: str
    file_id: UUID | None
    symbol_id: UUID | None
    path: str | None
    language: str | None
    lineage_id: UUID | None
    layer: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeRead(BaseModel):
    id: UUID
    source_node_id: UUID
    target_node_id: UUID
    edge_type: str
    weight: float
    confidence: float
    resolution_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphView(BaseModel):
    level: Literal["module", "file", "symbol"]
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    limited: bool
    graph_stale: bool


class GraphNodeDetail(BaseModel):
    node: GraphNodeRead
    incoming_edges: list[GraphEdgeRead]
    outgoing_edges: list[GraphEdgeRead]
    component: str | None
    layer: str | None


class CycleRead(BaseModel):
    cycle_id: int
    members: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    size: int


class CycleResponse(BaseModel):
    level: Literal["file", "module"]
    cycles: list[CycleRead]


class CouplingPair(BaseModel):
    source: GraphNodeRead
    target: GraphNodeRead
    co_changes: int
    coupling_score: float


class CouplingDiagnostics(BaseModel):
    commits_examined: int
    commits_used: int
    commits_excluded_large: int
    candidate_pairs: int
    pairs_after_filtering: int


class CouplingResponse(BaseModel):
    level: Literal["file"]
    pairs: list[CouplingPair]
    formula: str
    diagnostics: CouplingDiagnostics


class GraphMetrics(BaseModel):
    nodes: int
    edges: int
    files: int
    symbols: int
    modules: int
    external_dependencies: int
    cycles: int
    dependency_relationships: int
    edge_counts: dict[str, int]
    relationship_levels: dict[str, int]
    average_fan_in: float
    average_fan_out: float
    top_fan_in: list[GraphNodeRead]
    top_fan_out: list[GraphNodeRead]
    top_hotspots: list[GraphNodeRead]
    hotspot_tie_count: int
    hotspot_formula: str
    normalization_note: str


class ArchitectureComponentRead(BaseModel):
    id: UUID
    name: str
    path: str
    component_type: str
    layer: str | None
    confidence: float | None
    node_count: int


class ComponentDependency(BaseModel):
    source_component_id: UUID
    target_component_id: UUID
    weight: int


class ArchitectureResponse(BaseModel):
    label: str = "Current Architecture"
    components: list[ArchitectureComponentRead]
    component_dependencies: list[ComponentDependency]
    layers: dict[str, int]
    metrics: GraphMetrics
    graph_stale: bool


class DependencyPathResponse(BaseModel):
    found: bool
    path: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    length: int | None


class ImpactPath(BaseModel):
    distance: int
    nodes: list[GraphNodeRead]
    edges: list[GraphEdgeRead]
    confidence: float


class ImpactResponse(BaseModel):
    wording: str = "Potentially affected"
    target: GraphNodeRead
    direct_dependencies: list[GraphNodeRead]
    direct_dependents: list[GraphNodeRead]
    transitive_dependents: list[GraphNodeRead]
    callers: list[GraphNodeRead]
    callees: list[GraphNodeRead]
    change_coupled_nodes: list[GraphNodeRead]
    paths: list[ImpactPath]
    metrics: dict[str, Any]
