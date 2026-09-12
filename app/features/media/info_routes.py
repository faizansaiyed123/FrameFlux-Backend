from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.info_service import get_media_info
from app.features.media.info_schemas import MediaInfoResponse

router = APIRouter(prefix="/media-info", tags=["Media Information"])


@router.get("/{media_id}", response_model=MediaInfoResponse)
async def get_media_info_endpoint(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    info = await get_media_info(media.stored_filename)
    return MediaInfoResponse(**info)
