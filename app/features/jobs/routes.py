from fastapi import APIRouter, HTTPException, status
from app.features.jobs.schemas import JobStatusResponse
from app.features.jobs.service import get_job_status, list_queued_jobs

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "",
    response_model=list[JobStatusResponse],
    summary="List queued background jobs",
)
async def list_jobs_endpoint():
    """
    Returns a list of currently queued ARQ background jobs.
    """
    return await list_queued_jobs()


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get background job status and progress",
)
async def get_job_endpoint(job_id: str):
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
    return job_data
