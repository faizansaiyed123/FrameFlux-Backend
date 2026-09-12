from pydantic import BaseModel, ConfigDict


class MediaComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    media_a_id: str
    media_b_id: str
    size_diff: int
    duration_diff: float | None
    resolution_match: bool
    video_codec_match: bool
    audio_codec_match: bool
    storage_saved: int
