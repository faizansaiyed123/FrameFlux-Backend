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
