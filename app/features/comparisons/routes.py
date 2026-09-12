from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.comparisons.service import compare_media
from app.features.comparisons.schemas import MediaComparisonResponse

router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@router.get("/{media_a_id}/{media_b_id}", response_model=MediaComparisonResponse)
async def compare_media_endpoint(
    media_a_id: UUID,
    media_b_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result_a = await db.execute(select(Media).where(Media.id == media_a_id, Media.user_id == current_user.id))
    media_a = result_a.scalar_one_or_none()
    if media_a is None:
        raise HTTPException(status_code=404, detail="Media A not found")

    result_b = await db.execute(select(Media).where(Media.id == media_b_id, Media.user_id == current_user.id))
    media_b = result_b.scalar_one_or_none()
    if media_b is None:
        raise HTTPException(status_code=404, detail="Media B not found")

    return MediaComparisonResponse(**compare_media(media_a, media_b))
