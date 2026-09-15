import hashlib
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID, uuid5

import networkx as nx

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.parsers.models import ParsedImport
from app.parsers.registry import ParserRegistry
from app.services.architecture_history.models import (
    HistoricalEdge,
    HistoricalGraph,
    HistoricalNode,
)
from app.services.git import GitService, GitTreeEntry
from app.services.graph.builder import GraphBuilder
from app.services.graph.static_references import extract_static_references
from app.services.import_resolver import ImportResolver
from app.services.language_detector import LanguageDetector


class HistoricalArchitectureBuilder:
    """Build bounded module/component graphs from immutable Git objects."""

    def __init__(
        self,
        settings: Settings | None = None,
        git: GitService | None = None,
        registry: ParserRegistry | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.git = git or GitService(self.settings)
        self.registry = registry or ParserRegistry()
        self.detector = LanguageDetector()
        self.resolver = ImportResolver()
        self._parse_cache: dict[str, tuple[str | None, str, list[ParsedImport]]] = {}

    @staticmethod
    def module_path(path: str) -> str:
        value = PurePosixPath(path)
        if value.name.startswith("__init__."):
            return value.parent.as_posix() if value.parent.as_posix() != "." else "root"
        without_suffix = value.with_suffix("").as_posix()
        return without_suffix or "root"

    @staticmethod
    def component_path(path: str) -> str:
        parts = PurePosixPath(path).parts
        if len(parts) <= 1:
            return "root"
        if parts[0].lower() in {"src", "app", "lib"} and len(parts) > 2:
            return "/".join(parts[:2])
        return parts[0]

    def _read(
        self, repo_path: Path, entry: GitTreeEntry
    ) -> tuple[str | None, str, list[ParsedImport]] | None:
        cached = self._parse_cache.get(entry.blob_sha)
        if cached is not None:
            return cached
        detection = self.detector.detect(entry.path)
        if (
            detection.excluded
            or detection.binary_by_extension
            or entry.object_type != "blob"
            or entry.mode == "120000"
            or entry.size_bytes > self.settings.max_source_file_size_bytes
        ):
            return None
        content = self.git.get_blob(repo_path, entry.blob_sha, entry.size_bytes)
        if self.detector.is_binary(content):
            return None
        source = content.decode("utf-8", "replace")
        imports: list[ParsedImport] = []
        parser = self.registry.get(detection.language)
        if parser is not None:
            try:
                parsed = parser.parse(content, self.settings.max_parse_time_per_file_seconds)
                if parsed.parse_success:
                    imports = parsed.imports
            except Exception:
                imports = []
        result = (detection.language, source, imports)
        self._parse_cache[entry.blob_sha] = result
        return result

    def build(self, repository_id: UUID, repo_path: Path, commit_sha: str) -> HistoricalGraph:
        entries = self.git.list_tracked_files(repo_path, commit_sha)
        source_entries = [
            entry
            for entry in entries
            if not self.detector.detect(entry.path).excluded
            and (
                self.registry.get(self.detector.detect(entry.path).language) is not None
                or PurePosixPath(entry.path).suffix.lower() in {".html", ".htm", ".css"}
            )
        ]
        modules = {entry.path: self.module_path(entry.path) for entry in source_entries}
        module_paths = sorted(set(modules.values()))
        components = sorted({self.component_path(path) for path in modules})
        if len(module_paths) + len(components) > self.settings.max_historical_graph_nodes:
            raise IngestionError(
                "ARCHITECTURE_HISTORY_LIMIT_REACHED",
                "Historical architecture exceeds the configured node limit.",
                413,
            )

        nodes: dict[str, HistoricalNode] = {}
        for module in module_paths:
            source_files = sorted(path for path, value in modules.items() if value == module)
            representative = source_files[0]
            layer, confidence = GraphBuilder._layer(representative)
            key = f"module:{module}"
            nodes[key] = HistoricalNode(
                stable_key=key,
                node_type="module",
                name=PurePosixPath(module).name if module != "root" else "root",
                path=module,
                layer=layer,
                confidence=confidence,
                metadata={"source_files": source_files},
            )
        for component in components:
            layer, confidence = GraphBuilder._layer(component)
            key = f"component:{component}"
            nodes[key] = HistoricalNode(
                stable_key=key,
                node_type="component",
                name=PurePosixPath(component).name,
                path=component,
                layer=layer,
                confidence=confidence,
                component_type="directory",
            )

        file_ids = {
            path: uuid5(repository_id, f"historical-file:{path}") for path in modules
        }
        path_by_id = {value: path for path, value in file_ids.items()}
        repository_paths = set(modules)
        edge_evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        edge_confidence: dict[tuple[str, str], float] = {}
        for entry in source_entries:
            analyzed = self._read(repo_path, entry)
            if analyzed is None:
                continue
            language, source, imports = analyzed
            for item in imports:
                target_id = self.resolver.resolve(entry.path, item.module, language, file_ids)
                target_path = path_by_id.get(target_id) if target_id else None
                if not target_path or modules[target_path] == modules[entry.path]:
                    continue
                dependency_key = (
                    f"module:{modules[entry.path]}",
                    f"module:{modules[target_path]}",
                )
                edge_evidence[dependency_key].append(
                    {
                        "source_file": entry.path,
                        "target_file": target_path,
                        "reference": item.module,
                        "kind": item.import_type,
                    }
                )
                edge_confidence[dependency_key] = 1.0
            for reference in extract_static_references(entry.path, source, repository_paths):
                if modules[reference.target_path] == modules[entry.path]:
                    continue
                dependency_key = (
                    f"module:{modules[entry.path]}",
                    f"module:{modules[reference.target_path]}",
                )
                edge_evidence[dependency_key].append(
                    {
                        "source_file": entry.path,
                        "target_file": reference.target_path,
                        "reference": reference.raw_reference,
                        "kind": reference.reference_kind,
                    }
                )
                edge_confidence[dependency_key] = 1.0

        edges: list[HistoricalEdge] = []
        for (source, target), evidence in sorted(edge_evidence.items()):
            edges.append(
                HistoricalEdge(
                    source=source,
                    target=target,
                    weight=float(len(evidence)),
                    confidence=edge_confidence[(source, target)],
                    resolution_type="exact_static_reference",
                    metadata={"evidence": evidence[:20]},
                )
            )

        component_support: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
        for edge in edges:
            source_path = nodes[edge.source].path or "root"
            target_path = nodes[edge.target].path or "root"
            source_component = f"component:{self.component_path(source_path)}"
            target_component = f"component:{self.component_path(target_path)}"
            if source_component != target_component:
                component_support[(source_component, target_component)].append(
                    (edge.source, edge.target)
                )
        for (source, target), supporting in sorted(component_support.items()):
            edges.append(
                HistoricalEdge(
                    source=source,
                    target=target,
                    weight=float(len(supporting)),
                    confidence=1.0,
                    resolution_type="aggregate",
                    metadata={"module_dependencies": supporting[:20]},
                )
            )
        if len(edges) > self.settings.max_historical_graph_edges:
            raise IngestionError(
                "ARCHITECTURE_HISTORY_LIMIT_REACHED",
                "Historical architecture exceeds the configured edge limit.",
                413,
            )

        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(key for key, node in nodes.items() if node.node_type == "module")
        graph.add_edges_from(
            (edge.source, edge.target)
            for edge in edges
            if nodes[edge.source].node_type == nodes[edge.target].node_type == "module"
        )
        cycles: list[dict[str, Any]] = []
        for members in nx.strongly_connected_components(graph):
            if len(members) < 2:
                continue
            ordered = sorted(members)
            fingerprint = hashlib.sha256("\0".join(ordered).encode()).hexdigest()
            cycles.append({"fingerprint": fingerprint, "members": ordered})
        cycles.sort(key=lambda item: item["fingerprint"])

        incoming: dict[str, int] = defaultdict(int)
        outgoing: dict[str, int] = defaultdict(int)
        module_edges = [
            edge
            for edge in edges
            if nodes[edge.source].node_type == nodes[edge.target].node_type == "module"
        ]
        for edge in module_edges:
            outgoing[edge.source] += 1
            incoming[edge.target] += 1
        for key, node in nodes.items():
            node.metrics = {"fan_in": incoming[key], "fan_out": outgoing[key]}
        count = len(module_paths)
        density = len(module_edges) / (count * (count - 1)) if count > 1 else 0.0
        metrics = {
            "dependency_count": len(module_edges),
            "module_count": count,
            "component_count": len(components),
            "cycle_count": len(cycles),
            "average_fan_in": round(len(module_edges) / count, 6) if count else 0.0,
            "average_fan_out": round(len(module_edges) / count, 6) if count else 0.0,
            "maximum_fan_in": max(incoming.values(), default=0),
            "maximum_fan_out": max(outgoing.values(), default=0),
            "dependency_density": round(density, 6),
            "strongly_connected_component_count": len(cycles),
            "density_formula": "directed module dependencies / (modules * (modules - 1))",
        }
        return HistoricalGraph(list(nodes.values()), edges, cycles, metrics)
