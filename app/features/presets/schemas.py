from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from uuid import UUID


class PresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    name: str
    description: str | None = None
    is_builtin: bool = False
    settings: dict
    created_at: datetime
    updated_at: datetime

    @field_validator("settings", mode="before")
    @classmethod
    def parse_settings(cls, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    settings: dict = Field(default_factory=dict)


class PresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    settings: dict | None = None
