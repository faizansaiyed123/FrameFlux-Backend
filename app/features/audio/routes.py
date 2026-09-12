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
from app.features.media.service import get_media_type
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.features.audio.service import extract_audio, adjust_volume, replace_audio
from app.features.audio.processor import (
    convert_audio,
    trim_audio,
    cut_audio,
    split_audio,
    merge_audio,
    change_audio_speed,
    normalize_audio,
    apply_fade,
    add_silence,
    create_video_from_audio,
)
from app.features.audio.schemas import (
    AudioConvertRequest,
    AudioEditRequest,
    AudioToVideoRequest,
    BatchAudioExtractRequest,
    BatchAudioExtractResponse,
)

router = APIRouter(prefix="/audio", tags=["Audio"])


@router.get("/{media_id}/extract")
async def extract_audio_endpoint(
    media_id: UUID,
    format: str = "mp3",
    bitrate: str | None = None,
    sample_rate: int | None = None,
    start: float | None = None,
    end: float | None = None,
    channels: int | None = None,
    quality_preset: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    if media.media_type != "video" and media.media_type != "audio":
        raise HTTPException(status_code=400, detail="Media is not audio/video")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_audio_{uuid4().hex[:8]}.{format}"
    output_path = Path(settings.processed_dir) / output_filename

    extract_kwargs = {
        "format": format,
        "bitrate": bitrate,
        "sample_rate": sample_rate,
        "channels": channels,
        "quality": quality_preset,
    }
    if start is not None and end is not None:
        extract_kwargs["start"] = start
        extract_kwargs["end"] = end

    extract_audio(str(input_path), str(output_path), **extract_kwargs)
    return FileResponse(path=output_path, media_type=f"audio/{format}", filename=output_filename)


@router.post("/batch/extract", response_model=BatchAudioExtractResponse)
async def batch_extract_audio(
    data: BatchAudioExtractRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    jobs = []
    for media_id in data.media_ids:
        result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
        media = result.scalar_one_or_none()
        if media is None:
            continue
        jobs.append({
            "media_id": str(media_id),
            "format": data.format,
            "bitrate": data.bitrate,
            "sample_rate": data.sample_rate,
            "channels": data.channels,
        })
    return BatchAudioExtractResponse(jobs=jobs)


@router.post("/{media_id}/volume")
async def adjust_volume_endpoint(
    media_id: UUID,
    volume: float,
    fade_in: float | None = None,
    fade_out: float | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    output_filename = f"{media_id}_volume_{uuid4().hex[:8]}.mp4"
    input_path = get_uploaded_file(media.stored_filename)
    output_path = Path(settings.processed_dir) / output_filename
    adjust_volume(str(input_path), str(output_path), volume, fade_in, fade_out)
    return {"output_filename": output_filename}


@router.post("/{media_id}/replace-audio")
async def replace_audio_endpoint(
    media_id: UUID,
    audio_path: str,
    fade_in: float | None = None,
    fade_out: float | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    output_filename = f"{media_id}_replaced_audio_{uuid4().hex[:8]}.mp4"
    input_path = get_uploaded_file(media.stored_filename)
    audio_file = get_uploaded_file(audio_path)
    output_path = Path(settings.processed_dir) / output_filename
    replace_audio(str(input_path), str(audio_file), str(output_path), fade_in, fade_out)
    return {"output_filename": output_filename}


@router.post("/{media_id}/convert")
async def convert_audio_endpoint(
    media_id: UUID,
    data: AudioConvertRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    if media.media_type != "audio" and media.media_type != "video":
        raise HTTPException(status_code=400, detail="Media is not audio/video")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_converted_{uuid4().hex[:8]}.{data.format}"
    output_path = Path(settings.processed_dir) / output_filename
    convert_audio(
        str(input_path),
        str(output_path),
        format=data.format,
        bitrate=data.bitrate,
        sample_rate=data.sample_rate,
        channels=data.channels,
        quality=data.quality,
    )
    return FileResponse(path=output_path, media_type=f"audio/{data.format}", filename=output_filename)


@router.post("/{media_id}/edit")
async def edit_audio_endpoint(
    media_id: UUID,
    data: AudioEditRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    input_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp3"
    output_path = Path(settings.processed_dir) / output_filename

    if data.operation == "trim" and data.start is not None and data.end is not None:
        trim_audio(str(input_path), str(output_path), data.start, data.end)
    elif data.operation == "cut" and data.start is not None and data.end is not None:
        cut_audio(str(input_path), str(output_path), data.start, data.end)
    elif data.operation == "split" and data.start is not None and data.end is not None:
        split_audio(str(input_path), str(Path(settings.processed_dir) / f"{media_id}_split"), data.start, data.end)
    elif data.operation == "merge" and data.target_files:
        merge_audio(data.target_files, str(output_path))
    elif data.operation == "speed" and data.speed is not None:
        change_audio_speed(str(input_path), str(output_path), data.speed)
    elif data.operation == "normalize":
        normalize_audio(str(input_path), str(output_path))
    elif data.operation == "fade":
        apply_fade(str(input_path), str(output_path), data.fade_in, data.fade_out)
    elif data.operation == "silence" and data.silence_duration is not None:
        add_silence(str(input_path), str(output_path), data.silence_duration)
    else:
        raise HTTPException(status_code=400, detail="Invalid operation or missing parameters")

    return {"output_filename": output_filename}


@router.post("/{media_id}/to-video")
async def audio_to_video_endpoint(
    media_id: UUID,
    data: AudioToVideoRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    audio_path = get_uploaded_file(media.stored_filename)
    output_filename = f"{media_id}_video_{uuid4().hex[:8]}.{data.output_format}"
    output_path = Path(settings.processed_dir) / output_filename

    bg_image = get_uploaded_file(data.background_image) if data.background_image else None
    watermark_path = get_uploaded_file(data.watermark) if data.watermark else None

    create_video_from_audio(
        str(audio_path),
        str(output_path),
        background_image=bg_image,
        background_color=data.background_color,
        title=data.title,
        text=data.text,
        watermark=watermark_path,
        show_waveform=data.show_waveform,
        visualizer_style=data.visualizer_style,
        resolution=data.resolution,
        fps=data.fps,
        aspect_ratio=data.aspect_ratio,
        duration=data.duration,
        output_format=data.output_format,
    )
    return FileResponse(path=output_path, media_type=f"video/{data.output_format}", filename=output_filename)
