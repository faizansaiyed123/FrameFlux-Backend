from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.features.media.schemas import MediaResponse


class RecentProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    name: str
    description: str | None = None
    media_count: int = 0
    created_at: datetime
    updated_at: datetime


class DashboardOverviewResponse(BaseModel):
    total_projects: int
    total_media: int
    media_by_type: dict[str, int]
    processing_status_counts: dict[str, int]
    total_storage_used_bytes: int
    recent_projects: list[RecentProjectItem]
    recent_media: list[MediaResponse]
    active_jobs_count: int
