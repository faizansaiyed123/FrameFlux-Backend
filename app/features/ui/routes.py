from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.ui.models import UserPreference
from app.features.ui.service import get_preferences, upsert_preference
from app.features.ui.schemas import UserPreferenceResponse, UserPreferenceUpdate

router = APIRouter(prefix="/ui/preferences", tags=["UI Preferences"])


@router.get("", response_model=list[UserPreferenceResponse])
async def list_preferences(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await get_preferences(db, user_id=current_user.id)


@router.put("/{key}", response_model=UserPreferenceResponse)
async def set_preference(
    key: str,
    data: UserPreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await upsert_preference(db, user_id=current_user.id, key=key, value=data.value)
