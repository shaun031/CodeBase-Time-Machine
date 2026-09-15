from collections import defaultdict
from pathlib import PurePosixPath
from uuid import UUID

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Commit, DependencyEdge, DependencyNode, FileChange


class GraphMetricsService:
    HOTSPOT_FORMULA = "0.45*changes + 0.35*degree_centrality + 0.20*coupling"
    CHANGE_WEIGHT = 0.45
    DEGREE_WEIGHT = 0.35
    COUPLING_WEIGHT = 0.20

    @staticmethod
    def _module(path: str) -> str:
        parent = PurePosixPath(path).parent.as_posix()
        return parent if parent != "." else "root"

    @staticmethod
    def normalize(values: dict[UUID, int]) -> dict[UUID, float]:
        if not values:
            return {}
        minimum = min(values.values())
        maximum = max(values.values())
        if maximum == 0:
            return {key: 0.0 for key in values}
        if minimum == maximum:
            return {key: 0.5 for key in values}
        scale = maximum - minimum
        return {key: (value - minimum) / scale for key, value in values.items()}

    @classmethod
    def hotspot_score(cls, changes: float, degree: float, coupling: float) -> float:
        return (
            cls.CHANGE_WEIGHT * changes
            + cls.DEGREE_WEIGHT * degree
            + cls.COUPLING_WEIGHT * coupling
        )

    @staticmethod
    def _level(node: DependencyNode) -> str | None:
        if node.node_type in {"module", "file"}:
            return node.node_type
        if node.node_type not in {"repository", "external_package"}:
            return "symbol"
        return None

    @classmethod
    def apply(cls, session: Session, repository_id: UUID, nodes: list[DependencyNode]) -> None:
        edges = list(
            session.scalars(
                select(DependencyEdge).where(DependencyEdge.repository_id == repository_id)
            )
        )
        node_by_id = {item.id: item for item in nodes}
        graphs: dict[str, nx.DiGraph[UUID]] = {
            "module": nx.DiGraph(),
            "file": nx.DiGraph(),
            "symbol": nx.DiGraph(),
        }
        for node in nodes:
            level = cls._level(node)
            if level:
                graphs[level].add_node(node.id)
        symbol_edges = {"CALLS", "INHERITS", "IMPLEMENTS"}
        for edge in edges:
            source = node_by_id.get(edge.source_node_id)
            target = node_by_id.get(edge.target_node_id)
            if source is None or target is None:
                continue
            source_level = cls._level(source)
            target_level = cls._level(target)
            if source_level != target_level or source_level is None:
                continue
            if source_level in {"module", "file"} and edge.edge_type == "DEPENDS_ON":
                graphs[source_level].add_edge(source.id, target.id)
            elif source_level == "symbol" and edge.edge_type in symbol_edges:
                graphs[source_level].add_edge(source.id, target.id)

        centrality: dict[UUID, float] = {}
        for level_graph in graphs.values():
            if len(level_graph) > 1:
                centrality.update(nx.degree_centrality(level_graph))
            else:
                centrality.update({node_id: 0.0 for node_id in level_graph})

        file_coupling: dict[UUID, float] = defaultdict(float)
        for edge in edges:
            if edge.edge_type != "CO_CHANGES_WITH":
                continue
            metadata = edge.metadata_json or {}
            evidence = metadata.get("evidence") or [{}]
            score = float(evidence[0].get("coupling_score", metadata.get("coupling_score", 0)))
            file_coupling[edge.source_node_id] = max(file_coupling[edge.source_node_id], score)
            file_coupling[edge.target_node_id] = max(file_coupling[edge.target_node_id], score)

        file_nodes = {item.qualified_name: item for item in nodes if item.node_type == "file"}
        commits_by_path: dict[str, set[UUID]] = defaultdict(set)
        authors_by_path: dict[str, set[str]] = defaultdict(set)
        history = session.execute(
            select(
                FileChange.commit_id,
                FileChange.new_path,
                FileChange.old_path,
                Commit.author_email,
            )
            .join(Commit, Commit.id == FileChange.commit_id)
            .where(FileChange.repository_id == repository_id)
        )
        for commit_id, new_path, old_path, author_email in history:
            for path in {new_path, old_path}:
                if path in file_nodes:
                    commits_by_path[path].add(commit_id)
                    authors_by_path[path].add(author_email)

        change_counts: dict[UUID, int] = {}
        author_counts: dict[UUID, int] = {}
        module_commits: dict[str, set[UUID]] = defaultdict(set)
        module_authors: dict[str, set[str]] = defaultdict(set)
        module_coupling: dict[str, float] = defaultdict(float)
        for path, node in file_nodes.items():
            change_counts[node.id] = len(commits_by_path[path])
            author_counts[node.id] = len(authors_by_path[path])
            module = cls._module(path)
            module_commits[module].update(commits_by_path[path])
            module_authors[module].update(authors_by_path[path])
            module_coupling[module] = max(module_coupling[module], file_coupling[node.id])
        for node in nodes:
            if node.node_type == "module":
                change_counts[node.id] = len(module_commits[node.qualified_name])
                author_counts[node.id] = len(module_authors[node.qualified_name])

        normalized_changes: dict[UUID, float] = {}
        for level in ("file", "module"):
            level_values = {
                node.id: change_counts.get(node.id, 0) for node in nodes if node.node_type == level
            }
            normalized_changes.update(cls.normalize(level_values))

        for node in nodes:
            level = cls._level(node)
            selected_graph = graphs.get(level) if level else None
            fan_in = int(selected_graph.in_degree(node.id)) if selected_graph is not None else 0
            fan_out = int(selected_graph.out_degree(node.id)) if selected_graph is not None else 0
            degree = float(centrality.get(node.id, 0.0))
            coupling_score = (
                file_coupling[node.id]
                if node.node_type == "file"
                else module_coupling[node.qualified_name]
                if node.node_type == "module"
                else 0.0
            )
            change_score = normalized_changes.get(node.id, 0.0)
            hotspot = cls.hotspot_score(change_score, degree, coupling_score)
            node.metrics_json = {
                "fan_in": fan_in,
                "fan_out": fan_out,
                "dependency_count": fan_out,
                "reverse_dependency_count": fan_in,
                "change_count": change_counts.get(node.id, 0),
                "author_count": author_counts.get(node.id, 0),
                "change_frequency_score": round(change_score, 6),
                "centrality": round(degree, 6),
                "coupling_score": round(coupling_score, 6),
                "change_contribution": round(cls.CHANGE_WEIGHT * change_score, 6),
                "degree_contribution": round(cls.DEGREE_WEIGHT * degree, 6),
                "coupling_contribution": round(cls.COUPLING_WEIGHT * coupling_score, 6),
                "hotspot_score": round(hotspot, 6),
            }
