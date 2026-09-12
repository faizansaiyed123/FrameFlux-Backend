from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.video.service import adjust_video, filter_video, fade_video, reverse_media
from app.features.video.schemas import (
    VideoAdjustRequest,
    VideoAdjustResponse,
    VideoFilterRequest,
    VideoFadeRequest,
    VideoReverseRequest,
)

settings = get_settings()
router = APIRouter(prefix="/video", tags=["Video"])


async def _get_media_or_404(media_id: UUID, db: AsyncSession, user_id: UUID) -> Media:
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == user_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    return media


@router.post("/{media_id}/adjust", response_model=VideoAdjustResponse)
async def adjust_video_endpoint(
    media_id: UUID,
    data: VideoAdjustRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media_or_404(media_id, db, current_user.id)
    input_path = get_uploaded_file(media.stored_filename)
    output_filename = adjust_video(
        str(media_id),
        str(input_path),
        brightness=data.brightness,
        contrast=data.contrast,
        saturation=data.saturation,
        gamma=data.gamma,
        hue=data.hue,
    )
    return VideoAdjustResponse(output_filename=output_filename, operation="adjust", media_id=str(media_id))


@router.post("/{media_id}/filter", response_model=VideoAdjustResponse)
async def filter_video_endpoint(
    media_id: UUID,
    data: VideoFilterRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media_or_404(media_id, db, current_user.id)
    input_path = get_uploaded_file(media.stored_filename)
    output_filename = filter_video(
        str(media_id),
        str(input_path),
        operation=data.operation,
        intensity=data.intensity or 1.0,
    )
    return VideoAdjustResponse(output_filename=output_filename, operation=data.operation, media_id=str(media_id))


@router.post("/{media_id}/fade", response_model=VideoAdjustResponse)
async def fade_video_endpoint(
    media_id: UUID,
    data: VideoFadeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media_or_404(media_id, db, current_user.id)
    input_path = get_uploaded_file(media.stored_filename)
    output_filename = fade_video(
        str(media_id),
        str(input_path),
        fade_type=data.fade_type,
        duration=data.duration,
        start_time=data.start_time or 0.0,
    )
    return VideoAdjustResponse(output_filename=output_filename, operation=f"fade_{data.fade_type}", media_id=str(media_id))


@router.post("/{media_id}/reverse", response_model=VideoAdjustResponse)
async def reverse_video_endpoint(
    media_id: UUID,
    data: VideoReverseRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await _get_media_or_404(media_id, db, current_user.id)
    input_path = get_uploaded_file(media.stored_filename)
    output_filename = reverse_media(str(media_id), str(input_path))
    return VideoAdjustResponse(output_filename=output_filename, operation="reverse", media_id=str(media_id))
