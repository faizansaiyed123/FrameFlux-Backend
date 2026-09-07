# app/features/media/routes.py

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.media.schemas import MediaResponse
from app.features.media.service import save_upload
from app.infrastructure.database import get_db

router = APIRouter(
    prefix="/media",
    tags=["Media"],
)


@router.post(
    "/upload",
    response_model=MediaResponse,
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
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )
