from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.export.schemas import ExportRequest, ExportResponse
from app.features.media.models import Media
from app.features.media.routes import enqueue_media_job, mark_processing_pending
from app.infrastructure.database import get_db

router = APIRouter(prefix="/export", tags=["Export"])


async def _get_media(media_id: UUID, user_id: UUID, db: AsyncSession) -> Media:
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == user_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return media


@router.post("/{media_id}/export", response_model=ExportResponse)
async def export_media(
    media_id: UUID,
    data: ExportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media(media_id, current_user.id, db)

    output_format = data.format.lower().lstrip(".")
    options = dict(data.options or {})
    options["output_format"] = output_format
    if data.quality is not None:
        options["quality"] = data.quality
    if data.resolution:
        options["resolution"] = data.resolution

    output_filename = f"{media_id}_export_{uuid4().hex[:8]}.{output_format}"
    job = await enqueue_media_job(
        "convert_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        options,
    )
    await mark_processing_pending(media, db)

    return ExportResponse(
        media_id=str(media_id),
        status="queued",
        message=f"Export queued as {output_filename}",
    )


@router.get("/{media_id}/status", response_model=ExportResponse)
async def get_export_status(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media(media_id, current_user.id, db)
    status_value = media.processing_status
    message = media.processing_error if status_value == "failed" else media.processed_filename
    return ExportResponse(media_id=str(media_id), status=status_value, message=message)
