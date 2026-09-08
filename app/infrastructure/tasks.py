from uuid import UUID

from sqlalchemy import select

from app.features.media.conversion import convert_media
from app.features.media.models import Media
from app.features.media.processor import (
    get_uploaded_file,
    process_media,
)
from app.features.projects.models import Project  # registers projects table
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.ffmpeg import get_video_info


async def process_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Media).where(Media.id == UUID(media_id))
        )

        media = result.scalar_one_or_none()

        if media is None:
            return {
                "media_id": media_id,
                "status": "failed",
                "error": "Media not found",
            }

        try:
            media.processing_status = "processing"
            media.processing_error = None
            await db.commit()

            output_filename = process_media(
                media.id,
                stored_filename,
            )

            processed_path = get_uploaded_file(output_filename)

            metadata = get_video_info(str(processed_path))

            media.processed_filename = output_filename
            media.duration = metadata.get("duration")
            media.width = metadata.get("width")
            media.height = metadata.get("height")
            media.video_codec = metadata.get("codec")
            media.fps = metadata.get("fps")

            from app.infrastructure.ffmpeg import probe_media

            probe = await probe_media(str(processed_path))

            audio_stream = next(
                (
                    stream
                    for stream in probe.get("streams", [])
                    if stream.get("codec_type") == "audio"
                ),
                None,
            )

            media.audio_codec = (
                audio_stream.get("codec_name")
                if audio_stream
                else None
            )

            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "output_filename": output_filename,
                "metadata": {
                    "duration": media.duration,
                    "width": media.width,
                    "height": media.height,
                    "video_codec": media.video_codec,
                    "audio_codec": media.audio_codec,
                    "fps": media.fps,
                },
            }

        except Exception as exc:
            await db.rollback()

            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]

            await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }


async def convert_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    options: dict,
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Media).where(Media.id == UUID(media_id))
        )

        media = result.scalar_one_or_none()

        if media is None:
            return {
                "media_id": media_id,
                "status": "failed",
                "error": "Media not found",
            }

        try:
            media.processing_status = "processing"
            media.processing_error = None
            await db.commit()

            input_path = get_uploaded_file(stored_filename)
            output_path = get_uploaded_file(output_filename)

            convert_media(
                str(input_path),
                str(output_path),
                **options,
            )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "output_filename": output_filename,
            }

        except Exception as exc:
            await db.rollback()

            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]

            await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }

async def edit_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    operation: str,
    start: float,
    end: float,
):
    from app.features.media.editing import (
        cut_media,
        extract_media,
        trim_media,
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Media).where(Media.id == UUID(media_id))
        )
        media = result.scalar_one_or_none()

        if media is None:
            return {
                "media_id": media_id,
                "status": "failed",
                "error": "Media not found",
            }

        try:
            media.processing_status = "processing"
            media.processing_error = None
            await db.commit()

            input_path = get_uploaded_file(stored_filename)
            output_path = get_uploaded_file(output_filename)

            if operation == "trim":
                trim_media(
                    str(input_path),
                    str(output_path),
                    start,
                    end,
                )
            elif operation == "extract":
                extract_media(
                    str(input_path),
                    str(output_path),
                    start,
                    end,
                )
            elif operation == "cut":
                cut_media(
                    str(input_path),
                    str(output_path),
                    start,
                    end,
                )
            else:
                raise ValueError(
                    f"Unsupported editing operation: {operation}"
                )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "operation": operation,
                "output_filename": output_filename,
            }

        except Exception as exc:
            await db.rollback()

            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]
            await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }