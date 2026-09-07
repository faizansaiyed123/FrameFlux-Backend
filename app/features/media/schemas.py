# app/features/media/schemas.py

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
