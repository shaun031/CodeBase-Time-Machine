from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.architecture_history import (
    ArchitectureBaselineWrite,
    ArchitectureHistoryStatus,
    ArchitectureRuleRead,
    ArchitectureRuleWrite,
    ArchitectureSnapshotSummary,
    RuleValidationRequest,
)
from app.schemas.git import SubmissionResponse
from app.services.architecture_history.service import ArchitectureHistoryService
from app.services.repositories import submit_architecture_history_reindex

router = APIRouter(tags=["architecture evolution"])
Database = Annotated[Session, Depends(get_session)]


@router.get("/repositories/{repository_id}/architecture/history/status", response_model=ArchitectureHistoryStatus)
def status(repository_id: UUID, session: Database) -> dict[str, Any]:
    return ArchitectureHistoryService(session).status(repository_id)


@router.post("/repositories/{repository_id}/architecture/history/reindex", response_model=SubmissionResponse, status_code=202)
def reindex(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_architecture_history_reindex(session, repository_id)


@router.get("/repositories/{repository_id}/architecture/snapshots", response_model=list[ArchitectureSnapshotSummary])
def snapshots(repository_id: UUID, session: Database, from_date: datetime | None = None, to_date: datetime | None = None, tag: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 200) -> list[dict[str, Any]]:
    return ArchitectureHistoryService(session).snapshots(repository_id, from_date, to_date, tag, limit)


@router.get("/repositories/{repository_id}/architecture/at/{commit_sha}")
def architecture_at(repository_id: UUID, commit_sha: str, session: Database) -> dict[str, Any]:
    return ArchitectureHistoryService(session).graph_at(repository_id, commit_sha)


@router.get("/repositories/{repository_id}/architecture/compare")
def compare(repository_id: UUID, session: Database, from_commit: str | None = None, to_commit: str | None = None, from_snapshot_id: UUID | None = None, to_snapshot_id: UUID | None = None, from_tag: str | None = None, to_tag: str | None = None) -> dict[str, Any]:
    return ArchitectureHistoryService(session).compare(repository_id, from_commit=from_commit, to_commit=to_commit, from_snapshot_id=from_snapshot_id, to_snapshot_id=to_snapshot_id, from_tag=from_tag, to_tag=to_tag)


@router.get("/repositories/{repository_id}/architecture/evolution")
def evolution(
    repository_id: UUID,
    session: Database,
    event_type: str | None = None,
    module: str | None = None,
    component: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict[str, Any]]:
    return ArchitectureHistoryService(session).evolution(
        repository_id, event_type, module, component, from_date, to_date, limit
    )


@router.get("/repositories/{repository_id}/architecture/trends")
def trends(repository_id: UUID, session: Database, limit: Annotated[int, Query(ge=2, le=500)] = 500) -> dict[str, Any]:
    return ArchitectureHistoryService(session).trends(repository_id, limit)


@router.get("/repositories/{repository_id}/architecture/drift")
def drift(repository_id: UUID, session: Database, baseline_id: UUID | None = None, commit_sha: str | None = None) -> dict[str, Any]:
    return ArchitectureHistoryService(session).drift(repository_id, baseline_id, commit_sha)


@router.get("/repositories/{repository_id}/architecture/baselines")
def baselines(repository_id: UUID, session: Database) -> list[dict[str, Any]]:
    return ArchitectureHistoryService(session).baselines(repository_id)


@router.post("/repositories/{repository_id}/architecture/baselines", status_code=201)
def create_baseline(repository_id: UUID, payload: ArchitectureBaselineWrite, session: Database) -> dict[str, Any]:
    return ArchitectureHistoryService(session).create_baseline(repository_id, payload)


@router.delete("/repositories/{repository_id}/architecture/baselines/{baseline_id}", status_code=204)
def delete_baseline(repository_id: UUID, baseline_id: UUID, session: Database) -> Response:
    ArchitectureHistoryService(session).delete_baseline(repository_id, baseline_id)
    return Response(status_code=204)


@router.get("/repositories/{repository_id}/architecture/rules", response_model=list[ArchitectureRuleRead])
def rules(repository_id: UUID, session: Database) -> list[Any]:
    return ArchitectureHistoryService(session).rules(repository_id)


@router.post("/repositories/{repository_id}/architecture/rules", response_model=ArchitectureRuleRead, status_code=201)
def create_rule(repository_id: UUID, payload: ArchitectureRuleWrite, session: Database) -> Any:
    return ArchitectureHistoryService(session).save_rule(repository_id, payload)


@router.put("/repositories/{repository_id}/architecture/rules/{rule_id}", response_model=ArchitectureRuleRead)
def update_rule(repository_id: UUID, rule_id: UUID, payload: ArchitectureRuleWrite, session: Database) -> Any:
    return ArchitectureHistoryService(session).save_rule(repository_id, payload, rule_id)


@router.delete("/repositories/{repository_id}/architecture/rules/{rule_id}", status_code=204)
def delete_rule(repository_id: UUID, rule_id: UUID, session: Database) -> Response:
    ArchitectureHistoryService(session).delete_rule(repository_id, rule_id)
    return Response(status_code=204)


@router.post("/repositories/{repository_id}/architecture/rules/validate")
def validate_rule(repository_id: UUID, payload: RuleValidationRequest, session: Database) -> dict[str, Any]:
    return ArchitectureHistoryService(session).validate_preview(repository_id, payload.rule, payload.commit_sha, payload.from_commit, payload.to_commit)


@router.get("/repositories/{repository_id}/architecture/violations")
def violations(
    repository_id: UUID,
    session: Database,
    status: str | None = None,
    rule: UUID | None = None,
    severity: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[dict[str, Any]]:
    return ArchitectureHistoryService(session).violations(
        repository_id, status, rule, severity, from_date, to_date, limit
    )
