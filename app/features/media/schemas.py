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

    project_id: UUID | None = None

    processing_status: str
    processed_filename: str | None = None
    processing_error: str | None = None

    duration: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    fps: str | None = None

    created_at: datetime
