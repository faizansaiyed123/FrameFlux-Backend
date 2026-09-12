from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from uuid import UUID, uuid4

from app.core.config import get_settings

settings = get_settings()
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.media.gif_processor import video_to_gif, gif_to_frames

router = APIRouter(prefix="/gif", tags=["GIF"])


@router.post("/{media_id}/generate")
async def generate_gif(
    media_id: UUID,
    start: float = 0,
    end: float | None = None,
    duration: float | None = None,
    width: int = 480,
    fps: int = 15,
    quality: int = 10,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_preview_{uuid4().hex[:8]}.gif"
    output_path = Path(settings.processed_dir) / output_filename
    video_to_gif(str(input_path), str(output_path), start=start, end=end, duration=duration, width=width, fps=fps, quality=quality)
    return FileResponse(path=output_path, media_type="image/gif", filename=output_filename)


@router.get("/{gif_filename}/preview")
async def preview_gif(
    gif_filename: str,
    current_user: User = Depends(get_current_active_user),
):
    gif_path = Path(settings.processed_dir) / gif_filename
    if not gif_path.exists():
        raise HTTPException(status_code=404, detail="GIF not found")
    return FileResponse(path=gif_path, media_type="image/gif", filename=gif_filename)


@router.get("/{gif_filename}/frames")
async def extract_gif_frames(
    gif_filename: str,
    current_user: User = Depends(get_current_active_user),
):
    gif_path = Path(settings.processed_dir) / gif_filename
    if not gif_path.exists():
        raise HTTPException(status_code=404, detail="GIF not found")

    output_dir = Path(settings.processed_dir) / "gif_frames" / gif_filename
    frames = gif_to_frames(str(gif_path), str(output_dir))
    return {"frames": frames}
