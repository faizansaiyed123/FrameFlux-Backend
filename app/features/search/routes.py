from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.media.models import Media

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/media")
async def search_media(
    q: str | None = None,
    media_type: str | None = None,
    folder: str | None = None,
    tag: str | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    min_duration: float | None = None,
    max_duration: float | None = None,
    processing_status: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Media).where((Media.user_id == current_user.id) | (Media.user_id.is_(None)))
    if q:
        query = query.where(Media.original_filename.ilike(f"%{q}%"))
    if media_type:
        query = query.where(Media.media_type == media_type)
    if folder:
        query = query.where(Media.folder == folder)
    if tag:
        query = query.where(Media.tags.ilike(f"%{tag}%"))
    if min_size is not None:
        query = query.where(Media.file_size >= min_size)
    if max_size is not None:
        query = query.where(Media.file_size <= max_size)
    if min_duration is not None:
        query = query.where(Media.duration >= min_duration)
    if max_duration is not None:
        query = query.where(Media.duration <= max_duration)
    if processing_status:
        query = query.where(Media.processing_status == processing_status)
    query = query.order_by(Media.created_at.desc())
    result = await db.execute(query)
    media_list = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "original_filename": m.original_filename,
            "media_type": m.media_type,
            "file_size": m.file_size,
            "duration": m.duration,
            "processing_status": m.processing_status,
            "folder": m.folder,
            "tags": m.tags,
        }
        for m in media_list
    ]
