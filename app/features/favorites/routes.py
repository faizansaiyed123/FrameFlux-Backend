from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.favorites.schemas import FavoriteCreate, FavoriteResponse
from app.features.favorites.service import (
    add_favorite,
    remove_favorite,
    list_favorites,
)
from app.features.media.models import Media
from app.infrastructure.database import get_db

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.post("", response_model=FavoriteResponse, status_code=status.HTTP_201_CREATED)
async def create_favorite(
    data: FavoriteCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == data.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    return await add_favorite(db, current_user.id, data.media_id)


@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await remove_favorite(db, current_user.id, media_id)


@router.get("", response_model=list[FavoriteResponse])
async def get_favorites(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_favorites(db, current_user.id)
