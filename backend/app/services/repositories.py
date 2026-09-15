import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIIndexState,
    AnalysisJob,
    ArchaeologySyncState,
    ArchitectureHistoryState,
    GitHubSyncState,
    GraphIndexState,
    JobStatus,
    Repository,
    RepositoryStatus,
)
from app.schemas.git import SubmissionResponse
from app.services.git import GitService
from app.services.repository_url import GitHubRepositoryURL

logger = logging.getLogger("ctm")
ACTIVE = (JobStatus.queued, JobStatus.running)


def get_repository(session: Session, repository_id: UUID) -> Repository:
    repository = session.get(Repository, repository_id)
    if repository is None:
        raise IngestionError("REPOSITORY_NOT_FOUND", "Repository not found.", 404)
    return repository


def active_job(session: Session, repository_id: UUID) -> AnalysisJob | None:
    return session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.repository_id == repository_id, AnalysisJob.status.in_(ACTIVE)
        )
    )


def enqueue(job: AnalysisJob) -> None:
    from app.services.task_executor import task_executor

    assert job.repository_id is not None
    task_executor.submit("index_repository", job.repository_id, job.id)


def submit_repository(
    session: Session, value: str, *, refresh: bool = False, repository_id: UUID | None = None
) -> SubmissionResponse:
    logger.info("repository_submission_received")
    try:
        url = GitHubRepositoryURL.parse(value)
        GitService().verify_remote(url)
    except IngestionError:
        logger.info("repository_validation_failed")
        raise
    logger.info("repository_validation_succeeded")
    # Serialize canonical identities across API processes, including first insert races.
    key = int.from_bytes(hashlib.sha256(url.full_name.encode()).digest()[:8], signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    session.execute(
        insert(Repository)
        .values(owner=url.owner, name=url.name, full_name=url.full_name, url=url.url)
        .on_conflict_do_nothing(index_elements=[Repository.full_name])
    )
    repository = session.scalar(
        select(Repository)
        .where(Repository.full_name == url.full_name)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    assert repository is not None
    if repository_id is not None and repository.id != repository_id:
        raise IngestionError(
            "REPOSITORY_IDENTITY_CHANGED", "Repository identity does not match.", 409
        )
    job = active_job(session, repository.id)
    if job is None and repository.status == RepositoryStatus.ready and not refresh:
        result = SubmissionResponse(repository_id=repository.id, job_id=None, status="ready")
        session.commit()
        return result
    if job is None:
        job = AnalysisJob(
            repository_id=repository.id,
            job_type="repository_refresh" if repository.indexed_at else "repository_initial_index",
            current_step="queued",
        )
        session.add(job)
        repository.status = RepositoryStatus.pending
        repository.indexing_error = None
        session.flush()
        logger.info(
            "repository_job_created", extra={"repository_id": repository.id, "job_id": job.id}
        )
    result = SubmissionResponse(
        repository_id=repository.id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()  # Worker must be able to see the job before broker publication.
    try:
        enqueue(job)
    except Exception:
        # Lock before marking failed; a message accepted by Redis may already be executing.
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The worker queue is unavailable. Start Redis and retry."
            job.completed_at = datetime.now(UTC)
            repository.status = RepositoryStatus.failed
            repository.indexing_error = job.error_message
            session.commit()
        else:
            session.rollback()
        raise IngestionError(
            "QUEUE_UNAVAILABLE", "The worker queue is unavailable. Start Redis and retry.", 503
        ) from None
    return result


def submit_code_reindex(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if not repository.head_sha or not repository.local_path:
        raise IngestionError(
            "CODE_INDEX_NOT_READY", "Git indexing must finish before code indexing.", 409
        )
    git = GitService()
    cache_present = git.storage.path(repository_id).exists()
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is None:
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="code_reindex" if cache_present else "repository_refresh",
            current_step="queued",
        )
        session.add(job)
        repository.status = (
            RepositoryStatus.indexing_code if cache_present else RepositoryStatus.pending
        )
        repository.indexing_error = None
        session.flush()
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit(
            "index_code" if cache_present else "index_repository", repository_id, job.id
        )
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            repository.status = RepositoryStatus.failed
            repository.indexing_error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_history_reindex(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if not repository.head_sha or not repository.local_path:
        raise IngestionError(
            "HISTORY_NOT_INDEXED", "Git indexing must finish before historical indexing.", 409
        )
    if not GitService().storage.path(repository_id).exists():
        raise IngestionError(
            "HISTORY_NOT_INDEXED", "The local Git object cache is unavailable. Refresh first.", 409
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is None:
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="historical_index",
            current_step="queued",
        )
        session.add(job)
        repository.status = RepositoryStatus.indexing_history
        repository.history_index_status = "queued"
        repository.indexing_error = None
        session.flush()
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_history", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            repository.status = RepositoryStatus.ready
            repository.history_index_status = "failed"
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_github_sync(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if repository.status != RepositoryStatus.ready or not repository.head_sha:
        raise IngestionError(
            "REPOSITORY_NOT_READY", "Repository indexing must finish before GitHub sync.", 409
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is None:
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="github_sync",
            current_step="queued",
        )
        session.add(job)
        state = session.get(GitHubSyncState, repository_id)
        if state is None:
            state = GitHubSyncState(repository_id=repository_id, status="queued")
            session.add(state)
        else:
            state.status = "queued"
            state.current_step = "queued"
            state.sync_error = None
        session.flush()
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_github", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            state = session.get(GitHubSyncState, repository_id)
            if state:
                state.status = "failed"
                state.sync_error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_graph_reindex(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if repository.status != RepositoryStatus.ready or not repository.head_sha:
        raise IngestionError(
            "CODE_INDEX_NOT_READY", "Build the current code index before the dependency graph.", 409
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is None:
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="dependency_graph_index",
            current_step="queued",
        )
        session.add(job)
        state = session.get(GraphIndexState, repository_id)
        if state is None:
            state = GraphIndexState(repository_id=repository_id, status="queued")
            session.add(state)
        else:
            state.status = "queued"
            state.current_step = "queued"
            state.error = None
        session.flush()
        state.job_id = job.id
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_graph", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            state = session.get(GraphIndexState, repository_id)
            if state:
                state.status = "failed"
                state.error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_architecture_history_reindex(
    session: Session, repository_id: UUID
) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if repository.status != RepositoryStatus.ready or not repository.head_sha:
        raise IngestionError(
            "ARCHITECTURE_HISTORY_NOT_READY",
            "Repository indexing must finish before architecture history.",
            409,
        )
    if not GitService().storage.path(repository_id).exists():
        raise IngestionError(
            "ARCHITECTURE_HISTORY_NOT_READY",
            "The local Git object cache is unavailable. Refresh first.",
            409,
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is None:
        job = AnalysisJob(
            repository_id=repository_id,
            job_type="architecture_history_index",
            current_step="queued",
        )
        session.add(job)
        state = session.get(ArchitectureHistoryState, repository_id)
        if state is None:
            state = ArchitectureHistoryState(repository_id=repository_id, status="queued")
            session.add(state)
        else:
            state.status = "queued"
            state.current_step = "queued"
            state.error = None
        session.flush()
        state.job_id = job.id
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_architecture_history", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            state = session.get(ArchitectureHistoryState, repository_id)
            if state:
                state.status = "failed"
                state.error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_ai_reindex(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if repository.status != RepositoryStatus.ready or not repository.head_sha:
        raise IngestionError(
            "CODE_INDEX_NOT_READY", "Repository indexing must finish before AI indexing.", 409
        )
    from app.services.ai.ollama import OllamaService

    ai_status = OllamaService().status()
    if not ai_status["available"]:
        raise IngestionError("OLLAMA_UNAVAILABLE", "Ollama is not running.", 503)
    if not ai_status["embedding_model_available"]:
        raise IngestionError(
            "EMBEDDING_MODEL_NOT_FOUND", "The configured embedding model is not installed.", 409
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is not None:
        result = SubmissionResponse(
            repository_id=repository_id,
            job_id=job.id,
            status="running" if job.status == JobStatus.running else "queued",
        )
        session.commit()
        return result
    job = AnalysisJob(
        repository_id=repository_id, job_type="embedding_index", current_step="queued"
    )
    session.add(job)
    state = session.get(AIIndexState, repository_id)
    if state is None:
        state = AIIndexState(repository_id=repository_id, status="queued")
        session.add(state)
    else:
        state.status = "queued"
        state.current_step = "queued"
        state.error = None
    session.flush()
    state.job_id = job.id
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_ai", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            state = session.get(AIIndexState, repository_id)
            if state:
                state.status = "failed"
                state.error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result


def submit_archaeology_reindex(session: Session, repository_id: UUID) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    if repository.history_index_status != "ready" or repository.history_stale:
        raise IngestionError(
            "ARCHAEOLOGY_NOT_INDEXED",
            "Historical indexing must be ready before archaeology indexing.",
            409,
        )
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(repository_id.bytes[:8], signed=True)},
    )
    job = active_job(session, repository_id)
    if job is not None:
        result = SubmissionResponse(
            repository_id=repository_id,
            job_id=job.id,
            status="running" if job.status == JobStatus.running else "queued",
        )
        session.commit()
        return result
    job = AnalysisJob(
        repository_id=repository_id,
        job_type="archaeology_index",
        current_step="queued",
    )
    session.add(job)
    state = session.get(ArchaeologySyncState, repository_id)
    if state is None:
        state = ArchaeologySyncState(repository_id=repository_id, status="pending")
        session.add(state)
    else:
        state.status = "pending"
        state.current_step = "queued"
        state.error = None
    session.flush()
    state.job_id = job.id
    result = SubmissionResponse(
        repository_id=repository_id,
        job_id=job.id,
        status="running" if job.status == JobStatus.running else "queued",
    )
    session.commit()
    try:
        from app.services.task_executor import task_executor

        task_executor.submit("index_archaeology", repository_id, job.id)
    except Exception:
        session.refresh(job, with_for_update=True)
        if job.status == JobStatus.queued:
            job.status = JobStatus.failed
            job.error_message = "The configured task executor is unavailable."
            job.completed_at = datetime.now(UTC)
            state = session.get(ArchaeologySyncState, repository_id)
            if state:
                state.status = "failed"
                state.error = job.error_message
            session.commit()
        raise IngestionError(
            "TASK_EXECUTOR_UNAVAILABLE", "The configured task executor is unavailable.", 503
        ) from None
    return result
