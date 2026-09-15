from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.git import SubmissionResponse
from app.schemas.github import (
    CommitContext,
    GitHubStatus,
    IssueDetail,
    IssuePage,
    PullRequestDetail,
    PullRequestPage,
    SymbolContext,
)
from app.services.github.service import GitHubService
from app.services.repositories import submit_github_sync

router = APIRouter(tags=["GitHub context"])
Database = Annotated[Session, Depends(get_session)]
State = Literal["open", "closed", "all"]


@router.post(
    "/repositories/{repository_id}/github/sync",
    response_model=SubmissionResponse,
    status_code=202,
)
def sync_github(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_github_sync(session, repository_id)


@router.get("/repositories/{repository_id}/github/status", response_model=GitHubStatus)
def github_status(repository_id: UUID, session: Database) -> GitHubStatus:
    return GitHubService(session).status(repository_id)


@router.get("/repositories/{repository_id}/pull-requests", response_model=PullRequestPage)
def pull_requests(
    repository_id: UUID,
    session: Database,
    state: State = "all",
    search: Annotated[str | None, Query(max_length=200)] = None,
    author: Annotated[str | None, Query(max_length=200)] = None,
    label: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> PullRequestPage:
    return GitHubService(session).pull_requests(
        repository_id, state, search, author, label, page, page_size
    )


@router.get(
    "/repositories/{repository_id}/pull-requests/{number}",
    response_model=PullRequestDetail,
)
def pull_request(repository_id: UUID, number: int, session: Database) -> PullRequestDetail:
    return GitHubService(session).pull_request(repository_id, number)


@router.get("/repositories/{repository_id}/issues", response_model=IssuePage)
def issues(
    repository_id: UUID,
    session: Database,
    state: State = "all",
    search: Annotated[str | None, Query(max_length=200)] = None,
    author: Annotated[str | None, Query(max_length=200)] = None,
    label: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> IssuePage:
    return GitHubService(session).issues(
        repository_id, state, search, author, label, page, page_size
    )


@router.get("/repositories/{repository_id}/issues/{number}", response_model=IssueDetail)
def issue(repository_id: UUID, number: int, session: Database) -> IssueDetail:
    return GitHubService(session).issue(repository_id, number)


@router.get("/repositories/{repository_id}/commits/{sha}/context", response_model=CommitContext)
def commit_context(repository_id: UUID, sha: str, session: Database) -> CommitContext:
    return GitHubService(session).commit_context(repository_id, sha)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/context",
    response_model=SymbolContext,
)
def symbol_context(repository_id: UUID, lineage_id: UUID, session: Database) -> SymbolContext:
    return GitHubService(session).symbol_context(repository_id, lineage_id)
