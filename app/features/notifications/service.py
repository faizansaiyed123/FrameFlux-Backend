from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.notifications.models import Notification
from app.features.notifications.schemas import NotificationCreate


async def create_notification(db: AsyncSession, user_id: UUID | None, data: NotificationCreate) -> Notification:
    notification = Notification(
        user_id=user_id,
        event=data.event,
        message=data.message,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    return notification


async def list_notifications(db: AsyncSession, user_id: UUID | None) -> list[Notification]:
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())
    )
    return result.scalars().all()


async def mark_notification_read(db: AsyncSession, notification: Notification) -> Notification:
    notification.is_read = True
    await db.commit()
    await db.refresh(notification)
    return notification
