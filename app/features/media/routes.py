from pathlib import Path
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.media.models import Media
from app.features.media.schemas import MediaResponse
from app.features.media.service import delete_media_file, save_upload
from app.infrastructure.database import get_db
from app.infrastructure.worker import create_worker_pool
from fastapi.responses import FileResponse
from app.features.media.processor import get_uploaded_file
from uuid import UUID, uuid4

from app.features.media.schemas import MediaConvertRequest
from app.infrastructure.tasks import convert_media_task
from uuid import UUID, uuid4

from app.features.media.schemas import MediaEditRequest
from app.infrastructure.worker import create_worker_pool


settings = get_settings()

router = APIRouter(prefix="/media", tags=["Media"])


async def get_redis_pool():
    return await create_pool(
        RedisSettings(
            host="localhost",
            port=6379,
            database=0,
        )
    )


@router.post(
    "/upload",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        media = await save_upload(file)

        db.add(media)
        await db.commit()
        await db.refresh(media)

        return media

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/{media_id}/process")
async def process_media_endpoint(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    redis = await get_redis_pool()

    try:
        job = await redis.enqueue_job(
            "process_media_task",
            str(media.id),
            media.stored_filename,
        )
    finally:
        await redis.close()

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
    }


@router.get("/{media_id}/processed")
async def get_processed_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    processed_filename = f"{media.id}_processed.mp4"
    processed_path = Path(settings.upload_dir) / processed_filename

    if not processed_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processed media not found. Process the media first.",
        )

    return FileResponse(
        path=processed_path,
        media_type="video/mp4",
        filename=processed_filename,
    )


@router.get(
    "",
    response_model=list[MediaResponse],
)
async def list_media(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).order_by(Media.created_at.desc())
    )

    return result.scalars().all()


@router.get(
    "/{media_id}",
    response_model=MediaResponse,
)
async def get_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    return media


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    await delete_media_file(media.stored_filename)

    processed_filename = f"{media.id}_processed.mp4"
    await delete_media_file(processed_filename)

    await db.delete(media)
    await db.commit()


@router.post("/{media_id}/process")
async def process_media_endpoint(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    if media.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Media is already processing",
        )

    if media.processing_status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Media is already processed",
        )

    media.processing_status = "pending"
    media.processing_error = None

    await db.commit()

    pool = await create_worker_pool()

    try:
        job = await pool.enqueue_job(
            "process_media_task",
            str(media.id),
            media.stored_filename,
        )
    finally:
        await pool.close()

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
    }
@router.patch("/{media_id}/project/{project_id}")
async def attach_media_to_project(
    media_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    media_result = await db.execute(
        select(Media).where(Media.id == media_id)
    )
    media = media_result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    media.project_id = project_id

    await db.commit()
    await db.refresh(media)

    return media


@router.get("/{media_id}/file")
async def get_media_file(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    file_path = get_uploaded_file(media.stored_filename)

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Media file not found",
        )

    return FileResponse(
        path=file_path,
        media_type=media.mime_type,
        filename=media.original_filename,
    )


@router.get("/{media_id}/processed")
async def get_processed_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    if not media.processed_filename:
        raise HTTPException(
            status_code=404,
            detail="Processed media not available",
        )

    file_path = get_uploaded_file(media.processed_filename)

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Processed media file not found",
        )

    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=media.processed_filename,
    )


@router.post("/{media_id}/convert")
async def convert_media_endpoint(
    media_id: UUID,
    data: MediaConvertRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    extension = data.format.lower().lstrip(".")

    output_filename = (
        f"{media_id}_converted_{uuid4().hex[:8]}.{extension}"
    )

    options = data.model_dump(exclude_none=True)
    options["output_format"] = extension

    from app.infrastructure.worker import create_worker_pool

    pool = await create_worker_pool()

    try:
        job = await pool.enqueue_job(
            "convert_media_task",
            str(media.id),
            media.stored_filename,
            output_filename,
            options,
        )
    finally:
        await pool.close()

    media.processing_status = "pending"
    media.processing_error = None
    await db.commit()

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }

@router.post("/{media_id}/edit")
async def edit_media_endpoint(
    media_id: UUID,
    data: MediaEditRequest,
    db: AsyncSession = Depends(get_db),
):
    if data.operation not in {"trim", "cut", "extract"}:
        raise HTTPException(
            status_code=400,
            detail="Operation must be trim, cut, or extract",
        )

    if data.end <= data.start:
        raise HTTPException(
            status_code=400,
            detail="End time must be greater than start time",
        )

    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )
    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=404,
            detail="Media not found",
        )

    output_filename = (
        f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
    )

    pool = await create_worker_pool()

    try:
        job = await pool.enqueue_job(
            "edit_media_task",
            str(media.id),
            media.stored_filename,
            output_filename,
            data.operation,
            data.start,
            data.end,
        )
    finally:
        await pool.close()

    media.processing_status = "pending"
    media.processing_error = None
    await db.commit()

    return {
        "media_id": str(media.id),
        "status": "queued",
        "operation": data.operation,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }
