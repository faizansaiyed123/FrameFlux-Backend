from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    stored_filename: str
    media_type: str
    mime_type: str
    file_size: int

    project_id: UUID | None
    processing_status: str
    processed_filename: str | None
    processing_error: str | None

    created_at: datetime