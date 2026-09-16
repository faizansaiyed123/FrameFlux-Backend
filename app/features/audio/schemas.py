from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class AudioConvertRequest(BaseModel):
    format: Literal["mp3", "wav", "aac", "flac", "ogg", "m4a", "opus", "aiff"] = "mp3"
    bitrate: str | None = Field(default=None, description="Audio bitrate, e.g. 192k")
    sample_rate: int | None = Field(default=None, ge=8000, le=384000, description="Sample rate in Hz")
    channels: Literal[1, 2] | None = Field(default=None, description="1=mono, 2=stereo")
    quality: Literal["low", "medium", "high"] | None = Field(default=None, description="Quality preset")


class AudioEditRequest(BaseModel):
    operation: Literal["trim", "cut", "split", "merge", "speed", "normalize", "fade", "silence"]
    start: float | None = Field(default=None, ge=0, description="Start time in seconds")
    end: float | None = Field(default=None, gt=0, description="End time in seconds")
    speed: float | None = Field(default=None, ge=0.1, le=10.0, description="Playback speed multiplier")
    fade_in: float | None = Field(default=None, ge=0, description="Fade in duration in seconds")
    fade_out: float | None = Field(default=None, ge=0, description="Fade out duration in seconds")
    silence_duration: float | None = Field(default=None, ge=0, description="Silence duration in seconds")
    target_files: list[str] | None = Field(default=None, description="For merge: list of stored filenames")


class AudioToVideoRequest(BaseModel):
    background_image: str | None = Field(default=None, description="Stored filename of background image")
    background_color: str | None = Field(default="#000000", description="Hex color for solid background")
    title: str | None = Field(default=None, max_length=255)
    artist: str | None = Field(default=None, max_length=255)
    text: str | None = Field(default=None, description="Custom text overlay")
    watermark: str | None = Field(default=None, description="Stored filename of watermark image")
    show_waveform: bool = Field(default=False, description="Render audio waveform")
    visualizer_style: Literal["bars", "wave", "circle"] | None = Field(default=None, description="Visualizer style")
    resolution: str | None = Field(default="1920x1080", description="Video resolution WxH")
    fps: int | None = Field(default=30, ge=1, le=120)
    aspect_ratio: str | None = Field(default="16:9", description="Aspect ratio, e.g. 16:9")
    duration: float | None = Field(default=None, gt=0, description="Max video duration in seconds")
    output_format: Literal["mp4", "webm"] = "mp4"


class AudioVideoSyncRequest(BaseModel):
    audio_path: str = Field(description="Stored filename of external audio file")
    audio_offset: float = Field(default=0.0, description="Audio offset in seconds (positive = delay, negative = advance)")
    video_duration: float | None = Field(default=None, gt=0, description="Limit video duration")
    audio_duration: float | None = Field(default=None, gt=0, description="Limit audio duration")
    fade_in: float | None = Field(default=None, ge=0, description="Fade in duration for external audio")
    fade_out: float | None = Field(default=None, ge=0, description="Fade out duration for external audio")
    volume: float = Field(default=1.0, ge=0.0, le=10.0, description="Volume multiplier for external audio")
    mix: bool = Field(default=False, description="Mix with original audio instead of replacing")
    mix_volume: float = Field(default=0.5, ge=0.0, le=1.0, description="Original audio volume when mixing")
    output_format: Literal["mp4", "webm"] = "mp4"


class BatchAudioExtractRequest(BaseModel):
    media_ids: list[UUID] = Field(min_length=1, max_length=50)
    format: str = "mp3"
    bitrate: str | None = None
    sample_rate: int | None = None
    channels: int | None = None


class BatchAudioExtractResponse(BaseModel):
    jobs: list[dict]
