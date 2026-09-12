from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ProcessingHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    media_id: UUID
    operation: str
    status: str
    settings: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
