import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.db.models import (
    AnalysisJob,
    Commit,
    DependencyEdge,
    DependencyNode,
    FileChange,
    JobStatus,
    Repository,
    RepositoryStatus,
)
from app.services.code_index import CodeIndexService
from app.services.git import GitService
from app.services.graph.builder import GraphBuilder
from app.services.graph.coupling import ChangeCouplingService
from app.services.graph.service import GraphService

pytestmark = pytest.mark.integration


@pytest.fixture
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration checks")
    schema = "ctm_graph_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema},public"})
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.attributes["version_table_schema"] = schema
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def test_graph_build_api_algorithms_and_idempotency(engine, tmp_path):
    storage = tmp_path / "storage"
    repository_id = uuid4()
    repository_path = storage / str(repository_id) / "repo"
    files = {
        "controllers/user_controller.py": """from services.user_service import get_user

def handle():
    return get_user()
""",
        "services/user_service.py": """from repositories.user_repository import find_user

class UserService:
    pass

class AdminService(UserService):
    pass

def get_user():
    return find_user()
""",
        "repositories/user_repository.py": """from models.user import User

def find_user():
    return User()
""",
        "models/user.py": """class User:
    pass
""",
        "services/auth_service.py": """from services.permission_service import allowed

def authenticate():
    return allowed()
""",
        "services/permission_service.py": """from services.auth_service import authenticate

def allowed():
    return bool(authenticate)
""",
        "tools.py": """import requests

def duplicate():
    return 1
""",
        "other.py": """def duplicate():
    return 2
""",
        "web/index.html": """<link rel="stylesheet" href="../assets/site.css">
<script src="../scripts/app.js"></script>
<script src="https://cdn.example.com/external.js"></script>
""",
        "assets/site.css": '@import "theme.css";\nbody { color: #fff; }\n',
        "assets/theme.css": ":root { color-scheme: dark; }\n",
        "scripts/app.js": "function start() { return true; }\nstart();\n",
    }
    for name, content in files.items():
        target = repository_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    git(repository_path, "init", "-b", "main")
    git(repository_path, "config", "user.email", "fixture@example.com")
    git(repository_path, "config", "user.name", "Fixture")
    git(repository_path, "add", ".")
    git(repository_path, "commit", "-m", "fixture graph")
    sha = git(repository_path, "rev-parse", "HEAD")
    settings = Settings(
        _env_file=None,
        repository_storage_path=storage,
        max_graph_nodes=1000,
        max_graph_edges=5000,
    )
    git_service = GitService(settings)
    with Session(engine, expire_on_commit=False) as session:
        repository = Repository(
            id=repository_id,
            owner="owner",
            name="graph",
            full_name=f"owner/graph-{repository_id}",
            url="https://github.com/owner/graph",
            status=RepositoryStatus.ready,
            local_path=str(repository_path),
            head_sha=sha,
        )
        session.add(repository)
        session.flush()
        code_job = AnalysisJob(
            repository_id=repository_id, job_type="code", status=JobStatus.running
        )
        session.add(code_job)
        session.commit()
        CodeIndexService(settings).index_repository(session, repository, code_job, git_service)
        repository.status = RepositoryStatus.ready
        code_job.status = JobStatus.completed
        commit = Commit(
            repository_id=repository_id,
            sha=sha,
            short_sha=sha[:12],
            message="fixture graph",
            author_name="Fixture",
            author_email="fixture@example.com",
            committer_name="Fixture",
            committer_email="fixture@example.com",
            authored_at=datetime.now(UTC),
            committed_at=datetime.now(UTC),
            is_merge_commit=False,
            insertions=1,
            deletions=0,
            files_changed=2,
        )
        session.add(commit)
        session.flush()
        session.add_all(
            [
                FileChange(
                    repository_id=repository_id,
                    commit_id=commit.id,
                    change_order=index,
                    old_path=None,
                    new_path=path,
                    change_type="added",
                    additions=1,
                    deletions=0,
                    similarity_score=None,
                )
                for index, path in enumerate(
                    ["controllers/user_controller.py", "services/user_service.py"]
                )
            ]
        )
        large_commit = Commit(
            repository_id=repository_id,
            sha="c" * 40,
            short_sha="c" * 12,
            message="large generated import",
            author_name="Generator",
            author_email="generator@example.com",
            committer_name="Generator",
            committer_email="generator@example.com",
            authored_at=datetime.now(UTC),
            committed_at=datetime.now(UTC),
            is_merge_commit=False,
            insertions=1000,
            deletions=0,
            files_changed=1000,
        )
        session.add(large_commit)
        session.flush()
        session.add_all(
            FileChange(
                repository_id=repository_id,
                commit_id=large_commit.id,
                change_order=index,
                old_path=None,
                new_path=path,
                change_type="added",
                additions=1,
                deletions=0,
                similarity_score=None,
            )
            for index, path in enumerate(
                ["controllers/user_controller.py", "services/user_service.py"]
            )
        )
        for index in range(5):
            history_commit = Commit(
                repository_id=repository_id,
                sha=f"{index + 1:040x}",
                short_sha=f"{index + 1:012x}",
                message=f"service history {index}",
                author_name=f"Author {index}",
                author_email=f"author{index}@example.com",
                committer_name=f"Author {index}",
                committer_email=f"author{index}@example.com",
                authored_at=datetime.now(UTC),
                committed_at=datetime.now(UTC),
                is_merge_commit=False,
                insertions=1,
                deletions=0,
                files_changed=1,
            )
            session.add(history_commit)
            session.flush()
            session.add(
                FileChange(
                    repository_id=repository_id,
                    commit_id=history_commit.id,
                    change_order=0,
                    old_path="services/user_service.py",
                    new_path="services/user_service.py",
                    change_type="modified",
                    additions=1,
                    deletions=0,
                    similarity_score=None,
                )
            )
        small_commit = Commit(
            repository_id=repository_id,
            sha="e" * 40,
            short_sha="e" * 12,
            message="small utility history",
            author_name="Utility Author",
            author_email="utility@example.com",
            committer_name="Utility Author",
            committer_email="utility@example.com",
            authored_at=datetime.now(UTC),
            committed_at=datetime.now(UTC),
            is_merge_commit=False,
            insertions=1,
            deletions=0,
            files_changed=1,
        )
        session.add(small_commit)
        session.flush()
        session.add(
            FileChange(
                repository_id=repository_id,
                commit_id=small_commit.id,
                change_order=0,
                old_path="other.py",
                new_path="other.py",
                change_type="modified",
                additions=1,
                deletions=0,
                similarity_score=None,
            )
        )
        graph_job = AnalysisJob(
            repository_id=repository_id, job_type="graph", status=JobStatus.running
        )
        session.add(graph_job)
        session.commit()
        builder = GraphBuilder(settings, git_service)
        builder.run(session, repository, graph_job)
        first_counts = (
            session.scalar(
                select(func.count())
                .select_from(DependencyNode)
                .where(DependencyNode.repository_id == repository_id)
            ),
            session.scalar(
                select(func.count())
                .select_from(DependencyEdge)
                .where(DependencyEdge.repository_id == repository_id)
            ),
        )
        first_node_ids = set(
            session.scalars(
                select(DependencyNode.id).where(DependencyNode.repository_id == repository_id)
            )
        )
        builder.run(session, repository, graph_job)
        second_counts = (
            session.scalar(
                select(func.count())
                .select_from(DependencyNode)
                .where(DependencyNode.repository_id == repository_id)
            ),
            session.scalar(
                select(func.count())
                .select_from(DependencyEdge)
                .where(DependencyEdge.repository_id == repository_id)
            ),
        )
        assert first_counts == second_counts
        assert first_node_ids == set(
            session.scalars(
                select(DependencyNode.id).where(DependencyNode.repository_id == repository_id)
            )
        )
        service = GraphService(session, settings)
        file_graph = service.graph(repository_id, "file", None, None, None, 100)
        names = {node.qualified_name: node for node in file_graph.nodes}
        pairs = {
            (
                next(
                    node.qualified_name
                    for node in file_graph.nodes
                    if node.id == edge.source_node_id
                ),
                next(
                    node.qualified_name
                    for node in file_graph.nodes
                    if node.id == edge.target_node_id
                ),
            )
            for edge in file_graph.edges
            if edge.edge_type == "DEPENDS_ON"
        }
        assert ("controllers/user_controller.py", "services/user_service.py") in pairs
        assert ("services/user_service.py", "repositories/user_repository.py") in pairs
        assert ("repositories/user_repository.py", "models/user.py") in pairs
        assert ("web/index.html", "assets/site.css") in pairs
        assert ("web/index.html", "scripts/app.js") in pairs
        assert ("scripts/app.js", "tools.py") not in pairs
        assert names["services/user_service.py"].metrics["change_count"] == 7
        assert names["services/user_service.py"].metrics["author_count"] == 7
        assert (
            names["services/user_service.py"].metrics["hotspot_score"]
            > names["other.py"].metrics["hotspot_score"] + 0.3
        )
        module_graph = service.graph(repository_id, "module", None, None, None, 100)
        module_names = {node.id: node for node in module_graph.nodes}
        module_pairs = {
            (
                module_names[edge.source_node_id].qualified_name,
                module_names[edge.target_node_id].qualified_name,
            )
            for edge in module_graph.edges
            if edge.edge_type == "DEPENDS_ON"
        }
        assert {("web", "assets"), ("web", "scripts")} <= module_pairs
        web_module = next(node for node in module_graph.nodes if node.qualified_name == "web")
        assets_module = next(node for node in module_graph.nodes if node.qualified_name == "assets")
        assert web_module.metrics["fan_out"] == 2
        assert assets_module.metrics["fan_in"] == 1
        assert web_module.metrics["change_count"] == 0
        cycles = service.cycles(repository_id, "file")
        assert any(
            {node.name for node in cycle.members} == {"auth_service.py", "permission_service.py"}
            for cycle in cycles.cycles
        )
        impact = service.impact(
            repository_id,
            names["services/user_service.py"].file_id,
            None,
            None,
            3,
            True,
        )
        assert any(node.name == "user_controller.py" for node in impact.direct_dependents)
        assert service.architecture(repository_id).components
        coupling = service.coupling(repository_id, 0, 1, None)
        assert coupling.pairs
        assert coupling.diagnostics.commits_examined == 8
        assert coupling.diagnostics.commits_used == 7
        assert coupling.diagnostics.commits_excluded_large == 1
        assert coupling.diagnostics.candidate_pairs == 1
        graph_metrics = service.metrics(repository_id)
        assert graph_metrics.edge_counts["REFERENCES"] == 2
        assert graph_metrics.relationship_levels["module"] >= 2
        assert graph_metrics.dependency_relationships < graph_metrics.edges

        unchanged_model_id = names["models/user.py"].id
        controller_path = repository_path / "controllers/user_controller.py"
        controller_path.write_text(
            """from models.user import User

def handle():
    return User()
""",
            encoding="utf-8",
        )
        git(repository_path, "add", "controllers/user_controller.py")
        git(repository_path, "commit", "-m", "redirect controller dependency")
        repository.head_sha = git(repository_path, "rev-parse", "HEAD")
        graph_job.status = JobStatus.completed
        incremental_code_job = AnalysisJob(
            repository_id=repository_id, job_type="code", status=JobStatus.running
        )
        session.add(incremental_code_job)
        session.commit()
        CodeIndexService(settings).index_repository(
            session, repository, incremental_code_job, git_service
        )
        repository.status = RepositoryStatus.ready
        incremental_code_job.status = JobStatus.completed
        session.commit()
        graph_job.status = JobStatus.running
        builder.run(session, repository, graph_job)

        updated_graph = service.graph(repository_id, "file", None, None, None, 100)
        updated_names = {node.qualified_name: node for node in updated_graph.nodes}
        updated_pairs = {
            (
                next(
                    node.qualified_name
                    for node in updated_graph.nodes
                    if node.id == edge.source_node_id
                ),
                next(
                    node.qualified_name
                    for node in updated_graph.nodes
                    if node.id == edge.target_node_id
                ),
            )
            for edge in updated_graph.edges
            if edge.edge_type == "DEPENDS_ON"
        }
        assert ("controllers/user_controller.py", "services/user_service.py") not in updated_pairs
        assert ("controllers/user_controller.py", "models/user.py") in updated_pairs
        assert updated_names["models/user.py"].id == unchanged_model_id


def test_change_coupling_repeated_commits_and_insufficient_history(engine):
    repository_id = uuid4()
    paths = {name: uuid4() for name in ("A.js", "B.js", "C.js")}
    with Session(engine) as session:
        session.add(
            Repository(
                id=repository_id,
                owner="owner",
                name="coupling",
                full_name=f"owner/coupling-{repository_id}",
                url="https://github.com/owner/coupling",
                status=RepositoryStatus.ready,
                local_path="fixture",
                head_sha="a" * 40,
            )
        )
        session.flush()
        commits = [
            ("A.js", "B.js", "C.js"),
            ("A.js", "B.js"),
            ("A.js", "B.js"),
            ("A.js", "C.js"),
        ]
        for commit_index, changed_paths in enumerate(commits):
            commit = Commit(
                repository_id=repository_id,
                sha=f"{commit_index + 100:040x}",
                short_sha=f"{commit_index + 100:012x}",
                message=f"coupling {commit_index}",
                author_name="Fixture",
                author_email="fixture@example.com",
                committer_name="Fixture",
                committer_email="fixture@example.com",
                authored_at=datetime.now(UTC),
                committed_at=datetime.now(UTC),
                is_merge_commit=False,
                insertions=len(changed_paths),
                deletions=0,
                files_changed=len(changed_paths),
            )
            session.add(commit)
            session.flush()
            session.add_all(
                FileChange(
                    repository_id=repository_id,
                    commit_id=commit.id,
                    change_order=order,
                    old_path=path,
                    new_path=path,
                    change_type="modified",
                    additions=1,
                    deletions=0,
                    similarity_score=None,
                )
                for order, path in enumerate(changed_paths)
            )
        session.commit()
        analysis = ChangeCouplingService.calculate(session, repository_id, paths, 100)
        actual = {
            frozenset((source, target)): (count, score)
            for source, target, count, score in analysis.pairs
        }
        assert actual[frozenset((paths["A.js"], paths["B.js"]))] == (3, 1.0)
        assert actual[frozenset((paths["A.js"], paths["C.js"]))] == (2, 1.0)
        assert actual[frozenset((paths["B.js"], paths["C.js"]))] == (1, 0.5)
        assert analysis.diagnostics.commits_used == 4
        assert analysis.diagnostics.candidate_pairs == 3

        excluding_large = ChangeCouplingService.calculate(session, repository_id, paths, 2)
        assert excluding_large.diagnostics.commits_excluded_large == 1
        assert excluding_large.diagnostics.commits_used == 3
        assert excluding_large.diagnostics.candidate_pairs == 2

        single_path = {"only.js": uuid4()}
        empty_repository_id = uuid4()
        session.add(
            Repository(
                id=empty_repository_id,
                owner="owner",
                name="insufficient",
                full_name=f"owner/insufficient-{empty_repository_id}",
                url="https://github.com/owner/insufficient",
                status=RepositoryStatus.ready,
                local_path="fixture",
                head_sha="b" * 40,
            )
        )
        session.flush()
        only_commit = Commit(
            repository_id=empty_repository_id,
            sha="d" * 40,
            short_sha="d" * 12,
            message="only change",
            author_name="Fixture",
            author_email="fixture@example.com",
            committer_name="Fixture",
            committer_email="fixture@example.com",
            authored_at=datetime.now(UTC),
            committed_at=datetime.now(UTC),
            is_merge_commit=False,
            insertions=1,
            deletions=0,
            files_changed=1,
        )
        session.add(only_commit)
        session.flush()
        session.add(
            FileChange(
                repository_id=empty_repository_id,
                commit_id=only_commit.id,
                change_order=0,
                old_path="only.js",
                new_path="only.js",
                change_type="modified",
                additions=1,
                deletions=0,
                similarity_score=None,
            )
        )
        session.commit()
        insufficient = ChangeCouplingService.calculate(
            session, empty_repository_id, single_path, 100
        )
        assert insufficient.diagnostics.commits_examined == 1
        assert insufficient.diagnostics.candidate_pairs == 0
        assert insufficient.pairs == []
