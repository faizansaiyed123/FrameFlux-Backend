from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationCreate(BaseModel):
    event: str
    message: str
