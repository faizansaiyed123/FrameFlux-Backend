from pydantic import BaseModel
from typing import Any


class TranscodeRequest(BaseModel):
    format: str = "mp4"
    quality: int | None = None
    preserve_aspect_ratio: bool = True
    options: dict[str, Any] = {}


class TranscodeResponse(BaseModel):
    media_id: str
    status: str
    message: str | None = None
