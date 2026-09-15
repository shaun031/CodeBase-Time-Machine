from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoricalNode:
    stable_key: str
    node_type: str
    name: str
    path: str | None
    layer: str | None
    confidence: float
    component_type: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "stable_key": self.stable_key,
            "node_type": self.node_type,
            "name": self.name,
            "path": self.path,
            "layer": self.layer,
            "confidence": self.confidence,
            "component_type": self.component_type,
            "metrics": self.metrics,
            "metadata": self.metadata,
        }


@dataclass
class HistoricalEdge:
    source: str
    target: str
    edge_type: str = "DEPENDS_ON"
    weight: float = 1.0
    confidence: float = 1.0
    resolution_type: str = "exact"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "confidence": self.confidence,
            "resolution_type": self.resolution_type,
            "metadata": self.metadata,
        }


@dataclass
class HistoricalGraph:
    nodes: list[HistoricalNode]
    edges: list[HistoricalEdge]
    cycles: list[dict[str, Any]]
    metrics: dict[str, Any]
    limited: bool = False
