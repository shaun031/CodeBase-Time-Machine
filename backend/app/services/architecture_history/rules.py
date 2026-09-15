from typing import Any

from app.core.ingestion_errors import IngestionError
from app.services.architecture_history.models import HistoricalGraph, HistoricalNode

RULE_TYPES = {"allowed_dependency", "forbidden_dependency", "forbidden_cycle"}
SELECTOR_KINDS = {"layer", "component", "path_prefix", "module"}


def validate_rule(rule_type: str, source: dict[str, Any], target: dict[str, Any] | None) -> None:
    if rule_type not in RULE_TYPES:
        raise IngestionError("INVALID_ARCHITECTURE_RULE", "Unsupported architecture rule type.", 422)
    for selector in (source, target):
        if selector is None:
            continue
        if selector.get("kind") not in SELECTOR_KINDS or not str(selector.get("value", "")).strip():
            raise IngestionError("INVALID_ARCHITECTURE_RULE", "A selector needs a valid kind and value.", 422)
    if rule_type != "forbidden_cycle" and target is None:
        raise IngestionError("INVALID_ARCHITECTURE_RULE", "Dependency rules require a target selector.", 422)


def matches_selector(node: HistoricalNode, selector: dict[str, Any], threshold: float) -> bool:
    kind, value = selector["kind"], str(selector["value"]).strip().lower()
    if kind == "layer":
        return node.confidence >= threshold and (node.layer or "").lower() == value
    if kind == "component":
        path = (node.path or "").lower()
        return node.node_type == "component" and path == value
    if kind == "module":
        return node.node_type == "module" and (node.path or "").lower() == value
    return (node.path or "").lower().startswith(value.rstrip("/") + "/") or (
        node.path or ""
    ).lower() == value.rstrip("/")


def evaluate_rule(
    graph: HistoricalGraph,
    rule_type: str,
    source_selector: dict[str, Any],
    target_selector: dict[str, Any] | None,
    confidence_threshold: float = 0.8,
) -> list[dict[str, Any]]:
    validate_rule(rule_type, source_selector, target_selector)
    nodes = {node.stable_key: node for node in graph.nodes}
    result: list[dict[str, Any]] = []
    if rule_type == "forbidden_cycle":
        for cycle in graph.cycles:
            matching = [
                key
                for key in cycle["members"]
                if matches_selector(nodes[key], source_selector, confidence_threshold)
            ]
            if matching:
                result.append({
                    "source_stable_key": matching[0],
                    "target_stable_key": cycle["fingerprint"],
                    "confidence": min(nodes[key].confidence for key in matching),
                    "evidence": cycle,
                })
        return result
    assert target_selector is not None
    for edge in graph.edges:
        if edge.confidence < confidence_threshold:
            continue
        source, target = nodes[edge.source], nodes[edge.target]
        if source.node_type != "module" or target.node_type != "module":
            continue
        source_match = matches_selector(source, source_selector, confidence_threshold)
        target_match = matches_selector(target, target_selector, confidence_threshold)
        violates = source_match and (
            target_match if rule_type == "forbidden_dependency" else not target_match
        )
        if violates:
            result.append({
                "source_stable_key": edge.source,
                "target_stable_key": edge.target,
                "confidence": min(edge.confidence, source.confidence or 1.0, target.confidence or 1.0),
                "evidence": edge.as_dict(),
            })
    return result
