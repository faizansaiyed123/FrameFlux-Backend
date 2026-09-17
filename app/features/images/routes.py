from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.features.media.processor import get_uploaded_file
from app.infrastructure.database import get_db
from app.features.images.schemas import ImageConvertRequest
from app.features.images.processor import convert_image, compress_image

settings = get_settings()

router = APIRouter(prefix="/images", tags=["Images"])


@router.post("/{media_id}/convert")
async def convert_image_endpoint(
    media_id: UUID,
    data: ImageConvertRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    if media.media_type != "image":
        raise HTTPException(status_code=400, detail="Media is not an image")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_converted_{uuid4().hex[:8]}.{data.format}"
    output_path = Path(settings.processed_dir) / output_filename

    await convert_image(
        str(input_path),
        str(output_path),
        format=data.format,
        width=data.width,
        height=data.height,
        quality=data.quality,
    )
    return FileResponse(path=output_path, media_type=f"image/{data.format}", filename=output_filename)


@router.post("/{media_id}/compress")
async def compress_image_endpoint(
    media_id: UUID,
    quality: int = 80,
    max_width: int | None = None,
    max_height: int | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    if media.media_type != "image":
        raise HTTPException(status_code=400, detail="Media is not an image")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_compressed_{uuid4().hex[:8]}.webp"
    output_path = Path(settings.processed_dir) / output_filename

    result = await compress_image(
        str(input_path),
        str(output_path),
        quality=quality,
        max_width=max_width,
        max_height=max_height,
    )
    return {"output_filename": output_filename, **result}