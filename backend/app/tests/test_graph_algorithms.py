from types import SimpleNamespace
from uuid import uuid4

import networkx as nx

from app.db.models import CodeImport, CodeSymbol, RepositoryFile
from app.services.graph.builder import GraphBuilder
from app.services.graph.cycles import CycleDetectionService
from app.services.graph.impact import ImpactAnalysisService
from app.services.graph.metrics import GraphMetricsService
from app.services.graph.models import ReferenceCandidate
from app.services.graph.resolver import DependencyResolver
from app.services.graph.static_references import (
    extract_static_references,
    resolve_local_reference,
)


def file(path: str) -> RepositoryFile:
    return RepositoryFile(
        id=uuid4(),
        repository_id=uuid4(),
        path=path,
        filename=path.rsplit("/", 1)[-1],
        extension=".py",
        language="Python",
        blob_sha="a" * 40,
        size_bytes=1,
        parse_status="parsed",
        syntax_error_count=0,
        indexed_commit_sha="b" * 40,
    )


def symbol(source_file: RepositoryFile, name: str, qualified: str | None = None) -> CodeSymbol:
    return CodeSymbol(
        id=uuid4(),
        repository_id=source_file.repository_id,
        file_id=source_file.id,
        name=name,
        qualified_name=qualified or name,
        kind="function",
        start_line=1,
        end_line=2,
        start_column=1,
        end_column=1,
    )


def test_resolver_priorities_and_ambiguous_rejection():
    controller = file("controllers/user_controller.py")
    service = file("services/user_service.py")
    other = file("other/user_service.py")
    caller = symbol(controller, "run")
    imported_target = symbol(service, "get_user", "UserService.get_user")
    duplicate = symbol(other, "get_user", "OtherService.get_user")
    imported = CodeImport(
        repository_id=controller.repository_id,
        source_file_id=controller.id,
        target_file_id=service.id,
        module="services.user_service",
        imported_name="get_user",
        import_type="from",
        resolved=True,
    )
    resolver = DependencyResolver(
        [caller, imported_target, duplicate],
        {item.id: item for item in [controller, service, other]},
        [imported],
        20,
    )
    resolved = resolver.resolve(
        caller, ReferenceCandidate(caller.id, "get_user", "get_user", 2, "call")
    )
    assert resolved is not None
    assert resolved.target_symbol_id == imported_target.id
    assert resolved.resolution_type == "imported_symbol"

    ambiguous = DependencyResolver(
        [caller, imported_target, duplicate],
        {item.id: item for item in [controller, service, other]},
        [],
        20,
    )
    assert (
        ambiguous.resolve(caller, ReferenceCandidate(caller.id, "get_user", "get_user", 2, "call"))
        is None
    )


def test_cycles_reverse_impact_and_dependency_path():
    a, b, c, leaf = (uuid4() for _ in range(4))
    graph: nx.DiGraph = nx.DiGraph([(a, b), (b, c), (c, a), (leaf, a)])
    cycles = CycleDetectionService.find(graph)
    assert len(cycles) == 1
    assert set(cycles[0].members) == {a, b, c}
    impacts = ImpactAnalysisService.dependent_paths(graph, b, 3)
    assert any(node == leaf and path[-1] == b for node, path in impacts)
    assert nx.shortest_path(graph, leaf, b) == [leaf, a, b]


def test_grouping_layers_inheritance_and_external_names():
    builder = GraphBuilder.__new__(GraphBuilder)
    assert builder._module("controllers/user.py") == "controllers"
    assert builder._module("main.py") == "root"
    assert builder._external_name("@scope/package/client") == "@scope/package"
    assert builder._external_name("sqlalchemy.orm") == "sqlalchemy"
    assert builder._layer("src/services") == ("service", 0.8)
    inherited = SimpleNamespace(
        kind="class", signature="class AdminService(UserService):", name="AdminService"
    )
    assert builder._inheritance_candidates(inherited) == [("UserService", "INHERITS")]


def test_local_html_and_css_references_are_safe_and_exact():
    paths = {
        "web/index.html",
        "assets/site.css",
        "assets/theme.css",
        "scripts/app.js",
    }
    html = """<link rel="stylesheet" href="../assets/site.css?v=2">
<script src="/scripts/app.js#main"></script>
<script src="https://cdn.example.com/library.js"></script>
<script src="../../outside.js"></script>"""
    references = extract_static_references("web/index.html", html, paths)
    assert [(item.target_path, item.edge_type) for item in references] == [
        ("assets/site.css", "REFERENCES"),
        ("scripts/app.js", "REFERENCES"),
    ]
    css = '@import "theme.css"; @import url("https://cdn.example.com/reset.css");'
    assert [
        item.target_path for item in extract_static_references("assets/site.css", css, paths)
    ] == ["assets/theme.css"]
    assert resolve_local_reference("web/index.html", "../../../secret.css") is None
    assert resolve_local_reference("web/index.html", "javascript:alert(1)") is None


def test_traditional_javascript_does_not_invent_file_dependencies():
    paths = {"scripts/app.js", "scripts/helpers.js"}
    assert extract_static_references("scripts/app.js", "helpers();", paths) == []


def test_hotspot_normalization_handles_ties_and_weighted_components():
    first, second = uuid4(), uuid4()
    assert GraphMetricsService.normalize({first: 3, second: 3}) == {
        first: 0.5,
        second: 0.5,
    }
    assert GraphMetricsService.normalize({first: 0, second: 0}) == {
        first: 0.0,
        second: 0.0,
    }
    values = GraphMetricsService.normalize({first: 1, second: 4})
    assert values == {first: 0.0, second: 1.0}
    assert GraphMetricsService.hotspot_score(1.0, 1.0, 1.0) == 1.0
