from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
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
from app.features.media.models import Media, MediaVersion
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.subtitles.service import (
    burn_subtitles_into_video,
    extract_subtitle_track,
    mux_soft_subtitles,
    shift_subtitle_timestamps,
    update_subtitle_text,
    update_subtitle_timing,
    add_subtitle_entry,
)
from app.features.subtitles.schemas import SubtitleBurnRequest, SubtitleSyncRequest, SubtitleEditRequest, SubtitleTrackResponse

router = APIRouter(prefix="/subtitles", tags=["Subtitles"])


@router.post("/upload")
async def upload_subtitle_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    import aiofiles
    from app.core.config import get_settings
    settings = get_settings()
    
    # Validate file extension
    allowed_extensions = {'.srt', '.ass', '.vtt', '.sub', '.txt'}
    file_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported subtitle format. Allowed: {allowed_extensions}")
    
    # Generate unique filename
    unique_filename = f"{uuid4().hex}{file_ext}"
    file_path = Path(settings.upload_dir) / unique_filename
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    return {
        "filename": unique_filename,
        "original_filename": file.filename,
        "size": len(content),
    }


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
    output_filename = Path(rel_path).name
    full_path = Path(settings.processed_dir) / output_filename
    
    # Get file size
    file_size = full_path.stat().st_size if full_path.exists() else 0
    
    # Get video info using ffprobe
    try:
        probe = ffmpeg.probe(str(full_path))
        video_stream = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
        audio_stream = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
        
        duration = float(probe["format"].get("duration", 0)) if probe["format"].get("duration") else None
        width = video_stream.get("width") if video_stream else None
        height = video_stream.get("height") if video_stream else None
        video_codec = video_stream.get("codec_name") if video_stream else None
        audio_codec = audio_stream.get("codec_name") if audio_stream else None
        fps = eval(video_stream.get("r_frame_rate", "0")) if video_stream and video_stream.get("r_frame_rate") else None
    except Exception:
        duration = None
        width = None
        height = None
        video_codec = None
        audio_codec = None
        fps = None
    
    # Get next version number
    result = await db.execute(
        select(MediaVersion).where(MediaVersion.media_id == media_id).order_by(MediaVersion.version_number.desc())
    )
    last_version = result.scalars().first()
    version_number = (last_version.version_number + 1) if last_version else 1
    
    version = MediaVersion(
        media_id=media_id,
        version_number=version_number,
        label=f"Burned Subtitles ({font_size}pt, {position})",
        stored_filename=output_filename,
        original_filename=media.original_filename,
        file_size=file_size,
        mime_type="video/mp4",
        duration=duration,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        fps=str(fps) if fps else None,
        processing_status="completed",
    )
    
    db.add(version)
    await db.commit()
    await db.refresh(version)
    
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "label": version.label,
        "stored_filename": version.stored_filename,
        "processing_status": version.processing_status,
        "created_at": version.created_at.isoformat(),
    }


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



@router.post("/{media_id}/edit")
async def edit_subtitle(
    media_id: UUID,
    data: SubtitleEditRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if data.operation not in {"update_text", "update_timing", "add_entry"}:
        raise HTTPException(status_code=400, detail="Only supported subtitle editing operations are available")
    if data.entry_index is None:
        raise HTTPException(status_code=422, detail="entry_index is required for subtitle editing")

    result = await db.execute(
        select(Media).where(Media.id == media_id, Media.user_id == current_user.id)
    )
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    subtitle_file = get_uploaded_file(data.subtitle_path)
    if not subtitle_file.exists():
        raise HTTPException(status_code=404, detail="Subtitle file not found")

    output_filename = f"{media_id}_subtitle_edited_{uuid4().hex[:8]}{subtitle_file.suffix.lower()}"
    output_path = Path(settings.processed_dir) / output_filename
    try:
        if data.operation == "update_text":
            update_subtitle_text(
                str(subtitle_file),
                str(output_path),
                data.entry_index,
                data.text,
            )
        elif data.operation == "update_timing":
            update_subtitle_timing(
                str(subtitle_file),
                str(output_path),
                data.entry_index,
                data.start,
                data.end,
            )
        else:
            add_subtitle_entry(
                str(subtitle_file),
                str(output_path),
                data.entry_index,
                data.start,
                data.end,
                data.text,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type = {
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",
        ".ass": "text/plain",
        ".sub": "text/plain",
        ".txt": "text/plain",
    }.get(subtitle_file.suffix.lower(), "text/plain")
    return FileResponse(path=output_path, media_type=media_type, filename=output_filename)


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
    subtitle_file = get_uploaded_file(data.subtitle_path)
    if not subtitle_file.exists():
        raise HTTPException(status_code=404, detail="Subtitle file not found")

    output_filename = f"{media_id}_synced_{uuid4().hex[:8]}.mp4"
    output_path = Path(settings.processed_dir) / output_filename
    shifted_subtitle_path = Path(settings.temp_dir) / f"{media_id}_subtitle_shift_{uuid4().hex}{subtitle_file.suffix}"

    try:
        shift_subtitle_timestamps(str(subtitle_file), str(shifted_subtitle_path), data.offset_seconds)

        video_input = ffmpeg.input(str(input_path))
        subtitle_input = ffmpeg.input(str(shifted_subtitle_path))
        (
            ffmpeg
            .output(
                video_input.video,
                video_input.audio,
                subtitle_input['s'],
                str(output_path),
                vcodec="copy",
                acodec="copy",
                scodec="mov_text",
                map_metadata=0,
                shortest=None,
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )
    except (ffmpeg.Error, ValueError) as exc:
        error = exc.stderr.decode(errors="replace") if isinstance(exc, ffmpeg.Error) and exc.stderr else str(exc)
        raise HTTPException(status_code=500, detail=error or "FFmpeg subtitle sync failed") from exc
    finally:
        shifted_subtitle_path.unlink(missing_ok=True)

    return FileResponse(path=output_path, media_type="video/mp4", filename=output_filename)
