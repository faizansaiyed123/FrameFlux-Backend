from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator


class WorkflowOperation(BaseModel):
    type: str
    params: dict = {}


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    operations: list[WorkflowOperation]


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    operations: list[WorkflowOperation] | None = None


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    name: str
    description: str | None
    is_builtin: bool
    operations: list[WorkflowOperation]
    created_at: datetime
    updated_at: datetime

    @field_validator("operations", mode="before")
    @classmethod
    def parse_operations(cls, value):
        if isinstance(value, str):
            import json
            value = json.loads(value)
        return value
