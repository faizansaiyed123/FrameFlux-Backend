from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal


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
    folder: str | None = None
    tags: list[str] | None = None
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

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value):
        if isinstance(value, str):
            import json
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
        return value


class MediaConvertRequest(BaseModel):
    format: str

    width: int | None = None
    height: int | None = None
    fps: int | None = None
    fps_preset: str | None = Field(default=None, description="Preset FPS: 24, 25, 30, 50, 60")

    video_bitrate: str | None = None
    audio_bitrate: str | None = None

    video_codec: str | None = None
    audio_codec: str | None = None

    aspect_ratio: str | None = None
    aspect_ratio_preset: str | None = Field(default=None, description="Preset aspect ratio: 16:9, 9:16, 4:3, 1:1")
    quality: int | None = None
    resolution: str | None = None
    target_size_mb: int | None = Field(default=None, ge=1, description="Target output size in megabytes for compression")


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


MediaFreezeRequest = MediaFreezeFrameRequest


class OverlayItem(BaseModel):
    operation: str
    text: str | None = None
    image_filename: str | None = None
    x: int = 10
    y: int = 10
    font_size: int = 32
    opacity: float = Field(default=1.0, ge=0, le=1)


class MediaOverlayRequest(BaseModel):
    operation: str | None = None
    text: str | None = None
    image_filename: str | None = None
    x: int = 10
    y: int = 10
    font_size: int = 32
    opacity: float = Field(default=1.0, ge=0, le=1)

    overlays: list[OverlayItem] | None = None


class MediaMergeRequest(BaseModel):
    media_ids: list[str] = Field(min_length=2)


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


class BatchDownloadRequest(BaseModel):
    media_ids: list[UUID] = Field(min_length=1, max_length=50)


class MediaProcessingStatusResponse(BaseModel):
    media_id: str
    status: str = Field(description="pending, queued, processing, completed, or failed")
    progress: int = Field(default=0, ge=0, le=100, description="Processing progress from 0 to 100")
    stage: str | None = Field(default=None, description="Human-readable stage description")
    job_id: str | None = Field(default=None, description="Latest background job ID")
    processed_filename: str | None = None
    error: str | None = None


class UploadProgressResponse(BaseModel):
    upload_id: str
    user_id: str
    filename: str
    status: str
    progress: int
    total_size: str | None = None
    uploaded_size: str | None = None
    error: str | None = None


class TrimOperation(BaseModel):
    type: Literal["trim"] = "trim"
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class CutOperation(BaseModel):
    type: Literal["cut"] = "cut"
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class CropOperation(BaseModel):
    type: Literal["crop"] = "crop"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)


class ResizeOperation(BaseModel):
    type: Literal["resize"] = "resize"
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class RotateOperation(BaseModel):
    type: Literal["rotate"] = "rotate"
    angle: int = Field(ge=0, le=360)


class FlipOperation(BaseModel):
    type: Literal["flip"] = "flip"
    direction: Literal["horizontal", "vertical"] = "horizontal"


class SpeedOperation(BaseModel):
    type: Literal["speed"] = "speed"
    speed: float = Field(gt=0)


class FreezeOperation(BaseModel):
    type: Literal["freeze"] = "freeze"
    timestamp: float = Field(ge=0)
    duration: float = Field(gt=0)


class TextOverlayOperation(BaseModel):
    type: Literal["text_overlay"] = "text_overlay"
    text: str
    x: int = Field(default=10, ge=0)
    y: int = Field(default=10, ge=0)
    font_size: int = Field(default=32, gt=0)
    font_color: str = Field(default="white")
    box_color: str = Field(default="black@0.65")


class ImageOverlayOperation(BaseModel):
    type: Literal["image_overlay"] = "image_overlay"
    image_path: str
    x: int = Field(default=10, ge=0)
    y: int = Field(default=10, ge=0)
    opacity: float = Field(default=1.0, ge=0, le=1)


class WatermarkOperation(BaseModel):
    type: Literal["watermark"] = "watermark"
    image_path: str
    x: int = Field(default=10, ge=0)
    y: int = Field(default=10, ge=0)
    opacity: float = Field(default=1.0, ge=0, le=1)


class ConvertOperation(BaseModel):
    type: Literal["convert"] = "convert"
    format: str
    video_codec: str | None = None
    audio_codec: str | None = None
    video_bitrate: str | None = None
    audio_bitrate: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps: int | None = Field(default=None, gt=0)
    quality: int | None = Field(default=None, ge=0, le=51)
    aspect_ratio: str | None = None


class ExtractAudioOperation(BaseModel):
    type: Literal["extract_audio"] = "extract_audio"
    format: Literal["mp3", "wav", "aac", "flac", "ogg", "m4a", "opus"] = "mp3"
    bitrate: str | None = None
    sample_rate: int | None = Field(default=None, gt=0)


class MergeOperation(BaseModel):
    type: Literal["merge"] = "merge"
    media_ids: list[str] = Field(min_length=2)


class AudioVolumeOperation(BaseModel):
    type: Literal["audio_volume"] = "audio_volume"
    volume: float = Field(ge=0, le=10)
    fade_in: float | None = Field(default=None, ge=0)
    fade_out: float | None = Field(default=None, ge=0)


class AudioReplaceOperation(BaseModel):
    type: Literal["audio_replace"] = "audio_replace"
    audio_path: str
    fade_in: float | None = Field(default=None, ge=0)
    fade_out: float | None = Field(default=None, ge=0)


ProcessingOperation = (
    TrimOperation
    | CutOperation
    | CropOperation
    | ResizeOperation
    | RotateOperation
    | FlipOperation
    | SpeedOperation
    | FreezeOperation
    | TextOverlayOperation
    | ImageOverlayOperation
    | WatermarkOperation
    | ConvertOperation
    | ExtractAudioOperation
    | MergeOperation
    | AudioVolumeOperation
    | AudioReplaceOperation
)


class ProcessingRequest(BaseModel):
    media_id: str
    operations: list[ProcessingOperation] = Field(min_length=1)
