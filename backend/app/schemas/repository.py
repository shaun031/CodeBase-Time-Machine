from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models.repository import RepositoryStatus


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    provider: str
    owner: str
    name: str
    full_name: str
    url: str
    default_branch: str | None
    status: RepositoryStatus
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None
    indexing_error: str | None
