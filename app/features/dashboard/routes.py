from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.dashboard.schemas import DashboardOverviewResponse
from app.features.dashboard.service import get_dashboard_overview
from app.infrastructure.database import get_db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Get user-scoped dashboard overview and analytics",
)
async def dashboard_overview(
    limit: int = Query(default=5, ge=1, le=50, description="Max recent items to return"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns user-scoped analytics:
    - total_projects
    - total_media
    - media_by_type (video, audio, image)
    - processing_status_counts (pending, queued, processing, completed, failed)
    - total_storage_used_bytes
    - recent_projects (latest N, with media counts)
    - recent_media (latest N)
    - active_jobs_count
    """
    return await get_dashboard_overview(db, current_user.id, recent_limit=limit)
