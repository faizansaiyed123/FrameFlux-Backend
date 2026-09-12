from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from uuid import UUID, uuid4
import ffmpeg

from app.core.config import get_settings

settings = get_settings()
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.media.gif_processor import video_to_gif
from app.features.thumbnails.processor import generate_thumbnail

router = APIRouter(prefix="/preview", tags=["Video Preview"])


@router.get("/{media_id}/video")
async def generate_video_preview(
    media_id: UUID,
    duration: float = 15.0,
    start: float = 0.0,
    width: int = 480,
    fps: int = 15,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_preview_{uuid4().hex[:8]}.mp4"
    output_path = Path(settings.processed_dir) / output_filename

    kwargs = {
        "ss": start,
    }
    out_kwargs = {
        "t": duration,
        "vf": f"fps={fps},scale={width}:-1:flags=lanczos",
        "vcodec": "libx264",
        "acodec": "aac",
        "movflags": "+faststart",
    }
    try:
        (
            ffmpeg.input(str(input_path), **kwargs)
            .output(str(output_path), **out_kwargs)
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg preview generation failed"
        raise RuntimeError(error) from exc

    return FileResponse(path=output_path, media_type="video/mp4", filename=output_filename)


@router.get("/{media_id}/gif")
async def generate_gif_preview(
    media_id: UUID,
    duration: float = 5.0,
    start: float = 0.0,
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
    output_filename = f"{media_id}_gif_preview_{uuid4().hex[:8]}.gif"
    output_path = Path(settings.processed_dir) / output_filename
    video_to_gif(
        str(input_path),
        str(output_path),
        start=start,
        duration=duration,
        width=width,
        fps=fps,
        quality=quality,
    )
    return FileResponse(path=output_path, media_type="image/gif", filename=output_filename)


@router.get("/{media_id}/thumbnail")
async def generate_thumbnail_preview(
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
    output_dir = Path(settings.processed_dir) / "previews" / str(media_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"preview_{uuid4().hex[:8]}.{fmt}"
    output_path = output_dir / output_filename

    generate_thumbnail(str(input_path), str(output_path), timestamp=timestamp, width=width, height=height, fmt=fmt)
    media_type = "image/png" if fmt == "png" else "image/webp" if fmt == "webp" else "image/jpeg"
    return FileResponse(path=output_path, media_type=media_type, filename=output_filename)
