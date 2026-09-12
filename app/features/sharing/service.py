from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.sharing.models import ShareLink
from app.features.sharing.schemas import ShareCreate


async def create_share_link(db: AsyncSession, data: ShareCreate, user_id: UUID | None) -> ShareLink:
    token = uuid4().hex
    expires_at = None
    if data.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=data.expires_in_hours)
    share = ShareLink(
        user_id=user_id,
        media_id=data.media_id,
        token=token,
        password=data.password,
        expires_at=expires_at,
        allow_download=data.allow_download,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


async def get_share_link(db: AsyncSession, token: str) -> ShareLink | None:
    result = await db.execute(select(ShareLink).where(ShareLink.token == token))
    return result.scalar_one_or_none()


async def list_share_links(db: AsyncSession, user_id: UUID | None) -> list[ShareLink]:
    result = await db.execute(select(ShareLink).where(ShareLink.user_id == user_id))
    return result.scalars().all()


async def delete_share_link(db: AsyncSession, share: ShareLink) -> None:
    await db.delete(share)
    await db.commit()


async def disable_share_link(db: AsyncSession, share: ShareLink) -> ShareLink:
    share.is_active = False
    await db.commit()
    await db.refresh(share)
    return share
