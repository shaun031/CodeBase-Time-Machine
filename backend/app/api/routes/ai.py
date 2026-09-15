import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AIIndexState
from app.db.session import get_session
from app.schemas.ai import (
    AIStatus,
    AskRequest,
    AskResponse,
    EvidenceSearchResponse,
    RepositoryAIStatus,
)
from app.schemas.git import SubmissionResponse
from app.services.ai.archaeology import SoftwareArchaeologyService
from app.services.ai.ollama import OllamaService
from app.services.ai.retrieval import EvidenceRetriever
from app.services.repositories import get_repository, submit_ai_reindex

router = APIRouter(tags=["local AI"])
Database = Annotated[Session, Depends(get_session)]


@router.get("/system/ai-status", response_model=AIStatus)
def ai_status() -> AIStatus:
    return AIStatus.model_validate(OllamaService().status())


@router.get("/repositories/{repository_id}/ai/status", response_model=RepositoryAIStatus)
def repository_ai_status(repository_id: UUID, session: Database) -> RepositoryAIStatus:
    repository = get_repository(session, repository_id)
    state = session.get(AIIndexState, repository_id)
    available = OllamaService().is_available()
    settings = get_settings()
    if state is None:
        return RepositoryAIStatus(
            status="not_indexed",
            progress=None,
            current_step=None,
            documents=0,
            embedded_documents=0,
            embedding_model=None,
            embedding_dimension=None,
            last_indexed_sha=None,
            index_stale=False,
            ollama_available=available,
            error=None,
            job_id=None,
            completed_at=None,
        )
    stale = (
        state.last_indexed_sha != repository.head_sha
        or state.embedding_model != settings.ollama_embedding_model
        or state.embedding_version is None
    )
    status = (
        "incompatible"
        if state.status == "ready" and state.embedding_model != settings.ollama_embedding_model
        else state.status
    )
    return RepositoryAIStatus(
        status=status,
        progress=state.progress,
        current_step=state.current_step,
        documents=state.documents,
        embedded_documents=state.embedded_documents,
        embedding_model=state.embedding_model,
        embedding_dimension=state.embedding_dimension,
        last_indexed_sha=state.last_indexed_sha,
        index_stale=stale,
        ollama_available=available,
        error=state.error,
        job_id=state.job_id,
        completed_at=state.completed_at.isoformat() if state.completed_at else None,
    )


@router.post(
    "/repositories/{repository_id}/ai/reindex",
    response_model=SubmissionResponse,
    status_code=202,
)
def reindex_ai(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_ai_reindex(session, repository_id)


@router.post("/repositories/{repository_id}/ask", response_model=AskResponse)
def ask(repository_id: UUID, body: AskRequest, session: Database) -> AskResponse:
    return SoftwareArchaeologyService(session).ask(repository_id, body)


@router.get("/repositories/{repository_id}/ai/search", response_model=EvidenceSearchResponse)
def search_evidence(
    repository_id: UUID,
    session: Database,
    q: Annotated[str, Query(min_length=2, max_length=1000)],
    types: Annotated[str | None, Query(max_length=500)] = None,
    top_k: Annotated[int, Query(ge=1, le=50)] = 10,
) -> EvidenceSearchResponse:
    get_repository(session, repository_id)
    started = time.perf_counter()
    request = AskRequest(question=q)
    items, _, _ = EvidenceRetriever(session).retrieve(repository_id, request, top_k=top_k)
    allowed = {item.strip() for item in types.split(",")} if types else None
    if allowed:
        items = [item for item in items if item.type in allowed]
    return EvidenceSearchResponse(
        items=items[:top_k], query_ms=round((time.perf_counter() - started) * 1000, 2)
    )
