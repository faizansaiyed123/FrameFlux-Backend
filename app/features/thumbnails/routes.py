from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

settings = get_settings()
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.thumbnails.service import create_thumbnail, create_thumbnail_set
from app.features.thumbnails.processor import crop_thumbnail

router = APIRouter(prefix="/thumbnails", tags=["Thumbnails"])


@router.get("/{media_id}")
async def get_thumbnail(
    media_id: UUID,
    timestamp: float | None = None,
    width: int | None = None,
    height: int | None = None,
    fmt: str = "jpg",
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    rel_path = await create_thumbnail(str(input_path), str(media_id), timestamp=timestamp, width=width, fmt=fmt)
    full_path = Path(settings.processed_dir) / rel_path
    media_type = "image/png" if fmt == "png" else "image/webp" if fmt == "webp" else "image/jpeg"
    return FileResponse(path=full_path, media_type=media_type, filename=full_path.name)


@router.get("/{media_id}/set")
async def get_thumbnail_set(
    media_id: UUID,
    interval: float = 5.0,
    width: int | None = None,
    fmt: str = "jpg",
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    rel_paths = await create_thumbnail_set(str(input_path), str(media_id), interval=interval, width=width, fmt=fmt)
    return {"thumbnails": rel_paths}


@router.post("/{media_id}/crop")
async def crop_thumbnail_endpoint(
    media_id: UUID,
    timestamp: float,
    x: int,
    y: int,
    width: int,
    height: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    output_dir = Path(settings.processed_dir) / "thumbnails" / str(media_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"thumb_{int(timestamp)}s_crop_{width}x{height}.jpg"
    output_path = output_dir / output_filename
    crop_thumbnail(str(input_path), str(output_path), x, y, width, height)
    rel_path = str(output_path.relative_to(Path(settings.processed_dir)))
    return {"path": rel_path}


@router.post("/{media_id}/select")
async def select_thumbnail(
    media_id: UUID,
    timestamp: float,
    width: int | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    rel_path = await create_thumbnail(str(input_path), str(media_id), timestamp=timestamp, width=width)
    return {"selected": rel_path}
