from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.media.models import Media
from app.features.media.schemas import MediaResponse
from app.features.media.service import delete_media_file, save_upload
from app.infrastructure.database import get_db

router = APIRouter(prefix="/media", tags=["Media"])


@router.post(
    "/upload",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        media = await save_upload(file)
        db.add(media)
        await db.commit()
        await db.refresh(media)
        return media
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get(
    "",
    response_model=list[MediaResponse],
)
async def list_media(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).order_by(Media.created_at.desc())
    )
    return result.scalars().all()


@router.get(
    "/{media_id}",
    response_model=MediaResponse,
)
async def get_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )
    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    return media


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )
    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    await delete_media_file(media.stored_filename)

    await db.delete(media)
    await db.commit()
