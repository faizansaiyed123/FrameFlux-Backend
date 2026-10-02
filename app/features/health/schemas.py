from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class DependencyStatus(BaseModel):
    name: str
    status: str
    error: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    dependencies: list[DependencyStatus]
