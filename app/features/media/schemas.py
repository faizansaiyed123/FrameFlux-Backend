from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict,Field


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

class MediaConvertRequest(BaseModel):
    format: str = "mp4"

    resolution: str | None = None
    custom_width: int | None = Field(default=None, ge=16)
    custom_height: int | None = Field(default=None, ge=16)

    fps: float | None = Field(default=None, gt=0, le=240)

    video_codec: str | None = None

    quality: int | None = Field(default=None, ge=0, le=51)

    bitrate: str | None = None

    aspect_ratio: str | None = None



class MediaEditRequest(BaseModel):
    operation: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
