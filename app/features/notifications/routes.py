from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.notifications.models import Notification
from app.features.notifications.schemas import (
    NotificationCreate,
    NotificationResponse,
    UnreadCountResponse,
)
from app.features.notifications.service import (
    count_unread,
    create_notification,
    list_notifications,
    mark_all_read,
    mark_notification_read,
)
from app.infrastructure.database import get_db
from app.shared.pagination import (
    PaginatedResponse,
    PaginationParams,
    build_response,
    paginate,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.post(
    "",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_endpoint(
    data: NotificationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_notification(db, user_id=current_user.id, data=data)


@router.get(
    "",
    response_model=PaginatedResponse[NotificationResponse],
)
async def list_notifications_endpoint(
    unread_only: bool = False,
    pagination: PaginationParams = Depends(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notification).where(
        Notification.user_id == current_user.id
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = query.order_by(Notification.created_at.desc())

    items, total = await paginate(db, query, pagination)
    return build_response(items, total, pagination)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
)
async def unread_count_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return UnreadCountResponse(
        unread_count=await count_unread(db, current_user.id)
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
)
async def mark_read(
    notification_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return await mark_notification_read(db, notification)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_all_read_endpoint(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    await mark_all_read(db, current_user.id)
