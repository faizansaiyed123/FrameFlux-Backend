from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.batch.schemas import BatchUploadRequest, BatchUploadResponse, BatchOperationRequest, BatchOperationResponse, BatchResultResponse
from app.features.batch.service import get_batch_media, create_batch_job

router = APIRouter(prefix="/batch", tags=["Batch Processing"])


@router.post("/upload", response_model=BatchUploadResponse)
async def batch_upload(
    data: BatchUploadRequest,
    current_user: User = Depends(get_current_active_user),
):
    job_id = await create_batch_job("upload", [], {"files": data.files}, current_user.id)
    return BatchUploadResponse(job_id=job_id, total_files=len(data.files), status="queued")


@router.post("/process", response_model=BatchOperationResponse)
async def batch_process(
    data: BatchOperationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media_items = await get_batch_media(db, data.media_ids, current_user.id)
    if not media_items:
        raise HTTPException(status_code=404, detail="No valid media found")

    job_id = await create_batch_job(data.operation, data.media_ids, data.options, current_user.id)
    return BatchOperationResponse(
        job_id=job_id,
        total_items=len(media_items),
        operation=data.operation,
        status="queued",
        results=[{"media_id": str(m.id), "filename": m.original_filename} for m in media_items],
    )


@router.get("/{job_id}/status", response_model=BatchResultResponse)
async def get_batch_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    from app.features.jobs.models import ProcessingJob
    import json
    result = await db.execute(select(ProcessingJob).where(ProcessingJob.id == UUID(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Batch job not found")

    operation_params = {}
    if job.operation_params:
        if isinstance(job.operation_params, dict):
            operation_params = job.operation_params
        else:
            try:
                operation_params = json.loads(job.operation_params)
            except (json.JSONDecodeError, TypeError):
                pass

    return BatchResultResponse(
        job_id=job_id,
        status=job.status,
        total=operation_params.get("media_count", 0),
        completed=0,
        failed=0,
        results=[],
    )
