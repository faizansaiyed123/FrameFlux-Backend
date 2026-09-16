from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.export.schemas import ExportRequest, ExportResponse
from app.infrastructure.database import get_db

router = APIRouter(prefix="/export", tags=["Export"])


@router.post("/{media_id}/export", response_model=ExportResponse)
async def export_media(
    media_id: UUID,
    data: ExportRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ExportResponse(
        media_id=str(media_id),
        status="queued",
        message="Export support is being configured",
    )


@router.get("/{media_id}/status", response_model=ExportResponse)
async def get_export_status(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ExportResponse(
        media_id=str(media_id),
        status="queued",
        message="Export support is being configured",
    )
