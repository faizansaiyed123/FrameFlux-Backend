from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class ShareCreate(BaseModel):
    media_id: UUID
    password: str | None = None
    expires_in_hours: int | None = None
    allow_download: bool = True
    allowed_domains: str | None = None  # Comma-separated list of allowed domains for embed


class ShareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    media_id: UUID
    token: str
    password: str | None
    expires_at: datetime | None
    is_active: bool
    allow_download: bool
    view_count: int
    allowed_domains: str | None
    created_at: datetime


class EmbedResponse(BaseModel):
    embed_url: str
    embed_code: str
    media_title: str
