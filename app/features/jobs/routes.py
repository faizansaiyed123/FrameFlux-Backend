from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.jobs.models import ProcessingJob
from app.features.jobs.schemas import JobStatusResponse, ProcessingJobResponse
from app.features.jobs.service import (
    get_job_status,
    list_queued_jobs,
    list_processing_jobs,
    get_processing_job,
)
from app.features.media.models import Media
from app.infrastructure.database import get_db

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "",
    response_model=list[ProcessingJobResponse],
    summary="List processing jobs for the current user",
)
async def list_jobs_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    jobs = await list_processing_jobs(db, user_id=current_user.id)
    return [
        ProcessingJobResponse(
            job_id=str(job.id),
            media_id=str(job.media_id) if job.media_id else None,
            media_version_id=str(job.media_version_id) if job.media_version_id else None,
            task_name=job.task_name,
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            error=job.error,
            operation_type=job.operation_type,
            retry_count=job.retry_count,
            enqueued_at=job.enqueued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get background job status and progress by job ID",
)
async def get_job_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
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
