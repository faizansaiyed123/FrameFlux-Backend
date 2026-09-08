from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.jobs.schemas import JobStatusResponse
from app.features.jobs.service import get_job_status, list_queued_jobs
from app.features.media.models import Media
from app.infrastructure.database import get_db

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "",
    response_model=list[JobStatusResponse],
    summary="List queued background jobs",
)
async def list_jobs_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns a list of currently queued ARQ background jobs owned by the user.
    """
    all_jobs = await list_queued_jobs()
    user_jobs = []
    for job in all_jobs:
        media_id = job.get("media_id")
        if media_id:
            try:
                m_uuid = UUID(media_id)
                res = await db.execute(select(Media).where(Media.id == m_uuid))
                media = res.scalar_one_or_none()
                if media and media.user_id is not None and media.user_id != current_user.id:
                    continue
            except (ValueError, TypeError):
                pass
        user_jobs.append(job)
    return user_jobs


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get background job status and progress",
)
async def get_job_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Monitors an ARQ background job by its ID.
    Provides execution state (queued, processing, completed, failed),
    fine-grained progress (0-100), task name, associated media ID,
    start/finish timestamps, and any failure errors.
    """
    job_data = await get_job_status(job_id)
    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )

    media_id = job_data.get("media_id")
    if media_id:
        try:
            m_uuid = UUID(media_id)
            res = await db.execute(select(Media).where(Media.id == m_uuid))
            media = res.scalar_one_or_none()
            if media and media.user_id is not None and media.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job '{job_id}' not found",
                )
        except (ValueError, TypeError):
            pass

    return job_data
