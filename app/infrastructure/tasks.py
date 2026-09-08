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
from app.features.media.editing import (
    add_image_overlay,
    add_text_overlay,
    add_watermark,
    freeze_frame,
    transform_media,
)


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


async def merge_media_task(
    ctx,
    media_id: str,
    input_filenames: list[str],
    output_filename: str,
):
    from app.features.media.merge import merge_media

    async with AsyncSessionLocal() as db:
        try:
            input_paths = [
                str(get_uploaded_file(filename))
                for filename in input_filenames
            ]

            output_path = get_uploaded_file(output_filename)

            merge_media(
                input_paths,
                str(output_path),
            )

            result = await db.execute(
                select(Media).where(Media.id == UUID(media_id))
            )
            media = result.scalar_one_or_none()

            if media is None:
                return {
                    "status": "failed",
                    "error": "Media not found",
                }

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

            result = await db.execute(
                select(Media).where(Media.id == UUID(media_id))
            )
            media = result.scalar_one_or_none()

            if media:
                media.processing_status = "failed"
                media.processing_error = str(exc)[:500]
                await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }

async def transform_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    options: dict,
):
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media is None:
                return {
                    "status": "failed",
                    "error": "Media not found",
                }

            media.processing_status = "processing"
            media.processing_error = None
            await db.commit()

            input_path = get_uploaded_file(
                stored_filename
            )
            output_path = get_uploaded_file(
                output_filename
            )

            transform_media(
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
                "operation": options["operation"],
                "output_filename": output_filename,
            }

        except Exception as exc:
            await db.rollback()

            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media:
                media.processing_status = "failed"
                media.processing_error = str(exc)[:500]
                await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }


async def freeze_frame_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    timestamp: float,
    duration: float,
):
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media is None:
                return {
                    "status": "failed",
                    "error": "Media not found",
                }

            media.processing_status = "processing"
            await db.commit()

            input_path = get_uploaded_file(
                stored_filename
            )
            output_path = get_uploaded_file(
                output_filename
            )

            freeze_frame(
                str(input_path),
                str(output_path),
                timestamp,
                duration,
            )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "operation": "freeze",
                "output_filename": output_filename,
            }

        except Exception as exc:
            await db.rollback()

            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media:
                media.processing_status = "failed"
                media.processing_error = str(exc)[:500]
                await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }


async def overlay_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    options: dict,
):
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media is None:
                return {
                    "status": "failed",
                    "error": "Media not found",
                }

            media.processing_status = "processing"
            await db.commit()

            input_path = get_uploaded_file(
                stored_filename
            )
            output_path = get_uploaded_file(
                output_filename
            )

            operation = options["operation"]

            if operation == "text":
                add_text_overlay(
                    str(input_path),
                    str(output_path),
                    options["text"],
                    options["x"],
                    options["y"],
                    options["font_size"],
                )

            elif operation == "image":
                overlay_path = get_uploaded_file(
                    options["image_filename"]
                )

                add_image_overlay(
                    str(input_path),
                    str(overlay_path),
                    str(output_path),
                    options["x"],
                    options["y"],
                    options["opacity"],
                )

            elif operation == "watermark":
                watermark_path = get_uploaded_file(
                    options["image_filename"]
                )

                add_watermark(
                    str(input_path),
                    str(watermark_path),
                    str(output_path),
                    options["x"],
                    options["y"],
                    options["opacity"],
                )

            else:
                raise ValueError(
                    "Operation must be text, image, or watermark"
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

            result = await db.execute(
                select(Media).where(
                    Media.id == UUID(media_id)
                )
            )

            media = result.scalar_one_or_none()

            if media:
                media.processing_status = "failed"
                media.processing_error = str(exc)[:500]
                await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }

async def split_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_prefix: str,
    split_points: list[float],
):
    from app.features.media.editing import split_media
    from app.infrastructure.ffmpeg import get_video_info

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
            info = get_video_info(str(input_path))
            total_duration = info.get("duration", 0.0)

            # Determine number of intervals
            valid_pts = [p for p in sorted(split_points) if 0 < p < total_duration]
            num_clips = len(valid_pts) + 1

            output_filenames = [
                f"{output_prefix}_clip_{i + 1}.mp4" for i in range(num_clips)
            ]
            output_paths = [str(get_uploaded_file(f)) for f in output_filenames]

            split_media(str(input_path), split_points, output_paths)

            # Store the first clip or comma-separated list as processed_filename
            media.processed_filename = output_filenames[0]
            media.processing_status = "completed"
            media.processing_error = None
            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "operation": "split",
                "output_filenames": output_filenames,
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


async def clips_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    operation: str,
    clips: list[list[float]],
):
    from app.features.media.editing import (
        delete_selected_clips,
        keep_selected_clips,
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

            clip_tuples = [(float(c[0]), float(c[1])) for c in clips]

            if operation == "keep":
                keep_selected_clips(
                    str(input_path),
                    str(output_path),
                    clip_tuples,
                )
            elif operation == "delete":
                delete_selected_clips(
                    str(input_path),
                    str(output_path),
                    clip_tuples,
                )
            else:
                raise ValueError(f"Unsupported clips operation: {operation}")

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
