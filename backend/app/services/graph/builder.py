import logging
import re
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid5

import networkx as nx
from sqlalchemy import delete, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    ArchitectureComponent,
    CodeImport,
    CodeSymbol,
    ComponentMember,
    DependencyEdge,
    DependencyNode,
    GraphIndexState,
    JobStatus,
    Repository,
    RepositoryFile,
    RepositoryStatus,
)
from app.services.git import GitService
from app.services.graph.coupling import ChangeCouplingService
from app.services.graph.cycles import CycleDetectionService
from app.services.graph.metrics import GraphMetricsService
from app.services.graph.models import ReferenceCandidate
from app.services.graph.resolver import DependencyResolver
from app.services.graph.static_references import extract_static_references

logger = logging.getLogger("ctm")
CALL_PATTERN = re.compile(r"\b([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\s*\(")
CALL_KEYWORDS = {
    "if",
    "for",
    "while",
    "switch",
    "catch",
    "return",
    "new",
    "def",
    "class",
    "function",
    "sizeof",
    "typeof",
}
STATIC_EDGE_TYPES = {"IMPORTS", "REFERENCES", "CALLS", "INHERITS", "IMPLEMENTS"}


class GraphBuilder:
    def __init__(self, settings: Settings | None = None, git: GitService | None = None) -> None:
        self.settings = settings or get_settings()
        self.git = git or GitService(self.settings)
        self.started = 0.0
        self.limited = False

    def _check_time(self) -> None:
        if time.monotonic() - self.started > self.settings.max_graph_build_time_seconds:
            raise IngestionError(
                "GRAPH_INDEX_FAILED",
                "Dependency graph indexing exceeded its configured time limit.",
            )

    @staticmethod
    def _module(path: str) -> str:
        parent = PurePosixPath(path).parent.as_posix()
        return parent if parent != "." else "root"

    @staticmethod
    def _external_name(module: str) -> str:
        value = module.lstrip(".").replace("\\", "/")
        if value.startswith("@"):
            return "/".join(value.split("/")[:2])
        return re.split(r"[/.]", value, maxsplit=1)[0] or value

    @staticmethod
    def _layer(path: str) -> tuple[str, float]:
        raw_parts = [part.lower() for part in PurePosixPath(path).parts]
        parts = set(raw_parts)
        for part in raw_parts:
            parts.update(token for token in re.split(r"[^a-z0-9]+", part) if token)
            stem = PurePosixPath(part).stem
            parts.update(token for token in re.split(r"(?=[A-Z])|[^a-zA-Z0-9]+", stem) if token)
        rules = [
            ({"ui", "views", "pages", "components", "frontend"}, "presentation"),
            ({"api", "routes", "endpoints"}, "api"),
            ({"controller", "controllers"}, "controller"),
            ({"service", "services"}, "service"),
            ({"domain"}, "domain"),
            ({"repository", "repositories", "dao"}, "repository"),
            ({"database", "db", "model", "models", "migrations"}, "database"),
            ({"infrastructure", "infra"}, "infrastructure"),
            ({"util", "utils", "helpers"}, "utility"),
            ({"test", "tests", "spec", "specs"}, "test"),
        ]
        for names, layer in rules:
            if parts & names:
                return layer, 0.8
        return "unknown", 0.0

    @staticmethod
    def _inheritance_candidates(symbol: CodeSymbol) -> list[tuple[str, str]]:
        if symbol.kind not in {"class", "interface", "trait", "struct"} or not symbol.signature:
            return []
        signature = symbol.signature
        result: list[tuple[str, str]] = []
        python = re.search(r"\bclass\s+\w+\s*\(([^)]+)\)", signature)
        if python:
            result.extend(
                (name.strip().split("[")[0], "INHERITS") for name in python.group(1).split(",")
            )
        extends = re.search(r"\bextends\s+([\w.$]+)", signature)
        if extends:
            result.append((extends.group(1), "INHERITS"))
        implements = re.search(r"\bimplements\s+([\w.$,\s]+)", signature)
        if implements:
            result.extend((name.strip(), "IMPLEMENTS") for name in implements.group(1).split(","))
        return [(name, kind) for name, kind in result if name]

    @staticmethod
    def _symbol_qualified_names(
        symbols: list[CodeSymbol], path_by_file: dict[UUID, str]
    ) -> dict[UUID, str]:
        """Return deterministic, unique graph names for indexed symbols.

        Some parsers intentionally emit a short qualified name for object-literal
        methods. A file can therefore contain several distinct symbols named
        ``list`` or ``create``. Dependency nodes have a repository/type/name
        uniqueness constraint, so those symbols need a source-location suffix.
        Unique symbols retain their original name to keep existing node IDs stable.
        """
        bases = {
            symbol.id: f"{path_by_file[symbol.file_id]}::{symbol.qualified_name}"
            for symbol in symbols
        }
        counts = Counter((symbol.kind, bases[symbol.id]) for symbol in symbols)
        occurrences: dict[tuple[str, str], int] = defaultdict(int)
        result: dict[UUID, str] = {}
        for symbol in symbols:
            base = bases[symbol.id]
            key = (symbol.kind, base)
            if counts[key] == 1:
                result[symbol.id] = base
                continue
            occurrences[key] += 1
            result[symbol.id] = (
                f"{base}@{symbol.start_line}:{symbol.start_column}#{occurrences[key]}"
            )
        return result

    def run(self, session: Session, repository: Repository, job: AnalysisJob) -> None:
        if repository.status != RepositoryStatus.ready or not repository.head_sha:
            raise IngestionError("CODE_INDEX_NOT_READY", "Build the current code index first.", 409)
        state = session.get(GraphIndexState, repository.id)
        if state is None:
            state = GraphIndexState(repository_id=repository.id)
            session.add(state)
        state.status = "indexing"
        state.current_step = "loading_current_code_index"
        state.progress = 5
        state.error = None
        state.graph_limited = False
        state.started_at = datetime.now(UTC)
        state.completed_at = None
        state.job_id = job.id
        job.current_step = state.current_step
        job.progress = state.progress
        session.commit()

        self.started = time.monotonic()
        files = list(
            session.scalars(
                select(RepositoryFile)
                .where(RepositoryFile.repository_id == repository.id)
                .order_by(RepositoryFile.path)
            )
        )
        symbols = list(
            session.scalars(
                select(CodeSymbol)
                .where(CodeSymbol.repository_id == repository.id)
                .order_by(CodeSymbol.file_id, CodeSymbol.start_line, CodeSymbol.id)
            )
        )
        imports = list(
            session.scalars(select(CodeImport).where(CodeImport.repository_id == repository.id))
        )
        module_names = sorted({self._module(item.path) for item in files})
        minimum_nodes = 1 + len(files) + len(module_names)
        if minimum_nodes > self.settings.max_graph_nodes:
            raise IngestionError(
                "GRAPH_TOO_LARGE",
                "The repository file graph exceeds the configured node limit.",
                413,
            )

        session.execute(
            delete(ArchitectureComponent).where(
                ArchitectureComponent.repository_id == repository.id
            )
        )
        session.execute(delete(DependencyNode).where(DependencyNode.repository_id == repository.id))
        session.flush()

        nodes: list[DependencyNode] = []

        def node(
            node_type: str,
            name: str,
            qualified_name: str,
            *,
            file_id: UUID | None = None,
            symbol_id: UUID | None = None,
            external_name: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> DependencyNode | None:
            if len(nodes) >= self.settings.max_graph_nodes:
                self.limited = True
                return None
            created = DependencyNode(
                id=uuid5(repository.id, f"node:{node_type}:{qualified_name}"),
                repository_id=repository.id,
                node_type=node_type,
                file_id=file_id,
                symbol_id=symbol_id,
                external_name=external_name,
                name=name,
                qualified_name=qualified_name,
                metadata_json=metadata,
            )
            nodes.append(created)
            return created

        repository_node = node("repository", repository.full_name, repository.full_name)
        assert repository_node is not None
        module_nodes = {
            name: node(
                "module",
                PurePosixPath(name).name if name != "root" else "root",
                name,
                metadata={"path": name},
            )
            for name in module_names
        }
        file_nodes = {
            item.id: node(
                "file",
                item.filename,
                item.path,
                file_id=item.id,
                metadata={"path": item.path, "language": item.language, "blob_sha": item.blob_sha},
            )
            for item in files
        }
        assert all(file_nodes.values())
        symbol_nodes: dict[UUID, DependencyNode] = {}
        path_by_file = {file.id: file.path for file in files}
        symbol_qualified_names = self._symbol_qualified_names(symbols, path_by_file)
        for symbol in symbols:
            created = node(
                symbol.kind,
                symbol.name,
                symbol_qualified_names[symbol.id],
                file_id=symbol.file_id,
                symbol_id=symbol.id,
                metadata={"lineage_id": str(symbol.lineage_id) if symbol.lineage_id else None},
            )
            if created:
                symbol_nodes[symbol.id] = created
        session.add_all(nodes)
        session.flush()

        edge_values: dict[tuple[UUID, UUID, str], dict[str, Any]] = {}

        def edge(
            source: DependencyNode | None,
            target: DependencyNode | None,
            edge_type: str,
            confidence: float,
            resolution_type: str,
            evidence: dict[str, Any],
            weight: float = 1.0,
        ) -> None:
            if source is None or target is None or source.id == target.id:
                return
            key = (source.id, target.id, edge_type)
            current = edge_values.get(key)
            if current:
                current["weight"] += weight
                current["confidence"] = max(current["confidence"], confidence)
                values = current["metadata"].setdefault("evidence", [])
                if len(values) < 20:
                    values.append(evidence)
                return
            if len(edge_values) >= self.settings.max_graph_edges:
                self.limited = True
                return
            edge_values[key] = {
                "source": source,
                "target": target,
                "edge_type": edge_type,
                "weight": weight,
                "confidence": confidence,
                "resolution_type": resolution_type,
                "metadata": {"evidence": [evidence]},
            }

        for module_name, module_node in module_nodes.items():
            edge(repository_node, module_node, "CONTAINS", 1.0, "exact", {"path": module_name})
        for file in files:
            edge(
                module_nodes[self._module(file.path)],
                file_nodes[file.id],
                "CONTAINS",
                1.0,
                "exact",
                {"path": file.path},
            )
        for symbol in symbols:
            edge(
                file_nodes[symbol.file_id],
                symbol_nodes.get(symbol.id),
                "CONTAINS",
                1.0,
                "exact",
                {"lines": [symbol.start_line, symbol.end_line]},
            )

        state.current_step = "resolving_imports"
        state.progress = 30
        job.current_step = state.current_step
        job.progress = state.progress
        files_by_id = {item.id: item for item in files}
        files_by_path = {item.path: item for item in files}
        repo_path = self.git.storage.path(repository.id)
        source_cache: dict[UUID, str] = {}

        def source_for(file: RepositoryFile) -> str:
            if file.id not in source_cache:
                source_cache[file.id] = self.git.get_blob(
                    repo_path, file.blob_sha, file.size_bytes
                ).decode("utf-8", "replace")
            return source_cache[file.id]

        external_nodes: dict[str, DependencyNode | None] = {}
        for item in imports:
            source = file_nodes[item.source_file_id]
            if item.target_file_id and item.target_file_id in file_nodes:
                edge(
                    source,
                    file_nodes[item.target_file_id],
                    "IMPORTS",
                    1.0,
                    "exact",
                    {"module": item.module, "imported_name": item.imported_name},
                )
            elif not item.module.startswith("."):
                external_name = self._external_name(item.module)
                if external_name not in external_nodes:
                    external_nodes[external_name] = node(
                        "external_package",
                        external_name,
                        external_name,
                        external_name=external_name,
                    )
                    if external_nodes[external_name]:
                        session.add(external_nodes[external_name])
                edge(
                    source,
                    external_nodes[external_name],
                    "IMPORTS_EXTERNAL",
                    1.0,
                    "exact",
                    {"module": item.module},
                )

        for file in files:
            if file.is_binary or file.size_bytes > self.settings.max_source_file_size_bytes:
                continue
            for reference in extract_static_references(
                file.path, source_for(file), set(files_by_path)
            ):
                target_file_record = files_by_path[reference.target_path]
                edge(
                    file_nodes[file.id],
                    file_nodes[target_file_record.id],
                    reference.edge_type,
                    1.0,
                    "exact_local_path",
                    {
                        "reference": reference.raw_reference,
                        "reference_kind": reference.reference_kind,
                        "line": reference.line,
                    },
                )

        self._check_time()
        state.current_step = "resolving_symbol_references"
        state.progress = 50
        job.current_step = state.current_step
        job.progress = state.progress
        resolver = DependencyResolver(
            symbols, files_by_id, imports, self.settings.max_call_resolution_candidates
        )
        symbols_by_file: dict[UUID, list[CodeSymbol]] = defaultdict(list)
        for symbol in symbols:
            symbols_by_file[symbol.file_id].append(symbol)
        for file in files:
            if (
                file.parse_status != "parsed"
                or file.is_binary
                or file.size_bytes > self.settings.max_source_file_size_bytes
            ):
                continue
            source_text = source_for(file)
            lines = source_text.splitlines()
            for source_symbol in symbols_by_file[file.id]:
                if source_symbol.id not in symbol_nodes:
                    continue
                body = "\n".join(lines[source_symbol.start_line - 1 : source_symbol.end_line])
                for match in CALL_PATTERN.finditer(body):
                    qualified = match.group(1)
                    name = qualified.rsplit(".", 1)[-1]
                    if name in CALL_KEYWORDS or name == source_symbol.name and match.start() < 160:
                        continue
                    line = source_symbol.start_line + body[: match.start()].count("\n")
                    candidate = ReferenceCandidate(source_symbol.id, name, qualified, line, "call")
                    resolved = resolver.resolve(source_symbol, candidate)
                    if resolved and resolved.target_symbol_id != source_symbol.id:
                        edge(
                            symbol_nodes[source_symbol.id],
                            symbol_nodes.get(resolved.target_symbol_id),
                            "CALLS",
                            resolved.confidence,
                            resolved.resolution_type,
                            {"reference": qualified, "line": line},
                        )
                for base_name, kind in self._inheritance_candidates(source_symbol):
                    simple = base_name.rsplit(".", 1)[-1]
                    candidate = ReferenceCandidate(
                        source_symbol.id, simple, base_name, source_symbol.start_line, "inheritance"
                    )
                    resolved = resolver.resolve(source_symbol, candidate)
                    if resolved:
                        edge(
                            symbol_nodes[source_symbol.id],
                            symbol_nodes.get(resolved.target_symbol_id),
                            kind,
                            resolved.confidence,
                            resolved.resolution_type,
                            {"reference": base_name, "line": source_symbol.start_line},
                        )
            self._check_time()

        state.current_step = "aggregating_dependencies"
        state.progress = 65
        job.current_step = state.current_step
        job.progress = state.progress
        node_by_id = {item.id: item for item in nodes}
        file_support: dict[tuple[UUID, UUID], list[str]] = defaultdict(list)
        for source_id, target_id, edge_type in list(edge_values):
            if edge_type not in STATIC_EDGE_TYPES:
                continue
            source_file = node_by_id[source_id].file_id
            target_file = node_by_id[target_id].file_id
            if source_file and target_file and source_file != target_file:
                file_support[(source_file, target_file)].append(edge_type)
        for (source_file, target_file), evidence_types in file_support.items():
            edge(
                file_nodes[source_file],
                file_nodes[target_file],
                "DEPENDS_ON",
                1.0 if "IMPORTS" in evidence_types else 0.85,
                "aggregate",
                {"relationships": sorted(set(evidence_types))},
                float(len(evidence_types)),
            )
        module_support: dict[tuple[str, str], int] = defaultdict(int)
        for source_file, target_file in file_support:
            source_module = self._module(files_by_id[source_file].path)
            target_module = self._module(files_by_id[target_file].path)
            if source_module != target_module:
                module_support[(source_module, target_module)] += 1
        for (source_module, target_module), weight in module_support.items():
            edge(
                module_nodes[source_module],
                module_nodes[target_module],
                "DEPENDS_ON",
                1.0,
                "aggregate",
                {"file_dependencies": weight},
                float(weight),
            )

        state.current_step = "calculating_change_coupling"
        state.progress = 75
        job.current_step = state.current_step
        job.progress = state.progress
        path_ids = {item.path: item.id for item in files}
        coupling_analysis = ChangeCouplingService.calculate(
            session,
            repository.id,
            path_ids,
            self.settings.max_files_per_commit_for_coupling,
        )
        for source_file, target_file, count, score in coupling_analysis.pairs:
            edge(
                file_nodes[source_file],
                file_nodes[target_file],
                "CO_CHANGES_WITH",
                score,
                "git_history",
                {"co_change_count": count, "coupling_score": round(score, 6)},
                float(count),
            )

        edge_models = [
            DependencyEdge(
                id=uuid5(
                    repository.id,
                    (f"edge:{value['source'].id}:{value['target'].id}:{value['edge_type']}"),
                ),
                repository_id=repository.id,
                source_node_id=value["source"].id,
                target_node_id=value["target"].id,
                edge_type=value["edge_type"],
                weight=value["weight"],
                confidence=value["confidence"],
                resolution_type=value["resolution_type"],
                metadata_json=value["metadata"],
            )
            for value in edge_values.values()
        ]
        session.add_all(edge_models)
        session.flush()

        state.current_step = "detecting_components_and_metrics"
        state.progress = 88
        job.current_step = state.current_step
        job.progress = state.progress
        components: dict[str, ArchitectureComponent] = {}
        for file in files:
            top = (
                PurePosixPath(file.path).parts[0]
                if len(PurePosixPath(file.path).parts) > 1
                else "root"
            )
            if top not in components:
                layer, confidence = self._layer(top)
                components[top] = ArchitectureComponent(
                    id=uuid5(repository.id, f"component:{top}"),
                    repository_id=repository.id,
                    name=top,
                    path=top,
                    component_type="directory",
                    layer=layer,
                    confidence=confidence,
                    metadata_json={"grouping": "top_level_directory"},
                )
                session.add(components[top])
        session.flush()
        for file in files:
            top = (
                PurePosixPath(file.path).parts[0]
                if len(PurePosixPath(file.path).parts) > 1
                else "root"
            )
            member_nodes = [
                file_nodes[file.id],
                *[symbol_nodes.get(s.id) for s in symbols_by_file[file.id]],
            ]
            session.add_all(
                ComponentMember(component_id=components[top].id, node_id=item.id)
                for item in member_nodes
                if item is not None
            )
        GraphMetricsService.apply(session, repository.id, nodes)

        file_graph: nx.DiGraph[UUID] = nx.DiGraph()
        module_graph: nx.DiGraph[UUID] = nx.DiGraph()
        for edge_model in edge_models:
            edge_source_node = node_by_id[edge_model.source_node_id]
            edge_target_node = node_by_id[edge_model.target_node_id]
            if (
                edge_model.edge_type == "DEPENDS_ON"
                and edge_source_node.node_type == "file"
                and edge_target_node.node_type == "file"
            ):
                file_graph.add_edge(edge_source_node.id, edge_target_node.id)
            if (
                edge_model.edge_type == "DEPENDS_ON"
                and edge_source_node.node_type == "module"
                and edge_target_node.node_type == "module"
            ):
                module_graph.add_edge(edge_source_node.id, edge_target_node.id)
        cycle_count = len(CycleDetectionService.find(file_graph)) + len(
            CycleDetectionService.find(module_graph)
        )
        self._check_time()
        state.nodes = len(nodes)
        state.edges = len(edge_models)
        state.cycles = cycle_count
        state.components = len(components)
        state.last_indexed_sha = repository.head_sha
        state.graph_limited = self.limited
        state.status = "limited" if self.limited else "ready"
        state.progress = None
        state.current_step = "ready"
        state.completed_at = datetime.now(UTC)
        session.commit()


def index_dependency_graph(engine: Engine, repository_id: UUID, job_id: UUID) -> None:
    lock_key = int.from_bytes(repository_id.bytes[:8], signed=True)
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        )
        lock_connection.commit()
        if not acquired:
            return
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = session.get(AnalysisJob, job_id)
                repository = session.get(Repository, repository_id)
                if job is None or repository is None or job.repository_id != repository_id:
                    return
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    GraphBuilder().run(session, repository, job)
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.info(
                        "dependency_graph_completed", extra={"repository_id": repository_id}
                    )
                except Exception as error:
                    session.rollback()
                    state = session.get(GraphIndexState, repository_id)
                    if state is None:
                        state = GraphIndexState(repository_id=repository_id)
                        session.add(state)
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "Dependency graph indexing failed. Retry the graph index."
                    )
                    state.status = "failed"
                    state.progress = None
                    state.current_step = None
                    state.error = message
                    state.completed_at = datetime.now(UTC)
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.progress = None
                    job.completed_at = datetime.now(UTC)
                    session.commit()
                    logger.exception(
                        "dependency_graph_failed", extra={"repository_id": repository_id}
                    )
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
