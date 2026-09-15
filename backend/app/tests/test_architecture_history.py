import os
import subprocess
from datetime import datetime
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
    ArchitectureEvolutionEvent,
    ArchitectureRule,
    ArchitectureSnapshot,
    ArchitectureViolation,
    Commit,
    GitHubIssue,
    GitHubIssueReference,
    GitHubPRCommit,
    GitHubPullRequest,
    Repository,
    RepositoryStatus,
    Tag,
)
from app.services.architecture_history.builder import HistoricalArchitectureBuilder
from app.services.architecture_history.compare import compare_graphs
from app.services.architecture_history.indexer import ArchitectureHistoryIndexer
from app.services.architecture_history.rules import evaluate_rule
from app.services.architecture_history.service import ArchitectureHistoryService
from app.tests.architecture_history_git_fixtures import create_architecture_history_repository


def test_history_builder_detects_drift_cycle_and_resolutions(tmp_path):
    repository = tmp_path / "architecture-fixture"
    commits = create_architecture_history_repository(repository)
    builder = HistoricalArchitectureBuilder()
    repository_id = uuid4()
    graphs = {
        name: builder.build(repository_id, repository, sha) for name, sha in commits.items()
    }

    c1_edges = {(edge.source, edge.target) for edge in graphs["c1"].edges}
    assert ("module:controller", "module:service") in c1_edges
    assert ("module:service", "module:repository") in c1_edges
    assert ("module:repository", "module:model") in c1_edges
    assert graphs["c1"].cycles == []

    bypass = evaluate_rule(
        graphs["c3"],
        "forbidden_dependency",
        {"kind": "layer", "value": "controller"},
        {"kind": "layer", "value": "repository"},
    )
    assert [(item["source_stable_key"], item["target_stable_key"]) for item in bypass] == [
        ("module:controller", "module:repository")
    ]
    direct_edge = next(
        edge
        for edge in graphs["c3"].edges
        if edge.source == "module:controller" and edge.target == "module:repository"
    )
    direct_edge.confidence = 0.5
    assert evaluate_rule(
        graphs["c3"],
        "forbidden_dependency",
        {"kind": "layer", "value": "controller"},
        {"kind": "layer", "value": "repository"},
        confidence_threshold=0.8,
    ) == []
    direct_edge.confidence = 1.0
    assert graphs["c4"].metrics["cycle_count"] == 1
    assert graphs["c5"].metrics["cycle_count"] == 0
    assert evaluate_rule(
        graphs["c6"],
        "forbidden_dependency",
        {"kind": "layer", "value": "controller"},
        {"kind": "layer", "value": "repository"},
    ) == []

    cycle_diff = compare_graphs(graphs["c3"], graphs["c4"])
    fixed_diff = compare_graphs(graphs["c4"], graphs["c5"])
    assert len(cycle_diff["cycles_introduced"]) == 1
    assert len(fixed_diff["cycles_resolved"]) == 1
    assert cycle_diff["structural_drift"]["score"] > 0


def test_comparison_of_identical_graphs_has_zero_drift(tmp_path):
    repository = tmp_path / "architecture-fixture"
    commits = create_architecture_history_repository(repository)
    graph = HistoricalArchitectureBuilder().build(uuid4(), repository, commits["c1"])
    comparison = compare_graphs(graph, graph)
    assert comparison["structural_drift"]["score"] == 0
    assert comparison["nodes_added"] == []
    assert comparison["edges_added"] == []


@pytest.fixture
def architecture_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration checks")
    schema = "ctm_architecture_" + uuid4().hex
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


@pytest.mark.integration
def test_full_architecture_history_pipeline_and_idempotency(
    architecture_engine, tmp_path
):
    repository_id = uuid4()
    storage = tmp_path / "storage"
    repository_path = storage / str(repository_id) / "repo"
    commits = create_architecture_history_repository(repository_path)
    rows = subprocess.run(
        [
            "git",
            "-C",
            str(repository_path),
            "log",
            "--reverse",
            "--format=%H%x00%h%x00%s%x00%an%x00%ae%x00%aI%x00%cI%x00%P",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    settings = Settings(
        database_url=str(architecture_engine.url),
        repository_storage_path=storage,
        architecture_snapshot_strategy="all",
    )
    with Session(architecture_engine, expire_on_commit=False) as session:
        repository = Repository(
            id=repository_id,
            owner="fixture",
            name="architecture",
            full_name=f"fixture/architecture-{repository_id}",
            url="https://github.com/fixture/architecture",
            status=RepositoryStatus.ready,
            local_path=str(repository_path),
            head_sha=commits["c6"],
            commit_count=6,
        )
        session.add(repository)
        session.flush()
        for raw in rows:
            sha, short, message, author, email, authored, committed, parents = raw.split("\0")
            model = Commit(
                repository_id=repository_id,
                sha=sha,
                short_sha=short,
                message=message,
                author_name=author,
                author_email=email,
                committer_name=author,
                committer_email=email,
                authored_at=datetime.fromisoformat(authored),
                committed_at=datetime.fromisoformat(committed),
                is_merge_commit=len(parents.split()) > 1,
                insertions=0,
                deletions=0,
                files_changed=1,
            )
            session.add(model)
        session.add_all(
            [
                Tag(
                    repository_id=repository_id,
                    name="v1.0",
                    target_sha=commits["c1"],
                    annotated=False,
                ),
                Tag(
                    repository_id=repository_id,
                    name="v2.0",
                    target_sha=commits["c6"],
                    annotated=False,
                ),
            ]
        )
        rule = ArchitectureRule(
            repository_id=repository_id,
            name="No controller repository bypass",
            rule_type="forbidden_dependency",
            source_selector={"kind": "layer", "value": "controller"},
            target_selector={"kind": "layer", "value": "repository"},
            severity="error",
            enabled=True,
        )
        job = AnalysisJob(repository_id=repository_id, job_type="architecture_history_index")
        session.add_all([rule, job])
        session.commit()
        ArchitectureHistoryIndexer(settings).run(session, repository, job)
        job.status = "completed"
        session.commit()
        observed_at = datetime.now().astimezone()
        pull_request = GitHubPullRequest(
            repository_id=repository_id,
            github_pr_id=101,
            number=11,
            title="Introduce dependency cycle",
            body=None,
            state="closed",
            draft=False,
            merged=True,
            merged_at=observed_at,
            closed_at=observed_at,
            created_at=observed_at,
            updated_at=observed_at,
            author_login="fixture",
            merge_commit_sha=commits["c4"],
            base_branch="main",
            head_branch="cycle",
            additions=1,
            deletions=0,
            changed_files=1,
            commits_count=1,
            comments_count=0,
            review_comments_count=0,
            html_url="https://github.com/fixture/architecture/pull/11",
        )
        issue = GitHubIssue(
            repository_id=repository_id,
            github_issue_id=202,
            number=22,
            title="Remove dependency cycle",
            body=None,
            state="closed",
            author_login="fixture",
            created_at=observed_at,
            updated_at=observed_at,
            closed_at=observed_at,
            html_url="https://github.com/fixture/architecture/issues/22",
            comments_count=0,
            milestone=None,
        )
        session.add_all([pull_request, issue])
        session.flush()
        session.add_all(
            [
                GitHubPRCommit(
                    repository_id=repository_id,
                    pull_request_id=pull_request.id,
                    commit_sha=commits["c4"],
                ),
                GitHubIssueReference(
                    repository_id=repository_id,
                    source_type="pull_request",
                    source_id=pull_request.id,
                    target_issue_id=issue.id,
                    target_owner="fixture",
                    target_repository="architecture",
                    target_number=22,
                    reference_type="closes",
                    raw_reference="#22",
                    confidence=1.0,
                ),
            ]
        )
        session.commit()
        assert session.scalar(
            select(func.count(ArchitectureSnapshot.id)).where(
                ArchitectureSnapshot.repository_id == repository_id
            )
        ) == 6
        event_types = set(
            session.scalars(
                select(ArchitectureEvolutionEvent.event_type).where(
                    ArchitectureEvolutionEvent.repository_id == repository_id
                )
            )
        )
        assert {"cycle_introduced", "cycle_resolved"} <= event_types
        cycle_event = next(
            event
            for event in ArchitectureHistoryService(session).evolution(
                repository_id, event_type="cycle_introduced", limit=10
            )
            if event["commit_sha"] == commits["c4"]
        )
        assert cycle_event["development_context"]["pull_requests"][0]["number"] == 11
        assert cycle_event["development_context"]["issues"][0]["number"] == 22
        violation = session.scalar(
            select(ArchitectureViolation).where(
                ArchitectureViolation.repository_id == repository_id
            )
        )
        assert violation is not None
        assert violation.introduced_commit_sha == commits["c3"]
        assert violation.resolved_commit_sha == commits["c6"]
        second_job = AnalysisJob(
            repository_id=repository_id, job_type="architecture_history_index"
        )
        session.add(second_job)
        session.flush()
        ArchitectureHistoryIndexer(settings).run(session, repository, second_job)
        session.commit()
        assert session.scalar(
            select(func.count(ArchitectureSnapshot.id)).where(
                ArchitectureSnapshot.repository_id == repository_id
            )
        ) == 6
