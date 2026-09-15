from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.schemas.git import SubmissionResponse
from app.schemas.graph import (
    ArchitectureResponse,
    CouplingResponse,
    CycleResponse,
    DependencyPathResponse,
    GraphMetrics,
    GraphNodeDetail,
    GraphStatus,
    GraphView,
    ImpactResponse,
)
from app.services.graph.service import GraphService
from app.services.repositories import submit_graph_reindex

router = APIRouter(tags=["dependency graph"])
Database = Annotated[Session, Depends(get_session)]


@router.post(
    "/repositories/{repository_id}/graph/reindex",
    response_model=SubmissionResponse,
    status_code=202,
)
def reindex_graph(repository_id: UUID, session: Database) -> SubmissionResponse:
    return submit_graph_reindex(session, repository_id)


@router.get("/repositories/{repository_id}/graph/status", response_model=GraphStatus)
def graph_status(repository_id: UUID, session: Database) -> GraphStatus:
    return GraphService(session).status(repository_id)


@router.get("/repositories/{repository_id}/graph", response_model=GraphView)
def graph(
    repository_id: UUID,
    session: Database,
    level: Literal["module", "file", "symbol"] = "module",
    path: Annotated[str | None, Query(max_length=1000)] = None,
    node_type: Annotated[str | None, Query(max_length=40)] = None,
    edge_type: Annotated[str | None, Query(max_length=40)] = None,
    depth: Annotated[int, Query(ge=1, le=20)] = 2,
    max_nodes: Annotated[int, Query(ge=1, le=5000)] = 200,
) -> GraphView:
    del depth
    return GraphService(session).graph(repository_id, level, path, node_type, edge_type, max_nodes)


@router.get("/repositories/{repository_id}/graph/subgraph", response_model=GraphView)
def subgraph(
    repository_id: UUID,
    session: Database,
    node_id: UUID,
    direction: Literal["incoming", "outgoing", "both"] = "both",
    depth: Annotated[int, Query(ge=1, le=20)] = 2,
    edge_types: Annotated[str | None, Query(max_length=500)] = None,
) -> GraphView:
    selected = (
        {value.strip() for value in edge_types.split(",") if value.strip()} if edge_types else None
    )
    return GraphService(session).subgraph(repository_id, node_id, direction, depth, selected)


@router.get("/repositories/{repository_id}/graph/nodes/{node_id}", response_model=GraphNodeDetail)
def node_detail(repository_id: UUID, node_id: UUID, session: Database) -> GraphNodeDetail:
    return GraphService(session).node_detail(repository_id, node_id)


@router.get("/repositories/{repository_id}/graph/metrics", response_model=GraphMetrics)
def graph_metrics(repository_id: UUID, session: Database) -> GraphMetrics:
    return GraphService(session).metrics(repository_id)


@router.get("/repositories/{repository_id}/graph/cycles", response_model=CycleResponse)
def graph_cycles(
    repository_id: UUID,
    session: Database,
    level: Literal["file", "module"] = "file",
) -> CycleResponse:
    return GraphService(session).cycles(repository_id, level)


@router.get("/repositories/{repository_id}/graph/coupling", response_model=CouplingResponse)
def graph_coupling(
    repository_id: UUID,
    session: Database,
    level: Literal["file"] = "file",
    min_score: Annotated[float, Query(ge=0, le=1)] = 0.2,
    min_co_changes: Annotated[int, Query(ge=1)] = 2,
    path: Annotated[str | None, Query(max_length=1000)] = None,
) -> CouplingResponse:
    del level
    return GraphService(session).coupling(repository_id, min_score, min_co_changes, path)


@router.get("/repositories/{repository_id}/graph/path", response_model=DependencyPathResponse)
def graph_path(
    repository_id: UUID,
    session: Database,
    source_node_id: UUID,
    target_node_id: UUID,
) -> DependencyPathResponse:
    return GraphService(session).path(repository_id, source_node_id, target_node_id)


@router.get("/repositories/{repository_id}/architecture", response_model=ArchitectureResponse)
def architecture(repository_id: UUID, session: Database) -> ArchitectureResponse:
    return GraphService(session).architecture(repository_id)


@router.get("/repositories/{repository_id}/impact", response_model=ImpactResponse)
def impact(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    symbol_id: UUID | None = None,
    lineage_id: UUID | None = None,
    depth: Annotated[int, Query(ge=1, le=20)] = 2,
    include_coupling: bool = True,
) -> ImpactResponse:
    return GraphService(session).impact(
        repository_id, file_id, symbol_id, lineage_id, depth, include_coupling
    )
