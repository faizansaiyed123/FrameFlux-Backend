from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.notifications.models import Notification
from app.features.notifications.service import create_notification, list_notifications, mark_notification_read
from app.features.notifications.schemas import NotificationCreate, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post("", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
async def create_notification_endpoint(
    data: NotificationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_notification(db, user_id=current_user.id, data=data)


@router.get("", response_model=list[NotificationResponse])
async def list_notifications_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_notifications(db, user_id=current_user.id)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Notification).where(Notification.id == notification_id, Notification.user_id == current_user.id))
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return await mark_notification_read(db, notification)
