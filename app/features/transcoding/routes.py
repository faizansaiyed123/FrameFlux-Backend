from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.transcoding.schemas import TranscodeRequest, TranscodeResponse
from app.infrastructure.database import get_db

router = APIRouter(prefix="/transcoding", tags=["Transcoding"])


@router.post("/{media_id}/transcode", response_model=TranscodeResponse)
async def transcode_media(
    media_id: UUID,
    data: TranscodeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return TranscodeResponse(
        media_id=str(media_id),
        status="queued",
        message="Transcoding support is being configured",
    )


@router.post("/{media_id}/convert", response_model=TranscodeResponse)
async def convert_media(
    media_id: UUID,
    data: TranscodeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return TranscodeResponse(
        media_id=str(media_id),
        status="queued",
        message="Conversion support is being configured",
    )


@router.post("/{media_id}/compress", response_model=TranscodeResponse)
async def compress_media(
    media_id: UUID,
    data: TranscodeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return TranscodeResponse(
        media_id=str(media_id),
        status="queued",
        message="Compression support is being configured",
    )
