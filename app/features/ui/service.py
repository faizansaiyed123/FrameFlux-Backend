from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.ui.models import UserPreference
from app.features.ui.schemas import UserPreferenceUpdate


async def get_preferences(db: AsyncSession, user_id: UUID) -> list[UserPreference]:
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    return result.scalars().all()


async def upsert_preference(db: AsyncSession, user_id: UUID, key: str, value: str) -> UserPreference:
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.key == key))
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user_id, key=key, value=value)
        db.add(pref)
    else:
        pref.value = value
    await db.commit()
    await db.refresh(pref)
    return pref
