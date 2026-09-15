from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.git import SubmissionResponse
from app.schemas.history import (
    BlameLineRead,
    FileHistoryRead,
    HistoricalFileContent,
    HistoricalSymbolSource,
    HistoryEventPage,
    HistoryStatus,
    LineageSearchPage,
    SymbolAtCommit,
    SymbolBlameSummary,
    SymbolEventRead,
    SymbolLineageRead,
    SymbolVersionCompare,
    SymbolVersionPage,
)
from app.services.history import HistoryService
from app.services.repositories import submit_history_reindex

router = APIRouter(tags=["historical analysis"])
Database = Annotated[Session, Depends(get_session)]


@router.post(
    "/repositories/{repository_id}/history/reindex",
    response_model=SubmissionResponse,
    status_code=202,
)
def reindex_history(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_history_reindex(session, repository_id)


@router.get("/repositories/{repository_id}/history/status", response_model=HistoryStatus)
def history_status(repository_id: UUID, session: Database) -> HistoryStatus:
    return HistoryService(session).status(repository_id)


@router.get("/repositories/{repository_id}/history/events", response_model=HistoryEventPage)
def repository_events(
    repository_id: UUID,
    session: Database,
    event_type: str | None = None,
    symbol_kind: str | None = None,
    file_path: str | None = None,
    author: Annotated[str | None, Query(max_length=200)] = None,
    from_commit: str | None = None,
    to_commit: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> HistoryEventPage:
    return HistoryService(session).repository_events(
        repository_id,
        event_type,
        symbol_kind,
        file_path,
        author,
        from_commit,
        to_commit,
        page,
        page_size,
    )


@router.get("/repositories/{repository_id}/history/lineages", response_model=LineageSearchPage)
def search_lineages(
    repository_id: UUID,
    session: Database,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LineageSearchPage:
    return HistoryService(session).search_lineages(repository_id, search, page, page_size)


@router.get(
    "/repositories/{repository_id}/symbols/{symbol_id}/history",
    response_model=SymbolLineageRead,
)
def symbol_history(repository_id: UUID, symbol_id: UUID, session: Database) -> SymbolLineageRead:
    return HistoryService(session).for_current_symbol(repository_id, symbol_id)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/versions",
    response_model=SymbolVersionPage,
)
def lineage_versions(
    repository_id: UUID,
    lineage_id: UUID,
    session: Database,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SymbolVersionPage:
    return HistoryService(session).versions(repository_id, lineage_id, page, page_size)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/events",
    response_model=list[SymbolEventRead],
)
def lineage_events(
    repository_id: UUID, lineage_id: UUID, session: Database
) -> list[SymbolEventRead]:
    return HistoryService(session).events(repository_id, lineage_id)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/versions/{version_id}/source",
    response_model=HistoricalSymbolSource,
)
def lineage_source(
    repository_id: UUID, lineage_id: UUID, version_id: UUID, session: Database
) -> HistoricalSymbolSource:
    return HistoryService(session).source(repository_id, lineage_id, version_id)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/compare",
    response_model=SymbolVersionCompare,
)
def compare_versions(
    repository_id: UUID,
    lineage_id: UUID,
    session: Database,
    from_version: UUID,
    to_version: UUID,
) -> SymbolVersionCompare:
    return HistoryService(session).compare(repository_id, lineage_id, from_version, to_version)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/at/{commit_sha}",
    response_model=SymbolAtCommit,
)
def lineage_at_commit(
    repository_id: UUID, lineage_id: UUID, commit_sha: str, session: Database
) -> SymbolAtCommit:
    return HistoryService(session).at_commit(repository_id, lineage_id, commit_sha)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}/blame",
    response_model=SymbolBlameSummary,
)
def lineage_blame(repository_id: UUID, lineage_id: UUID, session: Database) -> SymbolBlameSummary:
    return HistoryService(session).lineage_blame(repository_id, lineage_id)


@router.get(
    "/repositories/{repository_id}/lineages/{lineage_id}",
    response_model=SymbolLineageRead,
)
def lineage_detail(repository_id: UUID, lineage_id: UUID, session: Database) -> SymbolLineageRead:
    return HistoryService(session).lineage(repository_id, lineage_id)


@router.get("/repositories/{repository_id}/files/history", response_model=FileHistoryRead)
def file_history(repository_id: UUID, path: str, session: Database) -> FileHistoryRead:
    return HistoryService(session).file_history(repository_id, path)


@router.get("/repositories/{repository_id}/files/content-at", response_model=HistoricalFileContent)
def historical_file(
    repository_id: UUID, path: str, commit_sha: str, session: Database
) -> HistoricalFileContent:
    return HistoryService(session).content_at(repository_id, path, commit_sha)


@router.get("/repositories/{repository_id}/blame", response_model=list[BlameLineRead])
def blame(
    repository_id: UUID,
    path: str,
    session: Database,
    start_line: Annotated[int | None, Query(ge=1)] = None,
    end_line: Annotated[int | None, Query(ge=1)] = None,
) -> list[BlameLineRead]:
    return HistoryService(session).blame(repository_id, path, start_line, end_line)


@router.get(
    "/repositories/{repository_id}/commits/{commit_sha}/symbols",
    response_model=list[SymbolEventRead],
)
def commit_symbols(
    repository_id: UUID, commit_sha: str, session: Database
) -> list[SymbolEventRead]:
    return HistoryService(session).commit_events(repository_id, commit_sha)
