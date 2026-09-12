from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FavoriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    media_id: UUID
    created_at: datetime


class FavoriteCreate(BaseModel):
    media_id: UUID
