import os
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.db.models import Commit, Repository, RepositoryFile, RepositoryStatus
from app.schemas.ai import GeneratedAnswer, GroundedClaim
from app.services.ai.archaeology import SoftwareArchaeologyService
from app.services.git import GitService
from app.services.investigation.regression import RegressionAnalysisService
from app.services.investigation.report import InvestigationReportService, sanitize_failure_text
from app.services.investigation.stacktrace import StackTraceParser
from app.services.investigation.szz import SZZAnalysisService
from app.tests.investigation_git_fixtures import create_bug_investigation_repository


def test_stack_trace_adapters_normalize_supported_languages():
    trace = """Traceback (most recent call last):
  File "src/service.py", line 12, in load
ValueError: missing account
    at loadData (frontend/app.js:42:9)
    at com.example.Worker.run(Worker.java:18)
calculate src/calc.cpp:30:4
serve cmd/server.go:77
"""
    result = StackTraceParser(50_000, 100).parse(trace)
    assert result["exception_type"] == "ValueError"
    assert result["error_message"] == "missing account"
    assert [frame["language"] for frame in result["frames"]] == [
        "python",
        "javascript",
        "java",
        "c_cpp",
        "go",
    ]
    assert result["frames"][1]["file_path"] == "frontend/app.js"
    assert result["frames"][1]["column"] == 9


def test_failure_text_is_redacted_before_persistence():
    value = (
        "TypeError token=super-secret password:also-secret safe=value\n"
        "Authorization: Bearer hidden-value"
    )
    assert sanitize_failure_text(value) == (
        "TypeError token=[REDACTED] password=[REDACTED] safe=value\n"
        "Authorization=[REDACTED]"
    )


def test_szz_line_selection_ignores_comments_and_tracks_deleted_code():
    diff = """@@ -10,3 +10,2 @@
-# explanatory comment
-return broken(value)
+return fixed(value)
 context()
"""
    assert SZZAnalysisService._candidate_lines(diff) == [11]


def test_investigation_explanation_uses_only_cited_report_evidence(monkeypatch):
    service = InvestigationReportService(None, Settings())  # type: ignore[arg-type]
    investigation_id = uuid4()
    repository_id = uuid4()
    monkeypatch.setattr(
        service,
        "read",
        lambda _repository_id, _investigation_id: {
            "status": "ready",
            "result": {
                "top_candidates": [
                    {
                        "commit_sha": "a" * 40,
                        "commit_id": "commit-a",
                        "score": 0.9,
                        "reasons": ["blamed_changed_line"],
                        "signals": {"blame": 1.0},
                        "message": "Change failing line",
                        "files": ["src/payment.py"],
                        "symbols": ["calculate_total"],
                    }
                ],
                "resolved_frames": [],
            },
        },
    )
    monkeypatch.setattr(
        SoftwareArchaeologyService,
        "_generate",
        lambda *_args, **_kwargs: GeneratedAnswer(
            answer="ignored free text",
            claims=[
                GroundedClaim(
                    text="This commit is the strongest candidate, not a confirmed cause.",
                    evidence_ids=["E1", "invented"],
                )
            ],
            confidence="high",
            limitations=[],
        ),
    )

    response = service.explain(repository_id, investigation_id, "Explain the report")
    assert response["claims"][0]["evidence_ids"] == ["E1"]
    assert response["answer"].endswith("[1]")
    assert response["confidence"] == "low"


def test_static_commit_range_and_rename_aware_blame(tmp_path):
    repository = tmp_path / "phase-nine"
    commits = create_bug_investigation_repository(repository)
    git = GitService(Settings(repository_storage_path=str(tmp_path / "storage")))

    commit_range = git.get_commit_range(repository, commits["B"], commits["E"], 20)
    assert commits["C"] in commit_range
    assert commits["D"] in commit_range
    assert commit_range[-1] == commits["E"]

    blamed = git.get_blame(repository, commits["D"], "src/math_utils.py", 2, 2)
    assert blamed[0].commit_sha == commits["C"]
    assert blamed[0].original_path == "src/calc.py"


@pytest.fixture
def investigation_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration checks")
    schema = "ctm_investigation_" + uuid4().hex
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
def test_szz_finds_bug_commit_across_rename(investigation_engine, tmp_path):
    repository_id = uuid4()
    storage = tmp_path / "storage"
    repository_path = storage / str(repository_id) / "repo"
    commits = create_bug_investigation_repository(repository_path)
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
        database_url=str(investigation_engine.url),
        repository_storage_path=storage,
    )
    with Session(investigation_engine, expire_on_commit=False) as session:
        session.add(
            Repository(
                id=repository_id,
                owner="fixture",
                name="investigation",
                full_name=f"fixture/investigation-{repository_id}",
                url="https://github.com/fixture/investigation",
                status=RepositoryStatus.ready,
                local_path=str(repository_path),
                head_sha=commits["E"],
                commit_count=len(rows),
                history_index_status="ready",
            )
        )
        session.flush()
        for raw in rows:
            sha, short, message, author, email, authored, committed, parents = raw.split("\0")
            session.add(
                Commit(
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
            )
        blob_sha = subprocess.run(
            ["git", "-C", str(repository_path), "rev-parse", f"{commits['E']}:src/math_utils.py"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        session.add(
            RepositoryFile(
                repository_id=repository_id,
                path="src/math_utils.py",
                filename="math_utils.py",
                extension=".py",
                language="Python",
                blob_sha=blob_sha,
                size_bytes=88,
                line_count=4,
                is_binary=False,
                parse_status="parsed",
                syntax_error_count=0,
                indexed_commit_sha=commits["E"],
            )
        )
        session.commit()

        result = SZZAnalysisService(session, settings).analyze(
            repository_id, commits["E"], "src/math_utils.py"
        )
        assert result["candidates"][0]["commit_sha"] == commits["C"]
        assert "src/calc.py" in {
            item["original_path"] for item in result["candidates"][0]["evidence"]
        }

        regression = RegressionAnalysisService(session, settings).range(
            repository_id, commits["B"], commits["E"]
        )
        assert commits["C"] in {item["sha"] for item in regression["commits"]}
