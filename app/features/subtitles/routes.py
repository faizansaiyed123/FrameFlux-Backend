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
from app.features.subtitles.service import burn_subtitles_into_video, extract_subtitle_track, mux_soft_subtitles
from app.features.subtitles.schemas import SubtitleBurnRequest, SubtitleSyncRequest, SubtitleEditRequest, SubtitleTrackResponse

router = APIRouter(prefix="/subtitles", tags=["Subtitles"])


@router.post("/{media_id}/burn")
async def burn_subtitles_endpoint(
    media_id: UUID,
    subtitle_path: str,
    font_size: int = 24,
    font_color: str = "white",
    background_color: str = "black@0.5",
    position: str = "bottom",
    font: str | None = None,
    alignment: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    subtitle_file = get_uploaded_file(subtitle_path)
    rel_path = burn_subtitles_into_video(
        str(input_path),
        str(subtitle_file),
        str(media_id),
        font_size=font_size,
        font_color=font_color,
        background_color=background_color,
        position=position,
        font=font,
        alignment=alignment,
    )
    full_path = Path(settings.processed_dir) / rel_path
    return FileResponse(path=full_path, media_type="video/mp4", filename=full_path.name)


@router.post("/{media_id}/mux")
async def mux_soft_subtitles_endpoint(
    media_id: UUID,
    subtitle_path: str,
    language: str = "und",
    is_default: bool = False,
    is_forced: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    subtitle_file = get_uploaded_file(subtitle_path)
    output_filename = f"{media_id}_mux_{uuid4().hex[:8]}.mp4"
    output_path = Path(settings.processed_dir) / output_filename
    mux_soft_subtitles(
        str(input_path),
        str(subtitle_file),
        str(output_path),
        language=language,
        is_default=is_default,
        is_forced=is_forced,
    )
    return FileResponse(path=output_path, media_type="video/mp4", filename=output_filename)


@router.get("/{media_id}/tracks", response_model=list[SubtitleTrackResponse])
async def list_subtitle_tracks(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    tracks = extract_subtitle_track(str(input_path))
    return [SubtitleTrackResponse(**track) for track in tracks]


@router.post("/{media_id}/sync")
async def sync_subtitles(
    media_id: UUID,
    data: SubtitleSyncRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_synced_{uuid4().hex[:8]}.mp4"
    output_path = Path(settings.processed_dir) / output_filename

    if data.preview:
        return {"preview_url": f"/media/{media_id}/file", "offset": data.offset_seconds, "scale": data.scale}

    try:
        (
            ffmpeg.input(str(input_path))
            .output(
                str(output_path),
                vf=f"subtitles={input_path}:si=0,setpts=PTS*{data.scale}+{data.offset_seconds}/TB",
                vcodec="libx264",
                acodec="aac",
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg sync failed"
        raise RuntimeError(error) from exc

    return FileResponse(path=output_path, media_type="video/mp4", filename=output_filename)
