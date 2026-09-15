import logging
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    Commit,
    CommitParent,
    FileChange,
    JobStatus,
    Repository,
    RepositoryStatus,
    Tag,
)
from app.services.code_index import CodeIndexService
from app.services.git import GitService
from app.services.historical_index import HistoricalIndexService
from app.services.repository_url import GitHubRepositoryURL

logger = logging.getLogger("ctm")
BATCH_COMMITS = 100


def index_repository(
    engine: Engine, repository_id: UUID, job_id: UUID, git: GitService | None = None
) -> None:
    git = git or GitService()
    context = {"repository_id": repository_id, "job_id": job_id}
    lock_key = int.from_bytes(repository_id.bytes[:8], signed=True)
    # A session advisory lock survives batch commits and is released on process death.
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        )
        lock_connection.commit()
        if not acquired:
            return
        try:
            with Session(engine, expire_on_commit=False) as session:
                job = session.scalar(
                    select(AnalysisJob).where(AnalysisJob.id == job_id).with_for_update()
                )
                repository = session.get(Repository, repository_id)
                if (
                    job is None
                    or repository is None
                    or job.repository_id != repository_id
                    or job.status in (JobStatus.completed, JobStatus.failed)
                ):
                    return
                try:
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    job.error_message = None
                    job.progress = None
                    job.current_step = "validating_repository"
                    session.commit()
                    url = GitHubRepositoryURL.parse(repository.url)
                    remote = git.verify_remote(url)  # Re-check public access for every run.
                    path = git.storage.path(repository_id)
                    was_present = path.exists()
                    continue_history = repository.history_indexed_through_sha is not None
                    repository.status = RepositoryStatus.cloning
                    job.current_step = (
                        "fetching_repository" if was_present else "cloning_repository"
                    )
                    session.commit()
                    logger.info(
                        "repository_refresh_started" if was_present else "clone_started",
                        extra=context,
                    )
                    if was_present:
                        git.fetch_repository(path, url, remote)
                    else:
                        path = git.clone_repository(repository_id, url, remote)
                    logger.info("clone_completed", extra=context)
                    head = git.get_head_sha(path, fetched=was_present) if remote.head_sha else None
                    # Read the fetched ref; the remote may advance after ls-remote.
                    if remote.head_sha and head is None:
                        raise IngestionError(
                            "HEAD_NOT_FOUND", "The default branch could not be read."
                        )
                    rewritten = bool(
                        repository.head_sha and not git.is_ancestor(path, repository.head_sha, head)
                    )
                    repository.status = RepositoryStatus.indexing_git
                    job.current_step = "reading_git_history"
                    session.commit()
                    logger.info("git_history_started", extra=context)
                    shas = git.get_commits(path, head)
                    existing = set(
                        session.scalars(
                            select(Commit.sha).where(Commit.repository_id == repository_id)
                        )
                    )
                    job.current_step = "storing_commits"
                    session.commit()
                    batch_rows = 0
                    for index, sha in enumerate(shas):
                        if sha not in existing:
                            metadata = git.get_commit(path, sha)
                            changes = git.get_changed_files(path, metadata)
                            values = asdict(metadata)
                            parents = values.pop("parents")
                            commit_id = uuid4()
                            session.add(
                                Commit(
                                    id=commit_id,
                                    repository_id=repository_id,
                                    short_sha=sha[:12],
                                    is_merge_commit=len(parents) > 1,
                                    files_changed=len(changes),
                                    insertions=sum(c.additions or 0 for c in changes),
                                    deletions=sum(c.deletions or 0 for c in changes),
                                    **values,
                                )
                            )
                            session.flush()  # Parent FK rows must exist before bulk child inserts.
                            session.add_all(
                                [
                                    CommitParent(
                                        commit_id=commit_id, parent_sha=parent, parent_order=order
                                    )
                                    for order, parent in enumerate(parents)
                                ]
                            )
                            session.add_all(
                                [
                                    FileChange(
                                        repository_id=repository_id,
                                        commit_id=commit_id,
                                        change_order=order,
                                        **asdict(change),
                                    )
                                    for order, change in enumerate(changes)
                                ]
                            )
                            batch_rows += len(changes) + len(parents) + 1
                        if (index + 1) % BATCH_COMMITS == 0 or batch_rows >= 2000:
                            job.progress = (index + 1) / len(shas) * 100
                            session.commit()
                            batch_rows = 0
                            logger.info("commit_batch_stored", extra=context)
                    job.current_step = "finalizing_git_index"
                    job.progress = None
                    session.commit()
                    tags = git.get_tags(path) if head else []
                    # Reconcile rewrites and branch switches only after new history is persisted.
                    session.execute(
                        delete(Commit).where(
                            Commit.repository_id == repository_id, Commit.sha.not_in(shas)
                        )
                    )
                    session.execute(delete(Tag).where(Tag.repository_id == repository_id))
                    session.add_all([Tag(repository_id=repository_id, **tag) for tag in tags])
                    repository.default_branch = remote.default_branch
                    repository.local_path = str(path)
                    repository.head_sha = head
                    repository.commit_count = len(shas)
                    repository.history_rewritten = rewritten
                    repository.history_stale = rewritten and continue_history
                    if repository.history_stale:
                        repository.history_index_status = "stale"
                    repository.status = RepositoryStatus.indexing_code
                    session.commit()
                    logger.info("git_history_completed", extra=context)
                    CodeIndexService(git.settings).index_repository(session, repository, job, git)
                    if continue_history:
                        repository.status = RepositoryStatus.indexing_history
                        job.current_step = "preparing_commit_history"
                        session.commit()
                        HistoricalIndexService(git.settings).index_repository(
                            session, repository, job, git
                        )
                    repository.indexed_at = datetime.now(UTC)
                    if job.job_type == "repository_refresh":
                        repository.last_refreshed_at = repository.indexed_at
                    repository.status = RepositoryStatus.ready
                    repository.indexing_error = None
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.completed_at = repository.indexed_at
                    job.progress = None
                    session.commit()
                    logger.info(
                        "repository_refresh_completed" if was_present else "repository_ready",
                        extra=context,
                    )
                except Exception as error:
                    session.rollback()
                    if isinstance(error, IngestionError) and error.code == "REPOSITORY_TOO_LARGE":
                        try:
                            git.storage.remove_repository(repository_id)
                        except OSError:
                            logger.error("repository_cleanup_failed", extra=context)
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "Repository indexing failed. Retry or check the local worker."
                    )
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.completed_at = datetime.now(UTC)
                    job.progress = None
                    repository.status = RepositoryStatus.failed
                    repository.indexing_error = message
                    session.commit()
                    logger.error("repository_index_failed", extra=context)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()


def index_code_repository(
    engine: Engine, repository_id: UUID, job_id: UUID, git: GitService | None = None
) -> None:
    git = git or GitService()
    context = {"repository_id": repository_id, "job_id": job_id}
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
                    if not repository.head_sha or not git.storage.path(repository_id).exists():
                        raise IngestionError(
                            "CODE_INDEX_NOT_READY",
                            "Git indexing must finish before code indexing.",
                            409,
                        )
                    job.status = JobStatus.running
                    job.started_at = job.started_at or datetime.now(UTC)
                    job.current_step = "enumerating_repository_files"
                    repository.status = RepositoryStatus.indexing_code
                    session.commit()
                    CodeIndexService(git.settings).index_repository(session, repository, job, git)
                    now = datetime.now(UTC)
                    repository.status = RepositoryStatus.ready
                    repository.indexing_error = None
                    repository.indexed_at = now
                    job.status = JobStatus.completed
                    job.current_step = "completed"
                    job.progress = None
                    job.completed_at = now
                    session.commit()
                    logger.info("code_index_completed", extra=context)
                except Exception as error:
                    session.rollback()
                    message = (
                        error.message
                        if isinstance(error, IngestionError)
                        else "Static code indexing failed. Retry the code index."
                    )
                    repository.status = RepositoryStatus.failed
                    repository.indexing_error = message
                    job.status = JobStatus.failed
                    job.error_message = message
                    job.completed_at = datetime.now(UTC)
                    job.progress = None
                    session.commit()
                    logger.error("code_index_failed", extra=context)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock_connection.commit()
