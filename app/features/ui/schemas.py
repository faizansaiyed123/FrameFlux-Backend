from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class UserPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    value: str
    updated_at: datetime


class UserPreferenceUpdate(BaseModel):
    value: str
