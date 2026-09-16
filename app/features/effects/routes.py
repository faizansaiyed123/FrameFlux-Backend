from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.effects.schemas import EffectsListResponse, ApplyEffectRequest, ApplyEffectResponse
from app.infrastructure.database import get_db

router = APIRouter(prefix="/effects", tags=["Effects"])


@router.get("/{media_id}/list", response_model=EffectsListResponse)
async def list_effects(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return EffectsListResponse(
        media_id=str(media_id),
        effects=[],
        message="Effects support is being configured",
    )


@router.post("/{media_id}/apply", response_model=ApplyEffectResponse)
async def apply_effect(
    media_id: UUID,
    data: ApplyEffectRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return ApplyEffectResponse(
        media_id=str(media_id),
        status="queued",
        message="Effect application support is being configured",
    )


@router.delete("/{media_id}/remove")
async def remove_effect(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"media_id": str(media_id), "status": "ok", "message": "Effect removal support is being configured"}
