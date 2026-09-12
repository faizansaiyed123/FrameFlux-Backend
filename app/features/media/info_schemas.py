from pydantic import BaseModel, ConfigDict
from typing import Any


class MediaInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_name: str
    file_size: int
    duration: float | None = None
    resolution: str | None = None
    fps: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate: str | None = None
    audio_channels: int | None = None
    sample_rate: int | None = None
    container_format: str | None = None
    audio_tracks: int | None = None
    subtitle_tracks: int | None = None
    available_streams: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    creation_metadata: dict[str, Any] | None = None
