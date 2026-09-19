from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.investigation import (
    BisectClassification,
    BisectCreate,
    CandidateFeedbackWrite,
    InvestigationCreate,
    InvestigationExplain,
    SZZRequest,
)
from app.services.investigation.regression import RegressionAnalysisService
from app.services.investigation.report import InvestigationReportService
from app.services.investigation.szz import SZZAnalysisService

router = APIRouter(tags=["bug investigation"])
Database = Annotated[Session, Depends(get_session)]


@router.post("/repositories/{repository_id}/investigations", status_code=202)
def create_investigation(
    repository_id: UUID, payload: InvestigationCreate, session: Database
) -> dict[str, Any]:
    return InvestigationReportService(session).create(repository_id, payload)


@router.get("/repositories/{repository_id}/investigations/{investigation_id}")
def investigation(
    repository_id: UUID, investigation_id: UUID, session: Database
) -> dict[str, Any]:
    return InvestigationReportService(session).read(repository_id, investigation_id)


@router.get("/repositories/{repository_id}/investigations/{investigation_id}/candidates")
def candidates(
    repository_id: UUID,
    investigation_id: UUID,
    session: Database,
    file: str | None = None,
    symbol: str | None = None,
    min_score: Annotated[float, Query(ge=0, le=1)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict[str, Any]]:
    return InvestigationReportService(session).candidates(
        repository_id, investigation_id, file, symbol, min_score, limit
    )


@router.post("/repositories/{repository_id}/investigations/{investigation_id}/feedback")
def candidate_feedback(
    repository_id: UUID,
    investigation_id: UUID,
    payload: CandidateFeedbackWrite,
    session: Database,
) -> dict[str, Any]:
    return InvestigationReportService(session).feedback(
        repository_id, investigation_id, payload.commit_sha, payload.result
    )


@router.post("/repositories/{repository_id}/investigations/{investigation_id}/explain")
def explain_investigation(
    repository_id: UUID,
    investigation_id: UUID,
    payload: InvestigationExplain,
    session: Database,
) -> dict[str, Any]:
    return InvestigationReportService(session).explain(
        repository_id, investigation_id, payload.question
    )


@router.post("/repositories/{repository_id}/investigations/szz")
def szz(
    repository_id: UUID, payload: SZZRequest, session: Database
) -> dict[str, Any]:
    return SZZAnalysisService(session, get_settings()).analyze(
        repository_id, payload.fix_commit_sha, payload.file_path, payload.lineage_id
    )


@router.get("/repositories/{repository_id}/line-history")
def line_history(
    repository_id: UUID,
    session: Database,
    path: str,
    line: Annotated[int, Query(ge=1)],
    commit_sha: str | None = None,
) -> dict[str, Any]:
    return InvestigationReportService(session).line_history(
        repository_id, path, line, commit_sha
    )


@router.post("/repositories/{repository_id}/investigations/bisect", status_code=201)
def create_bisect(
    repository_id: UUID, payload: BisectCreate, session: Database
) -> dict[str, Any]:
    return RegressionAnalysisService(session, get_settings()).create_bisect(
        repository_id, payload.known_good, payload.known_bad
    )


@router.post("/repositories/{repository_id}/investigations/bisect/{bisect_id}/classify")
def classify_bisect(
    repository_id: UUID,
    bisect_id: UUID,
    payload: BisectClassification,
    session: Database,
) -> dict[str, Any]:
    return RegressionAnalysisService(session, get_settings()).classify(
        repository_id, bisect_id, payload.commit_sha, payload.result
    )
