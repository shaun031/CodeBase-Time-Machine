from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ArchitectureSelector(BaseModel):
    kind: Literal["layer", "component", "path_prefix", "module"]
    value: str = Field(min_length=1, max_length=1000)


class ArchitectureRuleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    rule_type: Literal["allowed_dependency", "forbidden_dependency", "forbidden_cycle"]
    source_selector: ArchitectureSelector
    target_selector: ArchitectureSelector | None = None
    severity: Literal["info", "warning", "error"] = "warning"
    enabled: bool = True


class ArchitectureRuleRead(ArchitectureRuleWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    repository_id: UUID
    created_at: datetime
    updated_at: datetime


class RuleValidationRequest(BaseModel):
    rule: ArchitectureRuleWrite
    commit_sha: str | None = Field(default=None, min_length=40, max_length=40)
    from_commit: str | None = Field(default=None, min_length=40, max_length=40)
    to_commit: str | None = Field(default=None, min_length=40, max_length=40)


class ArchitectureBaselineWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    snapshot_id: UUID | None = None
    commit_sha: str | None = Field(default=None, min_length=40, max_length=40)
    is_default: bool = False


class ArchitectureHistoryStatus(BaseModel):
    status: str
    progress: float | None
    current_step: str | None
    commits_examined: int
    snapshots_created: int
    events_detected: int
    cycles_detected: int
    violations_detected: int
    last_indexed_sha: str | None
    stale: bool
    limited: bool
    error: str | None
    job_id: UUID | None
    completed_at: datetime | None


class ArchitectureSnapshotSummary(BaseModel):
    id: UUID
    commit_sha: str
    short_sha: str
    committed_at: datetime
    tags: list[str]
    node_count: int
    edge_count: int
    module_count: int
    component_count: int
    cycle_count: int
    metrics: dict[str, Any]

