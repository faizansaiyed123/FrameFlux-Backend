from pydantic import BaseModel
from typing import Any


class EffectDefinition(BaseModel):
    name: str
    category: str
    parameters: dict[str, Any] = {}


class EffectsListResponse(BaseModel):
    media_id: str
    effects: list[EffectDefinition]
    message: str | None = None


class ApplyEffectRequest(BaseModel):
    effect_name: str
    parameters: dict[str, Any] = {}


class ApplyEffectResponse(BaseModel):
    media_id: str
    status: str
    message: str | None = None
