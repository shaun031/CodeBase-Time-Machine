from typing import Any

from app.services.architecture_history.models import HistoricalGraph


def _distance(left: set[Any], right: set[Any]) -> float:
    union = left | right
    return 0.0 if not union else 1.0 - (len(left & right) / len(union))


def compare_graphs(before: HistoricalGraph, after: HistoricalGraph) -> dict[str, Any]:
    """Return a stable structural diff and an explicitly documented drift score."""
    old_nodes = {node.stable_key: node for node in before.nodes}
    new_nodes = {node.stable_key: node for node in after.nodes}
    old_edges = {(edge.source, edge.target, edge.edge_type): edge for edge in before.edges}
    new_edges = {(edge.source, edge.target, edge.edge_type): edge for edge in after.edges}
    old_cycles = {item["fingerprint"]: item for item in before.cycles}
    new_cycles = {item["fingerprint"]: item for item in after.cycles}
    common_nodes = old_nodes.keys() & new_nodes.keys()
    common_edges = old_edges.keys() & new_edges.keys()
    changed_nodes = [
        {
            "stable_key": key,
            "before": {"layer": old_nodes[key].layer, "path": old_nodes[key].path},
            "after": {"layer": new_nodes[key].layer, "path": new_nodes[key].path},
        }
        for key in sorted(common_nodes)
        if (old_nodes[key].layer, old_nodes[key].path)
        != (new_nodes[key].layer, new_nodes[key].path)
    ]
    changed_edges = [
        {
            "source": key[0],
            "target": key[1],
            "edge_type": key[2],
            "before_weight": old_edges[key].weight,
            "after_weight": new_edges[key].weight,
        }
        for key in sorted(common_edges)
        if old_edges[key].weight != new_edges[key].weight
    ]
    node_distance = _distance(set(old_nodes), set(new_nodes))
    edge_distance = _distance(set(old_edges), set(new_edges))
    cycle_distance = _distance(set(old_cycles), set(new_cycles))
    score = round(100 * (0.25 * node_distance + 0.60 * edge_distance + 0.15 * cycle_distance), 2)
    return {
        "nodes_added": [new_nodes[key].as_dict() for key in sorted(new_nodes.keys() - old_nodes.keys())],
        "nodes_removed": [old_nodes[key].as_dict() for key in sorted(old_nodes.keys() - new_nodes.keys())],
        "nodes_changed": changed_nodes,
        "edges_added": [new_edges[key].as_dict() for key in sorted(new_edges.keys() - old_edges.keys())],
        "edges_removed": [old_edges[key].as_dict() for key in sorted(old_edges.keys() - new_edges.keys())],
        "edges_changed": changed_edges,
        "cycles_introduced": [new_cycles[key] for key in sorted(new_cycles.keys() - old_cycles.keys())],
        "cycles_resolved": [old_cycles[key] for key in sorted(old_cycles.keys() - new_cycles.keys())],
        "metrics_before": before.metrics,
        "metrics_after": after.metrics,
        "structural_drift": {
            "score": score,
            "node_distance": round(node_distance, 6),
            "edge_distance": round(edge_distance, 6),
            "cycle_distance": round(cycle_distance, 6),
            "formula": "100 × (0.25 node Jaccard distance + 0.60 edge Jaccard distance + 0.15 cycle Jaccard distance)",
            "interpretation": "Structural difference from the selected baseline; it is not a policy judgment.",
        },
    }


def events_from_comparison(comparison: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for key, event_type in (
        ("edges_added", "dependency_introduced"),
        ("edges_removed", "dependency_removed"),
        ("cycles_introduced", "cycle_introduced"),
        ("cycles_resolved", "cycle_resolved"),
    ):
        for value in comparison[key]:
            result.append({"event_type": event_type, "value": value})
    for value in comparison["nodes_added"]:
        prefix = "component" if value["node_type"] == "component" else "module"
        result.append({"event_type": f"{prefix}_introduced", "value": value})
    for value in comparison["nodes_removed"]:
        prefix = "component" if value["node_type"] == "component" else "module"
        result.append({"event_type": f"{prefix}_removed", "value": value})
    for value in comparison["nodes_changed"]:
        result.append({"event_type": "layer_changed", "value": value})
    for value in comparison["edges_changed"]:
        result.append({"event_type": "dependency_weight_changed", "value": value})
    return result
