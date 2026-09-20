from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select, union
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AIIndexState,
    AnalysisJob,
    ArchaeologySyncState,
    ArchitectureHistoryState,
    CodeSymbol,
    Commit,
    CommitParent,
    FileChange,
    GitHubSyncState,
    GraphIndexState,
    Repository,
    RepositoryFile,
    RepositoryStatus,
    Tag,
)
from app.db.session import get_session
from app.schemas.analysis_job import AnalysisJobRead
from app.schemas.git import (
    CommitDetail,
    CommitPage,
    CommitSummary,
    DiffResponse,
    FileChangeRead,
    RepositoryDetail,
    RepositoryStats,
    RepositorySubmit,
    SubmissionResponse,
    TagRead,
)
from app.schemas.system_status import RepositorySubsystemStatus, RepositorySystemStatus
from app.services.ai.ollama import OllamaService
from app.services.git import GitService
from app.services.repositories import active_job, get_repository, submit_repository

router = APIRouter(tags=["repositories"])
Database = Annotated[Session, Depends(get_session)]


def ready(session: Session, repository_id: UUID) -> Repository:
    repository = get_repository(session, repository_id)
    if repository.status != RepositoryStatus.ready:
        raise IngestionError(
            "REPOSITORY_NOT_READY", "Wait for indexing to finish before browsing history.", 409
        )
    return repository


def stored_commit(session: Session, repository_id: UUID, sha: str) -> Commit:
    ready(session, repository_id)
    GitService.validate_sha(sha)
    commit = session.scalar(
        select(Commit).where(Commit.repository_id == repository_id, Commit.sha == sha)
    )
    if commit is None:
        raise IngestionError(
            "COMMIT_NOT_FOUND", "Commit not found in the indexed default-branch history.", 404
        )
    return commit


@router.post("/repositories", response_model=SubmissionResponse, status_code=202)
def submit(body: RepositorySubmit, session: Database) -> SubmissionResponse:
    return submit_repository(session, body.url)


@router.get("/repositories/{repository_id}", response_model=RepositoryDetail)
def repository_detail(repository_id: UUID, session: Database) -> RepositoryDetail:
    repository = get_repository(session, repository_id)
    response = RepositoryDetail.model_validate(repository)
    job = active_job(session, repository_id)
    response.active_job_id = job.id if job else None
    return response


def _state_status(
    status: str | None, indexed_sha: str | None, head_sha: str | None, *, error: str | None = None
) -> str:
    """Normalize persisted states without making one optional index block another."""
    if error:
        return "failed"
    if status in {"queued", "pending", "indexing", "syncing", "analyzing"}:
        return "indexing"
    if status in {"failed", "rate_limited", "not_indexed"}:
        return status
    if status in {"ready", "completed"}:
        return "stale" if head_sha and indexed_sha and indexed_sha != head_sha else "ready"
    return status or "not_indexed"


@router.get("/repositories/{repository_id}/system-status", response_model=RepositorySystemStatus)
def repository_system_status(repository_id: UUID, session: Database) -> RepositorySystemStatus:
    """Return all independent index states in one inexpensive dashboard request."""
    repository = get_repository(session, repository_id)
    graph = session.get(GraphIndexState, repository_id)
    ai = session.get(AIIndexState, repository_id)
    github = session.get(GitHubSyncState, repository_id)
    archaeology = session.get(ArchaeologySyncState, repository_id)
    architecture_history = session.get(ArchitectureHistoryState, repository_id)
    current_job = active_job(session, repository_id)
    file_count = session.scalar(
        select(func.count())
        .select_from(RepositoryFile)
        .where(RepositoryFile.repository_id == repository_id)
    ) or 0
    symbol_count = session.scalar(
        select(func.count())
        .select_from(CodeSymbol)
        .where(CodeSymbol.repository_id == repository_id)
    ) or 0
    ollama_available = OllamaService().is_available()

    repository_status = str(repository.status)
    git_status = (
        "ready" if repository.head_sha and repository_status == "ready" else repository_status
    )
    code_status = (
        "ready"
        if repository_status == "ready" and file_count
        else (repository_status if repository_status != "ready" else "not_indexed")
    )
    code_detail = f"{file_count} files, {symbol_count} symbols" if file_count else None
    return RepositorySystemStatus(
        repository=repository_status,
        active_job_id=current_job.id if current_job else None,
        git=RepositorySubsystemStatus(status=git_status, indexed_sha=repository.head_sha),
        code=RepositorySubsystemStatus(
            status=code_status, indexed_sha=repository.head_sha, detail=code_detail
        ),
        history=RepositorySubsystemStatus(
            status=_state_status(
                repository.history_index_status,
                repository.history_indexed_through_sha,
                repository.head_sha,
            ),
            indexed_sha=repository.history_indexed_through_sha,
            progress=(100 if repository.history_index_status == "ready" else None),
            limited=repository.history_limited,
        ),
        github=RepositorySubsystemStatus(
            status=_state_status(
                github.status if github else None,
                None,
                None,
                error=github.sync_error if github else None,
            ),
            progress=github.progress if github else None,
            current_step=github.current_step if github else None,
            error=github.sync_error if github else None,
            limited=github.github_index_limited if github else False,
            last_synced_at=github.last_synced_at if github else None,
            detail=(
                f"{github.rate_limit_remaining} GitHub requests remaining"
                if github and github.rate_limit_remaining is not None
                else None
            ),
        ),
        graph=RepositorySubsystemStatus(
            status=_state_status(
                graph.status if graph else None,
                graph.last_indexed_sha if graph else None,
                repository.head_sha,
                error=graph.error if graph else None,
            ),
            indexed_sha=graph.last_indexed_sha if graph else None,
            progress=graph.progress if graph else None,
            current_step=graph.current_step if graph else None,
            error=graph.error if graph else None,
            limited=graph.graph_limited if graph else False,
            job_id=graph.job_id if graph else None,
        ),
        ai=RepositorySubsystemStatus(
            status=(
                "unavailable"
                if not ollama_available
                else _state_status(
                    ai.status if ai else None,
                    ai.last_indexed_sha if ai else None,
                    repository.head_sha,
                    error=ai.error if ai else None,
                )
            ),
            indexed_sha=ai.last_indexed_sha if ai else None,
            progress=ai.progress if ai else None,
            current_step=ai.current_step if ai else None,
            error=ai.error if ai else None,
            job_id=ai.job_id if ai else None,
            ollama_available=ollama_available,
            detail=(f"{ai.embedded_documents}/{ai.documents} evidence documents" if ai else None),
        ),
        archaeology=RepositorySubsystemStatus(
            status=_state_status(
                archaeology.status if archaeology else None,
                archaeology.last_indexed_sha if archaeology else None,
                repository.head_sha,
                error=archaeology.error if archaeology else None,
            ),
            indexed_sha=archaeology.last_indexed_sha if archaeology else None,
            progress=archaeology.progress if archaeology else None,
            current_step=archaeology.current_step if archaeology else None,
            error=archaeology.error if archaeology else None,
            job_id=archaeology.job_id if archaeology else None,
        ),
        architecture_history=RepositorySubsystemStatus(
            status=_state_status(
                architecture_history.status if architecture_history else None,
                architecture_history.last_indexed_sha if architecture_history else None,
                repository.head_sha,
                error=architecture_history.error if architecture_history else None,
            ),
            indexed_sha=architecture_history.last_indexed_sha if architecture_history else None,
            progress=architecture_history.progress if architecture_history else None,
            current_step=architecture_history.current_step if architecture_history else None,
            error=architecture_history.error if architecture_history else None,
            limited=architecture_history.limited if architecture_history else False,
            job_id=architecture_history.job_id if architecture_history else None,
        ),
    )


@router.post(
    "/repositories/{repository_id}/refresh", response_model=SubmissionResponse, status_code=202
)
def refresh(repository_id: UUID, session: Database) -> SubmissionResponse:
    repository = get_repository(session, repository_id)
    return submit_repository(session, repository.url, refresh=True, repository_id=repository_id)


@router.get("/jobs/{job_id}", response_model=AnalysisJobRead)
def job_detail(job_id: UUID, session: Database) -> AnalysisJob:
    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise IngestionError("JOB_NOT_FOUND", "Analysis job not found.", 404)
    return job


@router.get("/repositories/{repository_id}/commits", response_model=CommitPage)
def commits(
    repository_id: UUID,
    session: Database,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CommitPage:
    repository = ready(session, repository_id)
    items = session.scalars(
        select(Commit)
        .where(Commit.repository_id == repository_id)
        .order_by(Commit.committed_at.desc(), Commit.sha)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return CommitPage(
        items=[CommitSummary.model_validate(item) for item in items],
        page=page,
        page_size=page_size,
        total=repository.commit_count,
    )


@router.get("/repositories/{repository_id}/commits/{sha}", response_model=CommitDetail)
def commit_detail(repository_id: UUID, sha: str, session: Database) -> CommitDetail:
    commit = stored_commit(session, repository_id, sha)
    parents = list(
        session.scalars(
            select(CommitParent.parent_sha)
            .where(CommitParent.commit_id == commit.id)
            .order_by(CommitParent.parent_order)
        )
    )
    changes = session.scalars(
        select(FileChange)
        .where(FileChange.commit_id == commit.id)
        .order_by(FileChange.change_order)
    )
    return CommitDetail(
        **CommitSummary.model_validate(commit).model_dump(),
        parents=parents,
        changes=[FileChangeRead.model_validate(change) for change in changes],
    )


@router.get("/repositories/{repository_id}/commits/{sha}/diff", response_model=DiffResponse)
def diff(repository_id: UUID, sha: str, session: Database) -> DiffResponse:
    stored_commit(session, repository_id, sha)
    git = GitService()
    content, truncated = git.get_commit_diff(git.storage.path(repository_id), sha)
    return DiffResponse(content=content, truncated=truncated)


@router.get("/repositories/{repository_id}/stats", response_model=RepositoryStats)
def stats(repository_id: UUID, session: Database) -> RepositoryStats:
    ready(session, repository_id)
    row = session.execute(
        select(
            func.count(Commit.id),
            func.count(Commit.id).filter(Commit.is_merge_commit),
            func.count(distinct(func.lower(Commit.author_email))),
            func.coalesce(func.sum(Commit.insertions), 0),
            func.coalesce(func.sum(Commit.deletions), 0),
            func.min(Commit.committed_at),
            func.max(Commit.committed_at),
        ).where(Commit.repository_id == repository_id)
    ).one()
    paths = union(
        select(FileChange.old_path.label("path")).where(FileChange.repository_id == repository_id),
        select(FileChange.new_path.label("path")).where(FileChange.repository_id == repository_id),
    ).subquery()
    count = (
        session.scalar(select(func.count()).select_from(paths).where(paths.c.path.is_not(None)))
        or 0
    )
    return RepositoryStats(
        total_commits=row[0],
        merge_commits=row[1],
        contributors=row[2],
        historical_paths=count,
        insertions=row[3],
        deletions=row[4],
        first_commit_at=row[5],
        latest_commit_at=row[6],
    )


@router.get("/repositories/{repository_id}/tags", response_model=list[TagRead])
def tags(repository_id: UUID, session: Database) -> list[Tag]:
    ready(session, repository_id)
    return list(
        session.scalars(select(Tag).where(Tag.repository_id == repository_id).order_by(Tag.name))
    )
