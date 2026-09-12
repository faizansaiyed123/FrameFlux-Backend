from uuid import UUID
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.favorites.models import Favorite
from app.features.media.models import Media


async def add_favorite(db: AsyncSession, user_id: UUID, media_id: UUID) -> Favorite:
    favorite = Favorite(user_id=user_id, media_id=media_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)
    return favorite


async def remove_favorite(db: AsyncSession, user_id: UUID, media_id: UUID) -> None:
    await db.execute(
        delete(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.media_id == media_id,
        )
    )
    await db.commit()


async def list_favorites(db: AsyncSession, user_id: UUID) -> list[Favorite]:
    result = await db.execute(
        select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.created_at.desc())
    )
    return list(result.scalars().all())


async def is_favorited(db: AsyncSession, user_id: UUID, media_id: UUID) -> bool:
    result = await db.execute(
        select(Favorite).where(
            Favorite.user_id == user_id,
            Favorite.media_id == media_id,
        )
    )
    return result.scalar_one_or_none() is not None
