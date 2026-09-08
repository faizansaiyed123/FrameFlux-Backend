from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MediaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    original_filename: str
    stored_filename: str
    media_type: str
    mime_type: str
    file_size: int
    project_id: UUID | None
    processing_status: str
    processed_filename: str | None
    processing_error: str | None

    duration: float | None = None
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    fps: str | None = None

    created_at: datetime


class MediaConvertRequest(BaseModel):
    format: str

    width: int | None = None
    height: int | None = None
    fps: int | None = None

    video_bitrate: str | None = None
    audio_bitrate: str | None = None

    video_codec: str | None = None
    audio_codec: str | None = None

    aspect_ratio: str | None = None
    quality: int | None = None
    resolution: str | None = None


class MediaEditRequest(BaseModel):
    operation: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class ClipInterval(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class MediaSplitRequest(BaseModel):
    split_points: list[float] = Field(min_length=1)


class MediaClipsRequest(BaseModel):
    clips: list[ClipInterval] = Field(min_length=1)


class MediaTransformRequest(BaseModel):
    operation: str

    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)

    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)

    angle: int | None = None

    speed: float | None = Field(default=None, gt=0)


class MediaFreezeFrameRequest(BaseModel):
    timestamp: float = Field(ge=0)
    duration: float = Field(default=1.0, gt=0)


# Backward compatibility alias
MediaFreezeRequest = MediaFreezeFrameRequest


class OverlayItem(BaseModel):
    operation: str  # "text", "image", "watermark"
    text: str | None = None
    image_filename: str | None = None
    x: int = 10
    y: int = 10
    font_size: int = 32
    opacity: float = Field(default=1.0, ge=0, le=1)


class MediaOverlayRequest(BaseModel):
    # Single overlay fields (backward compatibility)
    operation: str | None = None
    text: str | None = None
    image_filename: str | None = None
    x: int = 10
    y: int = 10
    font_size: int = 32
    opacity: float = Field(default=1.0, ge=0, le=1)

    # Multi-overlay field
    overlays: list[OverlayItem] | None = None


class MediaMergeRequest(BaseModel):
    media_ids: list[str] = Field(min_length=2)


# Resumable upload schemas


class ResumableInitRequest(BaseModel):
    original_filename: str
    total_size: int
    chunk_size: int | None = None


class ResumableInitResponse(BaseModel):
    upload_id: str


class ChunkUploadResponse(BaseModel):
    detail: str = "Chunk stored"


class ActionResponse(BaseModel):
    detail: str


class MediaProcessingStatusResponse(BaseModel):
    media_id: str
    status: str = Field(description="pending, queued, processing, completed, or failed")
    progress: int = Field(default=0, ge=0, le=100, description="Processing progress from 0 to 100")
    stage: str | None = Field(default=None, description="Human-readable stage description")
    job_id: str | None = Field(default=None, description="Latest background job ID")
    processed_filename: str | None = None
    error: str | None = None
