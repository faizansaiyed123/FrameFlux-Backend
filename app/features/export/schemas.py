from pydantic import BaseModel
from typing import Any


class ExportRequest(BaseModel):
    format: str = "mp4"
    quality: int | None = None
    resolution: str | None = None
    options: dict[str, Any] = {}


class ExportResponse(BaseModel):
    media_id: str
    status: str
    message: str | None = None
