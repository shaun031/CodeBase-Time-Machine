from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import distinct, func, select, union
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.models import (
    AnalysisJob,
    Commit,
    CommitParent,
    FileChange,
    Repository,
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
