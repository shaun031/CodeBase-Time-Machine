from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.code import (
    CodeStats,
    FileContent,
    FileRead,
    FileTreeNode,
    ImportPage,
    SymbolDetail,
    SymbolPage,
    SymbolRead,
)
from app.schemas.git import SubmissionResponse
from app.services.code_index import CodeIndexService
from app.services.files import FileService
from app.services.repositories import submit_code_reindex
from app.services.symbols import SymbolService

router = APIRouter(tags=["code explorer"])
Database = Annotated[Session, Depends(get_session)]


@router.get("/repositories/{repository_id}/code/stats", response_model=CodeStats)
def code_stats(repository_id: UUID, session: Database) -> CodeStats:
    return CodeIndexService.calculate_repository_code_stats(session, repository_id)


@router.post(
    "/repositories/{repository_id}/code/reindex", response_model=SubmissionResponse, status_code=202
)
def reindex(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_code_reindex(session, repository_id)


@router.get("/repositories/{repository_id}/files", response_model=list[FileTreeNode])
def files(
    repository_id: UUID, session: Database, directory: str | None = None
) -> list[FileTreeNode]:
    return FileService(session).get_file_tree(repository_id, directory)


@router.get(
    "/repositories/{repository_id}/files/{file_path:path}/content", response_model=FileContent
)
def file_content(
    repository_id: UUID,
    file_path: str,
    session: Database,
    start_line: Annotated[int | None, Query(ge=1)] = None,
    end_line: Annotated[int | None, Query(ge=1)] = None,
) -> FileContent:
    return FileService(session).get_content(repository_id, file_path, start_line, end_line)


@router.get(
    "/repositories/{repository_id}/files/{file_path:path}/symbols", response_model=list[SymbolRead]
)
def file_symbols(repository_id: UUID, file_path: str, session: Database) -> list[SymbolRead]:
    return SymbolService(session).for_file(repository_id, file_path)


@router.get("/repositories/{repository_id}/files/{file_path:path}", response_model=FileRead)
def file_metadata(repository_id: UUID, file_path: str, session: Database) -> FileRead:
    return FileService.read(FileService(session).get_file(repository_id, file_path))


@router.get("/repositories/{repository_id}/symbols", response_model=SymbolPage)
def symbols(
    repository_id: UUID,
    session: Database,
    search: Annotated[str | None, Query(max_length=200)] = None,
    kind: str | None = None,
    language: str | None = None,
    file: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SymbolPage:
    return SymbolService(session).search(
        repository_id, search, kind, language, file, page, page_size
    )


@router.get("/repositories/{repository_id}/symbols/{symbol_id}", response_model=SymbolDetail)
def symbol_detail(repository_id: UUID, symbol_id: UUID, session: Database) -> SymbolDetail:
    return SymbolService(session).detail(repository_id, symbol_id)


@router.get("/repositories/{repository_id}/imports", response_model=ImportPage)
def imports(
    repository_id: UUID,
    session: Database,
    file: str | None = None,
    resolved: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ImportPage:
    return SymbolService(session).imports(repository_id, file, resolved, page, page_size)
