from collections import Counter, defaultdict, deque
from uuid import UUID

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    ArchitectureComponent,
    ComponentMember,
    DependencyEdge,
    DependencyNode,
    GraphIndexState,
    Repository,
    RepositoryFile,
)
from app.schemas.graph import (
    ArchitectureComponentRead,
    ArchitectureResponse,
    ComponentDependency,
    CouplingDiagnostics,
    CouplingPair,
    CouplingResponse,
    CycleRead,
    CycleResponse,
    DependencyPathResponse,
    GraphEdgeRead,
    GraphMetrics,
    GraphNodeDetail,
    GraphNodeRead,
    GraphStatus,
    GraphView,
    ImpactPath,
    ImpactResponse,
)
from app.services.files import FileService
from app.services.graph.coupling import ChangeCouplingService
from app.services.graph.cycles import CycleDetectionService
from app.services.graph.impact import ImpactAnalysisService
from app.services.graph.metrics import GraphMetricsService

STATIC_TYPES = {"IMPORTS", "REFERENCES", "CALLS", "INHERITS", "IMPLEMENTS", "DEPENDS_ON"}
SYMBOL_TYPES = {
    "class",
    "interface",
    "function",
    "method",
    "constructor",
    "enum",
    "struct",
    "trait",
}


class GraphService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def _repository(self, repository_id: UUID) -> tuple[Repository, GraphIndexState]:
        repository = self.session.get(Repository, repository_id)
        if repository is None:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
        state = self.session.get(GraphIndexState, repository_id)
        if state is None or state.status not in {"ready", "limited"}:
            raise IngestionError(
                "GRAPH_NOT_INDEXED",
                "Build the current dependency graph before using this view.",
                409,
            )
        return repository, state

    def status(self, repository_id: UUID) -> GraphStatus:
        repository = self.session.get(Repository, repository_id)
        if repository is None:
            raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
        state = self.session.get(GraphIndexState, repository_id)
        if state is None:
            return GraphStatus(
                status="not_indexed",
                progress=None,
                current_step=None,
                nodes=0,
                edges=0,
                cycles=0,
                components=0,
                last_indexed_sha=None,
                graph_stale=bool(repository.head_sha),
                graph_limited=False,
                error=None,
                job_id=None,
                completed_at=None,
            )
        return GraphStatus(
            status=state.status,
            progress=state.progress,
            current_step=state.current_step,
            nodes=state.nodes,
            edges=state.edges,
            cycles=state.cycles,
            components=state.components,
            last_indexed_sha=state.last_indexed_sha,
            graph_stale=state.last_indexed_sha != repository.head_sha,
            graph_limited=state.graph_limited,
            error=state.error,
            job_id=state.job_id,
            completed_at=state.completed_at,
        )

    def _node(self, item: DependencyNode, layer: str | None = None) -> GraphNodeRead:
        metadata = item.metadata_json or {}
        lineage = metadata.get("lineage_id")
        return GraphNodeRead(
            id=item.id,
            node_type=item.node_type,
            name=item.name,
            qualified_name=item.qualified_name,
            file_id=item.file_id,
            symbol_id=item.symbol_id,
            path=metadata.get("path")
            or (item.qualified_name if item.node_type == "file" else None),
            language=metadata.get("language"),
            lineage_id=UUID(lineage) if lineage else None,
            layer=layer,
            metrics=item.metrics_json or {},
            metadata=metadata,
        )

    @staticmethod
    def _edge(item: DependencyEdge) -> GraphEdgeRead:
        return GraphEdgeRead(
            id=item.id,
            source_node_id=item.source_node_id,
            target_node_id=item.target_node_id,
            edge_type=item.edge_type,
            weight=item.weight,
            confidence=item.confidence,
            resolution_type=item.resolution_type,
            metadata=item.metadata_json or {},
        )

    def _all(self, repository_id: UUID) -> tuple[list[DependencyNode], list[DependencyEdge]]:
        nodes = list(
            self.session.scalars(
                select(DependencyNode).where(DependencyNode.repository_id == repository_id)
            )
        )
        edges = list(
            self.session.scalars(
                select(DependencyEdge).where(DependencyEdge.repository_id == repository_id)
            )
        )
        return nodes, edges

    def graph(
        self,
        repository_id: UUID,
        level: str,
        path: str | None,
        node_type: str | None,
        edge_type: str | None,
        max_nodes: int,
    ) -> GraphView:
        repository, state = self._repository(repository_id)
        allowed = {
            "module": {"module"},
            "file": {"file"},
            "symbol": SYMBOL_TYPES,
        }
        if level not in allowed:
            raise IngestionError("INVALID_GRAPH_LEVEL", "Graph level is invalid.", 422)
        if path:
            path = FileService.validate_repository_path(path)
        limit = min(max_nodes, self.settings.max_graph_response_nodes)
        nodes, edges = self._all(repository_id)
        selected = [
            item
            for item in nodes
            if item.node_type in allowed[level]
            and (not node_type or item.node_type == node_type)
            and (
                not path
                or item.qualified_name == path
                or item.qualified_name.startswith(path.rstrip("/") + "/")
                or item.qualified_name.startswith(path + "::")
            )
        ]
        selected.sort(key=lambda item: (item.qualified_name, str(item.id)))
        limited = len(selected) > limit
        selected = selected[:limit]
        ids = {item.id for item in selected}
        selected_edges = [
            item
            for item in edges
            if item.source_node_id in ids
            and item.target_node_id in ids
            and (not edge_type or item.edge_type == edge_type)
            and item.edge_type != "CONTAINS"
        ]
        return GraphView(
            level=level,
            nodes=[self._node(item) for item in selected],
            edges=[self._edge(item) for item in selected_edges],
            limited=limited or state.graph_limited,
            graph_stale=state.last_indexed_sha != repository.head_sha,
        )

    def subgraph(
        self,
        repository_id: UUID,
        node_id: UUID,
        direction: str,
        depth: int,
        edge_types: set[str] | None,
    ) -> GraphView:
        repository, state = self._repository(repository_id)
        if direction not in {"incoming", "outgoing", "both"}:
            raise IngestionError("INVALID_GRAPH_DIRECTION", "Graph direction is invalid.", 422)
        depth = min(depth, self.settings.max_graph_depth)
        nodes, edges = self._all(repository_id)
        by_id = {item.id: item for item in nodes}
        if node_id not in by_id:
            raise IngestionError("GRAPH_NODE_NOT_FOUND", "Graph node not found.", 404)
        usable = [item for item in edges if not edge_types or item.edge_type in edge_types]
        outgoing: dict[UUID, list[UUID]] = defaultdict(list)
        incoming: dict[UUID, list[UUID]] = defaultdict(list)
        for item in usable:
            outgoing[item.source_node_id].append(item.target_node_id)
            incoming[item.target_node_id].append(item.source_node_id)
        seen = {node_id}
        queue = deque([(node_id, 0)])
        while queue and len(seen) < self.settings.max_graph_response_nodes:
            current, distance = queue.popleft()
            if distance >= depth:
                continue
            adjacent: list[UUID] = []
            if direction in {"outgoing", "both"}:
                adjacent.extend(outgoing[current])
            if direction in {"incoming", "both"}:
                adjacent.extend(incoming[current])
            for value in adjacent:
                if value not in seen:
                    seen.add(value)
                    queue.append((value, distance + 1))
        selected = [by_id[value] for value in seen]
        selected_edges = [
            item for item in usable if item.source_node_id in seen and item.target_node_id in seen
        ]
        level = (
            "file"
            if by_id[node_id].node_type == "file"
            else "module"
            if by_id[node_id].node_type == "module"
            else "symbol"
        )
        return GraphView(
            level=level,
            nodes=[self._node(item) for item in selected],
            edges=[self._edge(item) for item in selected_edges],
            limited=len(seen) >= self.settings.max_graph_response_nodes,
            graph_stale=state.last_indexed_sha != repository.head_sha,
        )

    def node_detail(self, repository_id: UUID, node_id: UUID) -> GraphNodeDetail:
        self._repository(repository_id)
        item = self.session.scalar(
            select(DependencyNode).where(
                DependencyNode.repository_id == repository_id, DependencyNode.id == node_id
            )
        )
        if item is None:
            raise IngestionError("GRAPH_NODE_NOT_FOUND", "Graph node not found.", 404)
        incoming = list(
            self.session.scalars(
                select(DependencyEdge)
                .where(DependencyEdge.target_node_id == node_id)
                .order_by(DependencyEdge.edge_type)
                .limit(100)
            )
        )
        outgoing = list(
            self.session.scalars(
                select(DependencyEdge)
                .where(DependencyEdge.source_node_id == node_id)
                .order_by(DependencyEdge.edge_type)
                .limit(100)
            )
        )
        component = self.session.execute(
            select(ArchitectureComponent.name, ArchitectureComponent.layer)
            .join(ComponentMember, ComponentMember.component_id == ArchitectureComponent.id)
            .where(ComponentMember.node_id == node_id)
            .limit(1)
        ).first()
        if component is None and item.node_type == "module":
            component = self.session.execute(
                select(ArchitectureComponent.name, ArchitectureComponent.layer)
                .where(
                    ArchitectureComponent.repository_id == repository_id,
                    ArchitectureComponent.path == item.qualified_name,
                )
                .limit(1)
            ).first()
        return GraphNodeDetail(
            node=self._node(item, component.layer if component else None),
            incoming_edges=[self._edge(edge) for edge in incoming],
            outgoing_edges=[self._edge(edge) for edge in outgoing],
            component=component.name if component else None,
            layer=component.layer if component else None,
        )

    def cycles(self, repository_id: UUID, level: str) -> CycleResponse:
        self._repository(repository_id)
        if level not in {"file", "module"}:
            raise IngestionError("INVALID_GRAPH_LEVEL", "Cycle level must be file or module.", 422)
        nodes, edges = self._all(repository_id)
        selected = {item.id: item for item in nodes if item.node_type == level}
        graph: nx.DiGraph[UUID] = nx.DiGraph()
        graph.add_nodes_from(selected)
        dependency_edges = [
            item
            for item in edges
            if item.edge_type == "DEPENDS_ON"
            and item.source_node_id in selected
            and item.target_node_id in selected
        ]
        graph.add_edges_from(
            (item.source_node_id, item.target_node_id) for item in dependency_edges
        )
        by_pair = {(item.source_node_id, item.target_node_id): item for item in dependency_edges}
        groups = CycleDetectionService.find(graph)
        return CycleResponse(
            level=level,
            cycles=[
                CycleRead(
                    cycle_id=index,
                    members=[self._node(selected[node]) for node in group.members],
                    edges=[self._edge(by_pair[pair]) for pair in group.edges],
                    size=len(group.members),
                )
                for index, group in enumerate(groups, 1)
            ],
        )

    def coupling(
        self, repository_id: UUID, min_score: float, min_co_changes: int, path: str | None
    ) -> CouplingResponse:
        self._repository(repository_id)
        if path:
            path = FileService.validate_repository_path(path)
        nodes, edges = self._all(repository_id)
        by_id = {item.id: item for item in nodes}
        path_ids = {
            item.path: item.id
            for item in self.session.scalars(
                select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
            )
        }
        analysis = ChangeCouplingService.calculate(
            self.session,
            repository_id,
            path_ids,
            self.settings.max_files_per_commit_for_coupling,
        )
        pairs: list[CouplingPair] = []
        for item in edges:
            if item.edge_type != "CO_CHANGES_WITH":
                continue
            evidence = (item.metadata_json or {}).get("evidence", [{}])[0]
            count = int(evidence.get("co_change_count", item.weight))
            score = float(evidence.get("coupling_score", item.confidence))
            source = by_id[item.source_node_id]
            target = by_id[item.target_node_id]
            if count < min_co_changes or score < min_score:
                continue
            if path and not (
                source.qualified_name.startswith(path) or target.qualified_name.startswith(path)
            ):
                continue
            pairs.append(
                CouplingPair(
                    source=self._node(source),
                    target=self._node(target),
                    co_changes=count,
                    coupling_score=score,
                )
            )
        pairs.sort(
            key=lambda item: (-item.coupling_score, -item.co_changes, item.source.qualified_name)
        )
        return CouplingResponse(
            level="file",
            pairs=pairs[: self.settings.max_graph_response_nodes],
            formula="co_change_count / min(source_change_count, target_change_count)",
            diagnostics=CouplingDiagnostics(
                commits_examined=analysis.diagnostics.commits_examined,
                commits_used=analysis.diagnostics.commits_used,
                commits_excluded_large=analysis.diagnostics.commits_excluded_large,
                candidate_pairs=analysis.diagnostics.candidate_pairs,
                pairs_after_filtering=len(pairs),
            ),
        )

    def metrics(self, repository_id: UUID) -> GraphMetrics:
        _, state = self._repository(repository_id)
        nodes, edges = self._all(repository_id)
        file_nodes = [item for item in nodes if item.node_type == "file"]
        symbol_nodes = [item for item in nodes if item.node_type in SYMBOL_TYPES]

        def metric(item: DependencyNode, name: str) -> float:
            return float((item.metrics_json or {}).get(name, 0))

        top_in = sorted(nodes, key=lambda item: (-metric(item, "fan_in"), item.name))[:10]
        top_out = sorted(nodes, key=lambda item: (-metric(item, "fan_out"), item.name))[:10]
        hotspots = sorted(file_nodes, key=lambda item: (-metric(item, "hotspot_score"), item.name))[
            :10
        ]
        edge_counts = Counter(item.edge_type for item in edges)
        node_by_id = {item.id: item for item in nodes}
        relationship_levels: Counter[str] = Counter()
        for edge in edges:
            if edge.edge_type not in STATIC_TYPES:
                continue
            source = node_by_id[edge.source_node_id]
            target = node_by_id[edge.target_node_id]
            source_level = source.node_type if source.node_type in {"file", "module"} else "symbol"
            target_level = target.node_type if target.node_type in {"file", "module"} else "symbol"
            level = source_level if source_level == target_level else "cross_level"
            relationship_levels[level] += 1
        scores = [metric(item, "hotspot_score") for item in file_nodes]
        hotspot_tie_count = max(Counter(scores).values(), default=0)
        return GraphMetrics(
            nodes=len(nodes),
            edges=len(edges),
            files=len(file_nodes),
            symbols=len(symbol_nodes),
            modules=sum(item.node_type == "module" for item in nodes),
            external_dependencies=sum(item.node_type == "external_package" for item in nodes),
            cycles=state.cycles,
            dependency_relationships=sum(edge_counts[kind] for kind in STATIC_TYPES),
            edge_counts=dict(sorted(edge_counts.items())),
            relationship_levels=dict(sorted(relationship_levels.items())),
            average_fan_in=round(
                sum(metric(item, "fan_in") for item in nodes) / max(1, len(nodes)), 3
            ),
            average_fan_out=round(
                sum(metric(item, "fan_out") for item in nodes) / max(1, len(nodes)), 3
            ),
            top_fan_in=[self._node(item) for item in top_in],
            top_fan_out=[self._node(item) for item in top_out],
            top_hotspots=[self._node(item) for item in hotspots],
            hotspot_tie_count=hotspot_tie_count,
            hotspot_formula=GraphMetricsService.HOTSPOT_FORMULA,
            normalization_note=(
                "Change frequency uses min-max normalization per graph level; equal positive "
                "values receive the neutral score 0.5 and all-zero values receive 0."
            ),
        )

    def architecture(self, repository_id: UUID) -> ArchitectureResponse:
        repository, state = self._repository(repository_id)
        components = list(
            self.session.scalars(
                select(ArchitectureComponent)
                .where(ArchitectureComponent.repository_id == repository_id)
                .order_by(ArchitectureComponent.path)
            )
        )
        count_rows = self.session.execute(
            select(ComponentMember.component_id, func.count(ComponentMember.id))
            .join(
                ArchitectureComponent,
                ArchitectureComponent.id == ComponentMember.component_id,
            )
            .where(ArchitectureComponent.repository_id == repository_id)
            .group_by(ComponentMember.component_id)
        ).all()
        counts: dict[UUID, int] = {component_id: int(count) for component_id, count in count_rows}
        _nodes, edges = self._all(repository_id)
        member_rows = self.session.execute(
            select(ComponentMember.node_id, ComponentMember.component_id)
            .join(
                ArchitectureComponent,
                ArchitectureComponent.id == ComponentMember.component_id,
            )
            .where(ArchitectureComponent.repository_id == repository_id)
        ).all()
        component_by_node: dict[UUID, UUID] = {
            node_id: component_id for node_id, component_id in member_rows
        }
        dependencies: Counter[tuple[UUID, UUID]] = Counter()
        for edge in edges:
            if edge.edge_type != "DEPENDS_ON":
                continue
            source = component_by_node.get(edge.source_node_id)
            target = component_by_node.get(edge.target_node_id)
            if source and target and source != target:
                dependencies[(source, target)] += 1
        layers = Counter(item.layer or "unknown" for item in components)
        return ArchitectureResponse(
            components=[
                ArchitectureComponentRead(
                    id=item.id,
                    name=item.name,
                    path=item.path,
                    component_type=item.component_type,
                    layer=item.layer,
                    confidence=item.confidence,
                    node_count=counts.get(item.id, 0),
                )
                for item in components
            ],
            component_dependencies=[
                ComponentDependency(
                    source_component_id=source, target_component_id=target, weight=weight
                )
                for (source, target), weight in sorted(
                    dependencies.items(), key=lambda item: str(item[0])
                )
            ],
            layers=dict(layers),
            metrics=self.metrics(repository_id),
            graph_stale=state.last_indexed_sha != repository.head_sha,
        )

    def path(self, repository_id: UUID, source_id: UUID, target_id: UUID) -> DependencyPathResponse:
        self._repository(repository_id)
        nodes, edges = self._all(repository_id)
        by_id = {item.id: item for item in nodes}
        if source_id not in by_id or target_id not in by_id:
            raise IngestionError("GRAPH_NODE_NOT_FOUND", "Graph node not found.", 404)
        static = [item for item in edges if item.edge_type in STATIC_TYPES]
        graph: nx.DiGraph[UUID] = nx.DiGraph()
        graph.add_edges_from((item.source_node_id, item.target_node_id) for item in static)
        try:
            ids = nx.shortest_path(graph, source_id, target_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return DependencyPathResponse(found=False, path=[], edges=[], length=None)
        if len(ids) - 1 > self.settings.max_graph_depth:
            raise IngestionError(
                "GRAPH_DEPTH_LIMIT", "Dependency path exceeds the traversal limit.", 422
            )
        by_pair = {(item.source_node_id, item.target_node_id): item for item in static}
        return DependencyPathResponse(
            found=True,
            path=[self._node(by_id[item]) for item in ids],
            edges=[
                self._edge(by_pair[(source, target)])
                for source, target in zip(ids, ids[1:], strict=False)
            ],
            length=len(ids) - 1,
        )

    def impact(
        self,
        repository_id: UUID,
        file_id: UUID | None,
        symbol_id: UUID | None,
        lineage_id: UUID | None,
        depth: int,
        include_coupling: bool,
    ) -> ImpactResponse:
        self._repository(repository_id)
        if sum(value is not None for value in (file_id, symbol_id, lineage_id)) != 1:
            raise IngestionError(
                "IMPACT_TARGET_NOT_FOUND",
                "Provide exactly one file, symbol, or lineage target.",
                422,
            )
        query = select(DependencyNode).where(DependencyNode.repository_id == repository_id)
        if file_id:
            query = query.where(
                DependencyNode.node_type == "file", DependencyNode.file_id == file_id
            )
        elif symbol_id:
            query = query.where(DependencyNode.symbol_id == symbol_id)
        else:
            query = query.where(
                DependencyNode.metadata_json["lineage_id"].astext == str(lineage_id)
            )
        target = self.session.scalar(query.limit(1))
        if target is None:
            raise IngestionError("IMPACT_TARGET_NOT_FOUND", "Impact target was not found.", 404)
        nodes, edges = self._all(repository_id)
        by_id = {item.id: item for item in nodes}
        static = [item for item in edges if item.edge_type in STATIC_TYPES]
        graph: nx.DiGraph[UUID] = nx.DiGraph()
        graph.add_nodes_from(by_id)
        graph.add_edges_from((item.source_node_id, item.target_node_id) for item in static)
        by_pair = {(item.source_node_id, item.target_node_id): item for item in static}
        dependencies = [by_id[node] for node in graph.successors(target.id)]
        dependents = [by_id[node] for node in graph.predecessors(target.id)]
        paths = ImpactAnalysisService.dependent_paths(
            graph, target.id, min(depth, self.settings.max_graph_depth)
        )
        direct_ids = {item.id for item in dependents}
        transitive = [
            by_id[node] for node, path in paths if node not in direct_ids and len(path) > 2
        ]
        callers = [
            by_id[edge.source_node_id]
            for edge in static
            if edge.edge_type == "CALLS" and edge.target_node_id == target.id
        ]
        callees = [
            by_id[edge.target_node_id]
            for edge in static
            if edge.edge_type == "CALLS" and edge.source_node_id == target.id
        ]
        coupled: list[DependencyNode] = []
        if include_coupling:
            for edge in edges:
                if edge.edge_type != "CO_CHANGES_WITH":
                    continue
                if edge.source_node_id == target.id:
                    coupled.append(by_id[edge.target_node_id])
                elif edge.target_node_id == target.id:
                    coupled.append(by_id[edge.source_node_id])
        impact_paths: list[ImpactPath] = []
        for _, ids in paths[: self.settings.max_graph_response_nodes]:
            path_edges = [
                by_pair[(source, target)] for source, target in zip(ids, ids[1:], strict=False)
            ]
            confidence = min((edge.confidence for edge in path_edges), default=1.0)
            impact_paths.append(
                ImpactPath(
                    distance=len(ids) - 1,
                    nodes=[self._node(by_id[item]) for item in ids],
                    edges=[self._edge(item) for item in path_edges],
                    confidence=confidence,
                )
            )
        return ImpactResponse(
            target=self._node(target),
            direct_dependencies=[self._node(item) for item in dependencies],
            direct_dependents=[self._node(item) for item in dependents],
            transitive_dependents=[self._node(item) for item in transitive],
            callers=[self._node(item) for item in callers],
            callees=[self._node(item) for item in callees],
            change_coupled_nodes=[self._node(item) for item in coupled],
            paths=impact_paths,
            metrics=target.metrics_json or {},
        )
