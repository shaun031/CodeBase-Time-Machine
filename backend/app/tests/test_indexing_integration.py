"""Real PostgreSQL + local Git fixtures; no network, no SQLite fallback."""

import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    ArchaeologyMetric,
    ArchaeologySyncState,
    CodeSymbol,
    Commit,
    CommitParent,
    ContributorEntityMetric,
    CopyMoveCandidate,
    FileChange,
    FileLineage,
    FileVersion,
    JobStatus,
    Repository,
    RepositoryFile,
    RepositoryStatus,
    SymbolChangeEvent,
    SymbolLineage,
    SymbolRewriteEvent,
    SymbolVersion,
)
from app.services.archaeology.indexer import index_archaeology_repository
from app.services.archaeology.service import ArchaeologyService
from app.services.git import GitService, RemoteInfo
from app.services.historical_index import index_historical_repository
from app.services.history import HistoryService
from app.services.indexing import index_code_repository, index_repository
from app.services.repositories import submit_code_reindex, submit_repository
from app.tests.archaeology_git_fixtures import create_archaeology_repository
from app.tests.git_fixtures import create_repository
from app.tests.history_git_fixtures import create_history_repository

pytestmark = pytest.mark.integration


@pytest.fixture
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL integration checks")
    schema = "ctm_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(url, connect_args={"options": f"-c search_path={schema},public"})
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.attributes["version_table_schema"] = schema
    try:
        with test_engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            assert conn.scalar(text("SELECT current_schema()")) == schema
            assert conn.scalar(text("SELECT to_regclass('repositories')")) == "repositories"
        yield test_engine
    finally:
        test_engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def local_git(tmp_path, monkeypatch):
    source = tmp_path / "source"
    shas = create_repository(source)
    storage = tmp_path / "storage"
    monkeypatch.setenv("REPOSITORY_STORAGE_PATH", str(storage))
    get_settings.cache_clear()
    git = GitService(Settings(_env_file=None, repository_storage_path=storage))
    monkeypatch.setattr(git, "verify_remote", lambda url: RemoteInfo("main", shas["head"]))

    def clone(repository_id, url, remote):
        path = git.storage.path(repository_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, path)
        return path

    monkeypatch.setattr(git, "clone_repository", clone)
    return git, shas


@pytest.fixture
def history_git(tmp_path, monkeypatch):
    source = tmp_path / "history-source"
    shas = create_history_repository(source)
    storage = tmp_path / "history-storage"
    settings = Settings(_env_file=None, repository_storage_path=storage)
    git = GitService(settings)
    monkeypatch.setattr(git, "verify_remote", lambda url: RemoteInfo("main", shas["head"]))

    def clone(repository_id, url, remote):
        path = git.storage.path(repository_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, path)
        return path

    monkeypatch.setattr(git, "clone_repository", clone)
    return git, shas


@pytest.fixture
def archaeology_git(tmp_path, monkeypatch):
    source = tmp_path / "archaeology-source"
    shas = create_archaeology_repository(source)
    storage = tmp_path / "archaeology-storage"
    settings = Settings(_env_file=None, repository_storage_path=storage)
    git = GitService(settings)
    monkeypatch.setattr(git, "verify_remote", lambda url: RemoteInfo("main", shas["head"]))

    def clone(repository_id, url, remote):
        path = git.storage.path(repository_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, path)
        return path

    monkeypatch.setattr(git, "clone_repository", clone)
    return git, shas


def seed(engine):
    with Session(engine) as session:
        repository = Repository(
            owner="owner", name="repo", full_name="owner/repo", url="https://github.com/owner/repo"
        )
        session.add(repository)
        session.flush()
        job = AnalysisJob(
            repository_id=repository.id, job_type="repository_initial_index", current_step="queued"
        )
        session.add(job)
        session.commit()
        return repository.id, job.id


def test_indexing_roundtrip_idempotency_and_api(engine, local_git, client):
    git, shas = local_git
    repository_id, job_id = seed(engine)
    index_repository(engine, repository_id, job_id, git)
    index_repository(engine, repository_id, job_id, git)
    with Session(engine) as session:
        assert session.get(Repository, repository_id).status == RepositoryStatus.ready
        assert session.get(Repository, repository_id).head_sha == shas["head"]
        assert session.get(AnalysisJob, job_id).status == JobStatus.completed
        assert session.scalar(select(func.count()).select_from(Commit)) == 10
        assert session.scalar(select(func.count()).select_from(CommitParent)) == 10
        assert session.scalar(select(func.count()).select_from(FileChange)) == 10
        assert session.scalar(select(func.count()).select_from(RepositoryFile)) == 5
        from app.db.session import get_session

        client.app.dependency_overrides[get_session] = lambda: session
        try:
            repo = client.get(f"/api/repositories/{repository_id}")
            assert repo.json()["commit_count"] == 10 and "local_path" not in repo.json()
            assert client.get(f"/api/jobs/{job_id}").json()["status"] == "completed"
            page = client.get(f"/api/repositories/{repository_id}/commits?page_size=2")
            assert page.status_code == 200 and len(page.json()["items"]) == 2
            detail = client.get(f"/api/repositories/{repository_id}/commits/{shas['rename']}")
            assert detail.json()["changes"][0]["change_type"] == "renamed"
            assert "author_email" not in detail.json()
            code_stats = client.get(f"/api/repositories/{repository_id}/code/stats")
            assert code_stats.status_code == 200
            assert code_stats.json()["total_files"] == 5
            tree = client.get(f"/api/repositories/{repository_id}/files")
            assert tree.status_code == 200
            content = client.get(f"/api/repositories/{repository_id}/files/main.py/content")
            assert content.status_code == 200
            assert "print('world')" in content.json()["content"]
            binary = client.get(f"/api/repositories/{repository_id}/files/image.bin/content")
            assert binary.status_code == 415
            assert binary.json()["error"]["code"] == "BINARY_FILE"
        finally:
            client.app.dependency_overrides.clear()


def test_failure_sets_both_states(engine, local_git, monkeypatch):
    git, _ = local_git
    repository_id, job_id = seed(engine)

    def fail(*args):
        raise IngestionError("CLONE_FAILED", "Clone failed safely.")

    monkeypatch.setattr(git, "clone_repository", fail)
    index_repository(engine, repository_id, job_id, git)
    with Session(engine) as session:
        assert session.get(Repository, repository_id).status == RepositoryStatus.failed
        job = session.get(AnalysisJob, job_id)
        assert job.status == JobStatus.failed and job.error_message == "Clone failed safely."


def test_duplicate_and_queue_failure(engine, monkeypatch):
    monkeypatch.setattr(GitService, "verify_remote", lambda *args: RemoteInfo("main", "a" * 40))
    monkeypatch.setattr("app.services.repositories.enqueue", lambda job: None)
    with Session(engine) as session:
        first = submit_repository(session, "https://github.com/OWNER/Repo.git")
        second = submit_repository(session, "https://github.com/owner/repo")
        assert first.repository_id == second.repository_id and first.job_id == second.job_id
        assert session.scalar(select(func.count()).select_from(Repository)) == 1
        assert session.scalar(select(func.count()).select_from(AnalysisJob)) == 1

    def fail(job):
        raise RuntimeError("secret-internal-error")

    monkeypatch.setattr("app.services.repositories.enqueue", fail)
    with Session(engine) as session:
        with pytest.raises(IngestionError) as error:
            submit_repository(session, "https://github.com/owner/another")
        assert error.value.code == "QUEUE_UNAVAILABLE"
        failed = session.scalar(select(Repository).where(Repository.name == "another"))
        assert failed.status == RepositoryStatus.failed


def test_refresh_reuses_commits_and_reconciles_rewind(engine, local_git, monkeypatch):
    git, shas = local_git
    repo_id, job_id = seed(engine)
    index_repository(engine, repo_id, job_id, git)
    head_reader = git.get_head_sha
    monkeypatch.setattr(git, "fetch_repository", lambda *args: None)
    monkeypatch.setattr(git, "get_head_sha", lambda path, **kwargs: head_reader(path))

    def unexpected(*args):
        raise AssertionError("Already stored commits must not be parsed again")

    monkeypatch.setattr(git, "get_commit", unexpected)

    def new_job():
        with Session(engine) as session:
            job = AnalysisJob(
                repository_id=repo_id, job_type="repository_refresh", current_step="queued"
            )
            session.add(job)
            session.commit()
            return job.id

    index_repository(engine, repo_id, new_job(), git)
    with Session(engine) as session:
        repo = session.get(Repository, repo_id)
        assert repo.status == RepositoryStatus.ready
        assert repo.commit_count == 10 and repo.last_refreshed_at is not None
    monkeypatch.setattr(git, "verify_remote", lambda url: RemoteInfo("main", shas["rename"]))
    monkeypatch.setattr(git, "get_head_sha", lambda *args, **kwargs: shas["rename"])
    index_repository(engine, repo_id, new_job(), git)
    with Session(engine) as session:
        repo = session.get(Repository, repo_id)
        assert repo.status == RepositoryStatus.ready
        assert repo.history_rewritten and repo.head_sha == shas["rename"]
        assert repo.commit_count == 5
        assert session.scalar(select(func.count()).select_from(Commit)) == 5


def test_retry_after_partial_batch_is_idempotent(engine, local_git, monkeypatch):
    monkeypatch.setattr("app.services.indexing.BATCH_COMMITS", 2)
    git, shas = local_git
    repo_id, job_id = seed(engine)
    original = git.get_changed_files

    def fail_at_last(path, commit):
        if commit.sha == shas["head"]:
            raise IngestionError("GIT_COMMAND_FAILED", "Simulated read failure")
        return original(path, commit)

    monkeypatch.setattr(git, "get_changed_files", fail_at_last)
    index_repository(engine, repo_id, job_id, git)
    with Session(engine) as session:
        assert session.get(AnalysisJob, job_id).status == JobStatus.failed
        assert session.scalar(select(func.count()).select_from(Commit)) == 8
        retry = AnalysisJob(
            repository_id=repo_id, job_type="repository_initial_index", current_step="queued"
        )
        session.add(retry)
        session.commit()
        retry_id = retry.id
    monkeypatch.setattr(git, "get_changed_files", original)
    monkeypatch.setattr(git, "fetch_repository", lambda *args: None)
    head_reader = git.get_head_sha
    monkeypatch.setattr(git, "get_head_sha", lambda path, **kwargs: head_reader(path))
    index_repository(engine, repo_id, retry_id, git)
    with Session(engine) as session:
        assert session.get(AnalysisJob, retry_id).status == JobStatus.completed
        assert session.scalar(select(func.count()).select_from(Commit)) == 10


def test_code_index_reuses_modifies_and_deletes_blobs(engine, local_git):
    git, _ = local_git
    repository_id, job_id = seed(engine)
    index_repository(engine, repository_id, job_id, git)
    destination = git.storage.path(repository_id)
    with Session(engine) as session:
        original = session.scalar(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id,
                RepositoryFile.path == "main.py",
            )
        )
        assert original is not None
        original_id, original_blob = original.id, original.blob_sha
    (destination / "main.py").write_text("def current_value():\n    return 42\n", encoding="utf-8")
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "add",
            "main.py",
        ],
        cwd=destination,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-m",
            "Modify source",
        ],
        cwd=destination,
        check=True,
        stdout=subprocess.DEVNULL,
    )

    def run_code_index() -> None:
        head = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination).decode().strip()
        )
        with Session(engine) as session:
            repository = session.get(Repository, repository_id)
            repository.head_sha = head
            job = AnalysisJob(
                repository_id=repository_id, job_type="code_reindex", current_step="queued"
            )
            session.add(job)
            session.commit()
            current_job_id = job.id
        index_code_repository(engine, repository_id, current_job_id, git)

    run_code_index()
    with Session(engine) as session:
        modified = session.scalar(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id, RepositoryFile.path == "main.py"
            )
        )
        assert modified is not None
        assert modified.id == original_id and modified.blob_sha != original_blob
        assert (
            session.scalar(
                select(func.count())
                .select_from(CodeSymbol)
                .where(CodeSymbol.file_id == modified.id)
            )
            == 1
        )
    (destination / "main.py").unlink()
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "add", "--all"],
        cwd=destination,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.test",
            "commit",
            "-m",
            "Delete source",
        ],
        cwd=destination,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    run_code_index()
    with Session(engine) as session:
        assert (
            session.scalar(
                select(RepositoryFile).where(
                    RepositoryFile.repository_id == repository_id, RepositoryFile.path == "main.py"
                )
            )
            is None
        )


def test_code_reindex_rebuilds_a_missing_mode_specific_git_cache(engine, local_git, monkeypatch):
    git, _ = local_git
    repository_id, job_id = seed(engine)
    index_repository(engine, repository_id, job_id, git)
    git.storage.remove_repository(repository_id)
    assert not git.storage.path(repository_id).exists()
    submitted: list[tuple[str, object, object]] = []
    monkeypatch.setattr(
        "app.services.task_executor.task_executor.submit",
        lambda task, repo_id, queued_job_id: submitted.append((task, repo_id, queued_job_id)),
    )
    with Session(engine) as session:
        result = submit_code_reindex(session, repository_id)
        job = session.get(AnalysisJob, result.job_id)
        repository = session.get(Repository, repository_id)
        assert job is not None
        assert job.job_type == "repository_refresh"
        assert repository is not None
        assert repository.status == RepositoryStatus.pending
    assert submitted == [("index_repository", repository_id, result.job_id)]


def test_historical_lineage_roundtrip_incremental_refresh_and_idempotency(
    engine, history_git, client, monkeypatch
):
    git, shas = history_git
    repository_id, job_id = seed(engine)
    index_repository(engine, repository_id, job_id, git)
    with Session(engine) as session:
        history_job = AnalysisJob(
            repository_id=repository_id, job_type="historical_index", current_step="queued"
        )
        session.add(history_job)
        session.commit()
        history_job_id = history_job.id
    index_historical_repository(engine, repository_id, history_job_id, git)

    with Session(engine) as session:
        repository = session.get(Repository, repository_id)
        assert repository is not None
        assert repository.history_index_status == "ready"
        assert repository.history_indexed_commit_count == 11
        assert session.scalar(select(func.count()).select_from(FileLineage)) == 1
        assert session.scalar(select(func.count()).select_from(FileVersion)) == 10
        lineages = list(
            session.scalars(
                select(SymbolLineage).where(SymbolLineage.repository_id == repository_id)
            )
        )
        total_lineage = next(
            item for item in lineages if item.current_name == "total" and not item.is_deleted
        )
        versions = list(
            session.scalars(
                select(SymbolVersion).where(SymbolVersion.lineage_id == total_lineage.id)
            )
        )
        event_types = set(
            session.scalars(
                select(SymbolChangeEvent.event_type).where(
                    SymbolChangeEvent.lineage_id == total_lineage.id
                )
            )
        )
        assert {"introduced", "body_changed", "signature_changed"} <= event_types
        assert {
            "renamed",
            "moved",
            "documentation_changed",
            "deleted",
            "reintroduced",
        } <= event_types
        assert len(versions) >= 7
        phase_two_symbol = session.scalar(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.name == "total",
            )
        )
        assert phase_two_symbol is not None and phase_two_symbol.lineage_id == total_lineage.id

        service = HistoryService(session, git.settings)
        lineage = service.lineage(repository_id, total_lineage.id)
        assert lineage.introduced_commit is not None
        assert lineage.introduced_commit.sha == shas["introduced"]
        assert lineage.previous_names == ["calculate_total", "total"]
        compared = service.compare(
            repository_id,
            total_lineage.id,
            lineage.versions[0].id,
            lineage.versions[-1].id,
        )
        assert "calculate_total" in compared.old_source
        assert "total" in compared.new_source
        source = service.source(repository_id, total_lineage.id, lineage.versions[0].id)
        assert source.commit_sha == shas["introduced"]
        historical = service.content_at(repository_id, "calculator.py", shas["body"])
        assert "round(total, 2)" in historical.content

        from app.db.session import get_session

        client.app.dependency_overrides[get_session] = lambda: session
        try:
            status = client.get(f"/api/repositories/{repository_id}/history/status")
            assert status.status_code == 200 and status.json()["events"] > 0
            timeline = client.get(f"/api/repositories/{repository_id}/history/events")
            assert timeline.status_code == 200 and timeline.json()["total"] > 0
            current = client.get(
                f"/api/repositories/{repository_id}/symbols/{phase_two_symbol.id}/history"
            )
            assert current.status_code == 200 and current.json()["id"] == str(total_lineage.id)
            unsafe = client.get(
                f"/api/repositories/{repository_id}/files/content-at",
                params={"path": "../../../etc/passwd", "commit_sha": shas["head"]},
            )
            assert unsafe.status_code == 422
        finally:
            client.app.dependency_overrides.clear()

        counts_before = (
            session.scalar(select(func.count()).select_from(SymbolLineage)),
            session.scalar(select(func.count()).select_from(SymbolVersion)),
            session.scalar(select(func.count()).select_from(SymbolChangeEvent)),
        )

    with Session(engine) as session:
        repeat = AnalysisJob(
            repository_id=repository_id, job_type="historical_index", current_step="queued"
        )
        session.add(repeat)
        session.commit()
        repeat_id = repeat.id
    index_historical_repository(engine, repository_id, repeat_id, git)
    with Session(engine) as session:
        counts_after = (
            session.scalar(select(func.count()).select_from(SymbolLineage)),
            session.scalar(select(func.count()).select_from(SymbolVersion)),
            session.scalar(select(func.count()).select_from(SymbolChangeEvent)),
        )
        assert counts_after == counts_before

    destination = git.storage.path(repository_id)
    module = destination / "math_utils.py"
    module.write_text(
        module.read_text(encoding="utf-8").replace(
            "return round(total, 2)", "return round(total, 3)"
        ),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2021-02-12T12:00:00+00:00",
        "GIT_COMMITTER_DATE": "2021-02-12T12:00:00+00:00",
    }
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=History Fixture",
            "-c",
            "user.email=history@example.test",
            "add",
            "math_utils.py",
        ],
        cwd=destination,
        env=environment,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=History Fixture",
            "-c",
            "user.email=history@example.test",
            "commit",
            "-m",
            "Increase total precision",
        ],
        cwd=destination,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    new_head = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=destination).decode().strip()
    )
    original_head_reader = git.get_head_sha
    monkeypatch.setattr(git, "verify_remote", lambda url: RemoteInfo("main", new_head))
    monkeypatch.setattr(git, "fetch_repository", lambda *args: None)
    monkeypatch.setattr(
        git,
        "get_head_sha",
        lambda path, fetched=False: original_head_reader(path),
    )
    with Session(engine) as session:
        refresh = AnalysisJob(
            repository_id=repository_id, job_type="repository_refresh", current_step="queued"
        )
        session.add(refresh)
        session.commit()
        refresh_id = refresh.id
    index_repository(engine, repository_id, refresh_id, git)
    with Session(engine) as session:
        repository = session.get(Repository, repository_id)
        assert repository is not None
        assert repository.head_sha == new_head
        assert repository.history_indexed_through_sha == new_head
        assert repository.history_indexed_commit_count == 12
        assert session.scalar(select(func.count()).select_from(SymbolVersion)) > counts_after[1]


def test_archaeology_provenance_churn_contributors_copy_search_and_api(
    engine, archaeology_git, client
):
    git, shas = archaeology_git
    repository_id, repository_job_id = seed(engine)
    index_repository(engine, repository_id, repository_job_id, git)

    with Session(engine) as session:
        history_job = AnalysisJob(
            repository_id=repository_id,
            job_type="historical_index",
            current_step="queued",
        )
        session.add(history_job)
        session.commit()
        history_job_id = history_job.id
    index_historical_repository(engine, repository_id, history_job_id, git)

    with Session(engine) as session:
        archaeology_job = AnalysisJob(
            repository_id=repository_id,
            job_type="archaeology_index",
            current_step="queued",
        )
        session.add(archaeology_job)
        session.commit()
        archaeology_job_id = archaeology_job.id
    index_archaeology_repository(engine, repository_id, archaeology_job_id)

    with Session(engine) as session:
        state = session.get(ArchaeologySyncState, repository_id)
        assert state is not None
        assert state.status == "ready" and state.last_indexed_sha == shas["head"]

        lineages = list(
            session.scalars(
                select(SymbolLineage).where(SymbolLineage.repository_id == repository_id)
            )
        )
        current = next(
            lineage
            for lineage in lineages
            if not lineage.is_deleted
            and lineage.current_name == "find_user"
            and lineage.current_file_path == "src/services/user_service.py"
        )
        deleted_copy = next(
            lineage
            for lineage in lineages
            if lineage.is_deleted
            and lineage.current_name == "find_user"
            and lineage.current_file_path == "src/admin/admin_user_service.py"
        )
        current_metric = session.scalar(
            select(ArchaeologyMetric).where(
                ArchaeologyMetric.repository_id == repository_id,
                ArchaeologyMetric.entity_type == "symbol",
                ArchaeologyMetric.entity_id == current.id,
            )
        )
        assert current_metric is not None
        assert current_metric.metadata_json["original_name"] == "get_user"
        assert current_metric.metadata_json["original_path"] == "src/users.py"
        assert current_metric.metadata_json["introduced_commit_sha"] == shas["introduced"]
        assert current_metric.rename_count >= 1
        assert current_metric.move_count >= 1
        assert current_metric.rewrite_count == 1
        assert current_metric.change_count == 5

        rewrite = session.scalar(
            select(SymbolRewriteEvent).where(SymbolRewriteEvent.lineage_id == current.id)
        )
        assert rewrite is not None
        assert rewrite.commit_id == session.scalar(
            select(Commit.id).where(Commit.sha == shas["rewritten"])
        )
        assert rewrite.similarity < 0.5

        candidate = session.scalar(
            select(CopyMoveCandidate).where(
                CopyMoveCandidate.source_lineage_id == current.id,
                CopyMoveCandidate.target_lineage_id == deleted_copy.id,
            )
        )
        assert candidate is not None
        assert candidate.relationship == "exact_copy"
        assert candidate.similarity == 1

        stable = session.scalar(
            select(ArchaeologyMetric).where(
                ArchaeologyMetric.repository_id == repository_id,
                ArchaeologyMetric.entity_type == "file",
                ArchaeologyMetric.path == "src/stable_util.py",
            )
        )
        volatile = session.scalar(
            select(ArchaeologyMetric).where(
                ArchaeologyMetric.repository_id == repository_id,
                ArchaeologyMetric.entity_type == "file",
                ArchaeologyMetric.path == "src/volatile_service.py",
            )
        )
        assert stable is not None and volatile is not None
        assert volatile.change_count == 7
        assert volatile.churn > stable.churn
        assert volatile.volatility_score > stable.volatility_score
        assert stable.stability_score > volatile.stability_score

        contributors = list(
            session.scalars(
                select(ContributorEntityMetric).where(
                    ContributorEntityMetric.repository_id == repository_id,
                    ContributorEntityMetric.entity_type == "file",
                    ContributorEntityMetric.entity_id == volatile.entity_id,
                )
            )
        )
        assert {row.display_name for row in contributors} == {"Alice", "Bob", "Charlie"}
        bob = next(row for row in contributors if row.display_name == "Bob")
        assert bob.commit_count == 4
        assert bob.knowledge_score == max(row.knowledge_score for row in contributors)

        archaeology = ArchaeologyService(session)
        old_name = archaeology.search(repository_id, "get_user", "all", "all", None, None, 1, 50)
        assert any(item.lineage_id == current.id for item in old_name.items)
        deleted = archaeology.search(
            repository_id, "find_user", "deleted_symbol", "all", None, None, 1, 50
        )
        assert deleted.items and all(item.status == "deleted" for item in deleted.items)
        dossier = archaeology.dossier(
            repository_id,
            file_id=None,
            symbol_id=None,
            lineage_id=current.id,
        )
        assert dossier.provenance.origin["name"] == "get_user"
        assert dossier.provenance.origin["path"] == "src/users.py"
        assert dossier.target.rewrite_count == 1

        from app.db.session import get_session

        client.app.dependency_overrides[get_session] = lambda: session
        try:
            status = client.get(f"/api/repositories/{repository_id}/archaeology/status")
            assert status.status_code == 200 and status.json()["status"] == "ready"
            provenance = client.get(
                f"/api/repositories/{repository_id}/archaeology/provenance",
                params={"lineage_id": str(current.id)},
            )
            assert provenance.status_code == 200
            assert provenance.json()["origin"]["name"] == "get_user"
            deleted_search = client.get(
                f"/api/repositories/{repository_id}/archaeology/search",
                params={"q": "find_user", "type": "deleted_symbol"},
            )
            assert deleted_search.status_code == 200
            assert all(item["status"] == "deleted" for item in deleted_search.json()["items"])
        finally:
            client.app.dependency_overrides.clear()
