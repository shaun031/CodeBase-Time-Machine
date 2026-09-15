from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.analysis_job import JobStatus


class AnalysisJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    repository_id: UUID | None
    job_type: str
    status: JobStatus
    progress: float | None = Field(default=None, ge=0, le=100)
    current_step: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
