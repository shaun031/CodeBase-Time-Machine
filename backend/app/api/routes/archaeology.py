import json
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.ingestion_errors import IngestionError
from app.db.session import get_session
from app.schemas.archaeology import (
    ArchaeologyOverview,
    ArchaeologyStatus,
    ContributorResponse,
    DossierExplainResponse,
    DossierResponse,
    HistoricalSearchResponse,
    ProvenanceResponse,
    RelatedCodeRead,
    RewriteRead,
    VolatilityResponse,
)
from app.schemas.git import SubmissionResponse
from app.services.ai.ollama import OllamaService
from app.services.archaeology.service import ArchaeologyService
from app.services.repositories import submit_archaeology_reindex

router = APIRouter(tags=["software archaeology"])
Database = Annotated[Session, Depends(get_session)]


class _Summary(BaseModel):
    summary: str = Field(min_length=1, max_length=4000)


@router.get("/repositories/{repository_id}/archaeology/status", response_model=ArchaeologyStatus)
def status(repository_id: UUID, session: Database) -> ArchaeologyStatus:
    return ArchaeologyService(session).status(repository_id)


@router.post(
    "/repositories/{repository_id}/archaeology/reindex",
    response_model=SubmissionResponse,
    status_code=202,
)
def reindex(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_archaeology_reindex(session, repository_id)


@router.get(
    "/repositories/{repository_id}/archaeology/overview", response_model=ArchaeologyOverview
)
def overview(repository_id: UUID, session: Database) -> ArchaeologyOverview:
    return ArchaeologyService(session).overview(repository_id)


@router.get(
    "/repositories/{repository_id}/archaeology/volatility", response_model=VolatilityResponse
)
def volatility(
    repository_id: UUID,
    session: Database,
    level: Literal["file", "symbol"] = "symbol",
    sort: str = "volatility",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> VolatilityResponse:
    return ArchaeologyService(session).volatility(repository_id, level, sort, limit)


@router.get(
    "/repositories/{repository_id}/archaeology/contributors", response_model=ContributorResponse
)
def contributors(
    repository_id: UUID,
    session: Database,
    sort: Literal["commits", "files", "symbols", "recent"] = "commits",
) -> ContributorResponse:
    return ArchaeologyService(session).contributors(repository_id, sort)


@router.get(
    "/repositories/{repository_id}/archaeology/contributors-for", response_model=ContributorResponse
)
def contributors_for(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    symbol_id: UUID | None = None,
    lineage_id: UUID | None = None,
) -> ContributorResponse:
    return ArchaeologyService(session).contributors_for(
        repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
    )


@router.get(
    "/repositories/{repository_id}/archaeology/provenance", response_model=ProvenanceResponse
)
def provenance(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    symbol_id: UUID | None = None,
    lineage_id: UUID | None = None,
) -> ProvenanceResponse:
    return ArchaeologyService(session).provenance(
        repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
    )


@router.get(
    "/repositories/{repository_id}/archaeology/search", response_model=HistoricalSearchResponse
)
def search(
    repository_id: UUID,
    session: Database,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    type: Literal["symbol", "file", "deleted_symbol", "deleted_file", "all"] = "all",
    status: Literal["current", "deleted", "all"] = "all",
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> HistoricalSearchResponse:
    return ArchaeologyService(session).search(
        repository_id, q, type, status, from_date, to_date, page, page_size
    )


@router.get("/repositories/{repository_id}/archaeology/rewrites", response_model=list[RewriteRead])
def rewrites(
    repository_id: UUID,
    session: Database,
    file: Annotated[str | None, Query(max_length=1000)] = None,
    symbol: Annotated[str | None, Query(max_length=500)] = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> list[RewriteRead]:
    return ArchaeologyService(session).rewrites(
        repository_id, file=file, symbol=symbol, from_date=from_date, to_date=to_date
    )


@router.get(
    "/repositories/{repository_id}/archaeology/related-code", response_model=list[RelatedCodeRead]
)
def related_code(
    repository_id: UUID,
    session: Database,
    lineage_id: UUID,
    min_similarity: Annotated[float, Query(ge=0, le=1)] = 0.8,
    include_deleted: bool = True,
    include_historical: bool = True,
) -> list[RelatedCodeRead]:
    return ArchaeologyService(session).related_code(
        repository_id, lineage_id, min_similarity, include_deleted, include_historical
    )


@router.get("/repositories/{repository_id}/archaeology/dossier", response_model=DossierResponse)
def dossier(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    symbol_id: UUID | None = None,
    lineage_id: UUID | None = None,
) -> DossierResponse:
    return ArchaeologyService(session).dossier(
        repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
    )


@router.post(
    "/repositories/{repository_id}/archaeology/dossier/explain",
    response_model=DossierExplainResponse,
)
def explain_dossier(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    symbol_id: UUID | None = None,
    lineage_id: UUID | None = None,
) -> DossierExplainResponse:
    dossier_data = ArchaeologyService(session).dossier(
        repository_id, file_id=file_id, symbol_id=symbol_id, lineage_id=lineage_id
    )
    target = dossier_data.target
    citations = [
        {"id": "provenance", "description": "Deterministic provenance timeline"},
        {"id": "metrics", "description": "Derived age, churn, and volatility metrics"},
        {"id": "contributors", "description": "Git contribution records"},
    ]
    ollama = OllamaService()
    fallback = (
        f"{target.name} is {target.age_days} days old, has {target.change_count} "
        f"recorded changes and {target.rewrite_count} detected major rewrites. "
        f"Its volatility score is {target.volatility:.2f}."
    )
    if not ollama.is_available():
        return DossierExplainResponse(
            summary=fallback,
            citations=citations,
            ai_enriched=False,
            limitation="Ollama is unavailable; deterministic dossier facts remain available.",
        )
    prompt = (
        "Summarize only the JSON facts below in at most three sentences. "
        "Cite [provenance], [metrics], or [contributors] after every historical "
        "statement. Do not infer quality, expertise, copying, or organizational risk.\n"
        + json.dumps(dossier_data.model_dump(mode="json"), separators=(",", ":"))
    )
    try:
        generated = _Summary.model_validate_json(
            ollama.generate(
                [{"role": "user", "content": prompt}],
                format_schema=_Summary.model_json_schema(),
            )
        )
        if not any(f"[{item['id']}]" in generated.summary for item in citations):
            return DossierExplainResponse(
                summary=fallback,
                citations=citations,
                ai_enriched=False,
                limitation="The local model did not return grounded citations.",
            )
        return DossierExplainResponse(
            summary=generated.summary, citations=citations, ai_enriched=True
        )
    except (ValueError, ValidationError, IngestionError):
        return DossierExplainResponse(
            summary=fallback,
            citations=citations,
            ai_enriched=False,
            limitation="The local model did not return a valid grounded summary.",
        )
