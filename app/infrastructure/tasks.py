from uuid import UUID

from sqlalchemy import select

from app.features.media.conversion import compress_media, convert_media
from app.features.media.models import Media, MediaVersion
from app.features.media.processor import (
    get_uploaded_file,
    process_media,
)
from app.features.projects.models import Project
from app.features.jobs.models import ProcessingJob
from app.features.jobs.service import (
    create_processing_job,
    update_processing_job,
    set_processing_progress,
)
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.ffmpeg import get_video_info, probe_media
from app.features.media.editing import (
    add_image_overlay,
    add_text_overlay,
    add_watermark,
    freeze_frame,
    transform_media,
)
from app.features.media.engine import ProcessingEngine, ProcessingEngineError
from app.features.media.schemas import ProcessingRequest
from app.features.auth.models import User

engine = ProcessingEngine()


async def process_media_unified_task(
    ctx,
    media_id: str,
    operations: list[dict],
    job_id: str,
    user_id: str | None = None,
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

        job = await create_processing_job(
            db,
            media_id=media.id,
            user_id=UUID(user_id) if user_id else None,
            task_name="process_media_unified_task",
            operation_type="unified",
            operation_params={"operations": operations},
            arq_job_id=job_id,
            input_filename=media.stored_filename,
        )

        try:
            await update_processing_job(db, job, status="running", progress=10, stage="Initializing")
            await set_processing_progress(media_id, "processing", 10, job_id=job_id, stage="Initializing", task_name="process_media_unified_task")

            request = ProcessingRequest(media_id=media_id, operations=operations)

            await update_processing_job(db, job, progress=25, stage="Running processing pipeline")
            await set_processing_progress(media_id, "processing", 25, job_id=job_id, stage="Running processing pipeline", task_name="process_media_unified_task")

            result = await engine.execute(request)

            await update_processing_job(
                db,
                job,
                status="completed",
                progress=100,
                stage="Processing completed",
                output_filename=result.get("output_filename"),
            )
            await set_processing_progress(media_id, "completed", 100, job_id=job_id, stage="Processing completed", task_name="process_media_unified_task")

            media.processed_filename = result.get("output_filename")
            media.processing_status = "completed"
            media.processing_error = None
            await db.commit()

            return result

        except ProcessingEngineError as exc:
            await db.rollback()
            await update_processing_job(db, job, status="failed", error=str(exc)[:500])
            await set_processing_progress(media_id, "failed", 0, job_id=job_id, error=str(exc)[:500], stage="Processing failed", task_name="process_media_unified_task")
            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]
            await db.commit()
            return {"status": "failed", "error": str(exc)}
        except Exception as exc:
            await db.rollback()
            await update_processing_job(db, job, status="failed", error=str(exc)[:500])
            await set_processing_progress(media_id, "failed", 0, job_id=job_id, error=str(exc)[:500], stage="Processing failed", task_name="process_media_unified_task")
            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]
            await db.commit()
            return {"status": "failed", "error": str(exc)}


async def _update_progress(
    ctx,
    media_id: str,
    status: str,
    progress: int,
    stage: str | None = None,
    error: str | None = None,
    task_name: str | None = None,
):
    try:
        job_id = ctx.get("job_id") if isinstance(ctx, dict) else None
        redis = ctx.get("redis") if isinstance(ctx, dict) else None
        await set_processing_progress(
            media_id=media_id,
            status=status,
            progress=progress,
            job_id=job_id,
            stage=stage,
            error=error,
            task_name=task_name,
            redis=redis,
        )
    except Exception:
        pass


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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing media processing", task_name="process_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Processing completed", task_name="process_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Processing failed", error=str(exc)[:500], task_name="process_media_task")

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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing conversion", task_name="convert_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Conversion completed", task_name="convert_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Conversion failed", error=str(exc)[:500], task_name="convert_media_task")

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }


async def compress_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
    output_filename: str,
    options: dict,
    target_size_mb: int | None = None,
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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing compression", task_name="compress_media_task")

            input_path = get_uploaded_file(stored_filename)
            output_path = get_uploaded_file(output_filename)

            preset = options.get("compression_preset", "balanced")
            stats = compress_media(
                str(input_path),
                str(output_path),
                preset=preset,
                target_size_mb=target_size_mb,
            )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None
            await db.commit()
            await _update_progress(ctx, media_id, "completed", 100, stage="Compression completed", task_name="compress_media_task")

            return {
                "media_id": media_id,
                "status": "completed",
                "output_filename": output_filename,
                "compression_stats": {
                    "original_size": stats["original_size"],
                    "processed_size": stats["processed_size"],
                    "bytes_saved": stats["bytes_saved"],
                    "percentage_saved": stats["percentage_saved"],
                },
            }

        except Exception as exc:
            await db.rollback()
            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]
            await db.commit()
            await _update_progress(ctx, media_id, "failed", 0, stage="Compression failed", error=str(exc)[:500], task_name="compress_media_task")
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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing edit", task_name="edit_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Edit completed", task_name="edit_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Edit failed", error=str(exc)[:500], task_name="edit_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Merge completed", task_name="merge_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Merge failed", error=str(exc)[:500], task_name="merge_media_task")

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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing transformation", task_name="transform_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Transformation completed", task_name="transform_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Transformation failed", error=str(exc)[:500], task_name="transform_media_task")

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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing freeze frame", task_name="freeze_frame_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Freeze frame completed", task_name="freeze_frame_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Freeze frame failed", error=str(exc)[:500], task_name="freeze_frame_task")

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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing overlay", task_name="overlay_media_task")

            input_path = get_uploaded_file(
                stored_filename
            )
            output_path = get_uploaded_file(
                output_filename
            )

            from app.features.media.editing import apply_multiple_overlays

            if "overlays" in options and options["overlays"]:
                operation = "multi_overlay"
                prepared_overlays = []
                for item in options["overlays"]:
                    entry = dict(item)
                    if entry.get("operation") in ("image", "watermark") and entry.get("image_filename"):
                        entry["image_path"] = str(get_uploaded_file(entry["image_filename"]))
                    prepared_overlays.append(entry)
                apply_multiple_overlays(
                    str(input_path),
                    str(output_path),
                    prepared_overlays,
                )
            else:
                operation = options.get("operation")
                if operation == "text":
                    add_text_overlay(
                        str(input_path),
                        str(output_path),
                        options["text"],
                        options.get("x", 10),
                        options.get("y", 10),
                        options.get("font_size", 32),
                    )
                elif operation == "image":
                    overlay_path = get_uploaded_file(
                        options["image_filename"]
                    )
                    add_image_overlay(
                        str(input_path),
                        str(overlay_path),
                        str(output_path),
                        options.get("x", 10),
                        options.get("y", 10),
                        options.get("opacity", 1.0),
                    )
                elif operation == "watermark":
                    watermark_path = get_uploaded_file(
                        options["image_filename"]
                    )
                    add_watermark(
                        str(input_path),
                        str(watermark_path),
                        str(output_path),
                        options.get("x", 10),
                        options.get("y", 10),
                        options.get("opacity", 1.0),
                    )
                else:
                    raise ValueError(
                        "Operation must be text, image, or watermark"
                    )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()
            await _update_progress(ctx, media_id, "completed", 100, stage="Overlay completed", task_name="overlay_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Overlay failed", error=str(exc)[:500], task_name="overlay_media_task")

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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing split", task_name="split_media_task")

            input_path = get_uploaded_file(stored_filename)
            info = get_video_info(str(input_path))
            total_duration = info.get("duration", 0.0)

            valid_pts = [p for p in sorted(split_points) if 0 < p < total_duration]
            num_clips = len(valid_pts) + 1

            output_filenames = [
                f"{output_prefix}_clip_{i + 1}.mp4" for i in range(num_clips)
            ]
            output_paths = [str(get_uploaded_file(f)) for f in output_filenames]

            split_media(str(input_path), split_points, output_paths)

            media.processed_filename = output_filenames[0]
            media.processing_status = "completed"
            media.processing_error = None
            await db.commit()
            await _update_progress(ctx, media_id, "completed", 100, stage="Split completed", task_name="split_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Split failed", error=str(exc)[:500], task_name="split_media_task")
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
            await _update_progress(ctx, media_id, "processing", 15, stage="Initializing clips operation", task_name="clips_media_task")

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
            await _update_progress(ctx, media_id, "completed", 100, stage="Clips operation completed", task_name="clips_media_task")

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
            await _update_progress(ctx, media_id, "failed", 0, stage="Clips operation failed", error=str(exc)[:500], task_name="clips_media_task")
            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }


async def execute_workflow_task(
    ctx,
    workflow_id: str,
    media_id: str,
    job_id: str,
    user_id: str | None = None,
):
    import json
    from uuid import UUID
    from sqlalchemy import select

    from app.features.workflows.models import Workflow
    from app.features.media.models import Media
    from app.features.media.engine import ProcessingEngine
    from app.features.media.schemas import ProcessingRequest
    from app.features.jobs.models import ProcessingJob
    from app.features.jobs.service import (
        create_processing_job,
        update_processing_job,
        set_processing_progress,
    )
    from app.infrastructure.database import AsyncSessionLocal

    engine = ProcessingEngine()

    async with AsyncSessionLocal() as db:
        # Load workflow
        result = await db.execute(
            select(Workflow).where(Workflow.id == UUID(workflow_id))
        )
        workflow = result.scalar_one_or_none()

        if workflow is None:
            return {
                "workflow_id": workflow_id,
                "media_id": media_id,
                "status": "failed",
                "error": "Workflow not found",
            }

        # Load media
        result = await db.execute(
            select(Media).where(Media.id == UUID(media_id))
        )
        media = result.scalar_one_or_none()

        if media is None:
            return {
                "workflow_id": workflow_id,
                "media_id": media_id,
                "status": "failed",
                "error": "Media not found",
            }

        # Create processing job for tracking
        job = await create_processing_job(
            db,
            media_id=media.id,
            user_id=UUID(user_id) if user_id else None,
            task_name="execute_workflow_task",
            operation_type="workflow",
            operation_params=json.dumps({"workflow_id": workflow_id, "workflow_name": workflow.name}),
            arq_job_id=job_id,
            input_filename=media.stored_filename,
        )

        try:
            await update_processing_job(db, job, status="running", progress=10, stage="Initializing workflow")
            await set_processing_progress(media_id, "processing", 10, job_id=job_id, stage="Initializing workflow", task_name="execute_workflow_task")

            # Parse workflow operations
            workflow_ops = json.loads(workflow.operations) if workflow.operations else []

            # Map workflow operations to ProcessingEngine operations
            processing_ops = _map_workflow_operations(workflow_ops)

            if not processing_ops:
                await update_processing_job(db, job, status="failed", error="No valid operations in workflow")
                await set_processing_progress(media_id, "failed", 0, job_id=job_id, error="No valid operations in workflow", stage="Workflow failed", task_name="execute_workflow_task")
                return {"status": "failed", "error": "No valid operations in workflow"}

            await update_processing_job(db, job, progress=25, stage=f"Running workflow ({len(processing_ops)} operations)")
            await set_processing_progress(media_id, "processing", 25, job_id=job_id, stage=f"Running workflow ({len(processing_ops)} operations)", task_name="execute_workflow_task")

            # Execute through ProcessingEngine
            request = ProcessingRequest(media_id=media_id, operations=processing_ops)
            result = await engine.execute(request)

            await update_processing_job(
                db,
                job,
                status="completed",
                progress=100,
                stage="Workflow completed",
                output_filename=result.get("output_filename"),
            )
            await set_processing_progress(media_id, "completed", 100, job_id=job_id, stage="Workflow completed", task_name="execute_workflow_task")

            media.processed_filename = result.get("output_filename")
            media.processing_status = "completed"
            media.processing_error = None
            await db.commit()

            return result

        except Exception as exc:
            await db.rollback()
            await update_processing_job(db, job, status="failed", error=str(exc)[:500])
            await set_processing_progress(media_id, "failed", 0, job_id=job_id, error=str(exc)[:500], stage="Workflow failed", task_name="execute_workflow_task")
            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]
            await db.commit()
            return {"status": "failed", "error": str(exc)}


def _map_workflow_operations(workflow_ops: list[dict]) -> list[dict]:
    """Map workflow operations to ProcessingEngine operations."""
    processing_ops = []

    for op in workflow_ops:
        op_type = op.get("type")
        params = op.get("params", {})

        if op_type == "convert":
            processing_ops.append({
                "type": "convert",
                "format": params.get("format", "mp4"),
                "video_codec": params.get("video_codec"),
                "audio_codec": params.get("audio_codec"),
                "video_bitrate": params.get("video_bitrate"),
                "audio_bitrate": params.get("audio_bitrate"),
                "width": params.get("width"),
                "height": params.get("height"),
                "fps": params.get("fps"),
                "quality": params.get("quality"),
                "aspect_ratio": params.get("aspect_ratio"),
            })
        elif op_type == "compress":
            # Map compress to convert with compression settings
            processing_ops.append({
                "type": "convert",
                "format": params.get("format", "mp4"),
                "video_bitrate": params.get("video_bitrate"),
                "audio_bitrate": params.get("audio_bitrate"),
                "width": params.get("width"),
                "height": params.get("height"),
                "quality": params.get("quality"),
                "video_codec": "libx264",
                "audio_codec": "aac",
            })
        elif op_type == "extract_audio":
            processing_ops.append({
                "type": "extract_audio",
                "format": params.get("format", "mp3"),
                "bitrate": params.get("bitrate"),
                "sample_rate": params.get("sample_rate"),
            })
        elif op_type == "generate_thumbnail":
            processing_ops.append({
                "type": "freeze",
                "timestamp": params.get("timestamp", 0),
                "duration": params.get("duration", 1),
            })
        elif op_type == "trim":
            processing_ops.append({
                "type": "trim",
                "start": params.get("start", 0),
                "end": params.get("end", 0),
            })
        elif op_type == "cut":
            processing_ops.append({
                "type": "cut",
                "start": params.get("start", 0),
                "end": params.get("end", 0),
            })
        elif op_type == "crop":
            processing_ops.append({
                "type": "crop",
                "width": params.get("width"),
                "height": params.get("height"),
                "x": params.get("x", 0),
                "y": params.get("y", 0),
            })
        elif op_type == "resize":
            processing_ops.append({
                "type": "resize",
                "width": params.get("width"),
                "height": params.get("height"),
            })
        elif op_type == "rotate":
            processing_ops.append({
                "type": "rotate",
                "angle": params.get("angle", 90),
            })
        elif op_type == "remove_audio":
            processing_ops.append({
                "type": "convert",
                "format": params.get("format", "mp4"),
                "audio_codec": "none",
            })
        elif op_type == "replace_audio":
            processing_ops.append({
                "type": "audio_replace",
                "audio_path": params.get("audio_path"),
                "fade_in": params.get("fade_in"),
                "fade_out": params.get("fade_out"),
            })
        elif op_type == "speed":
            processing_ops.append({
                "type": "speed",
                "speed": params.get("speed", 1.0),
            })
        elif op_type == "overlay":
            # Determine overlay type from params
            if params.get("text"):
                processing_ops.append({
                    "type": "text_overlay",
                    "text": params.get("text"),
                    "x": params.get("x", 10),
                    "y": params.get("y", 10),
                    "font_size": params.get("font_size", 32),
                    "font_color": params.get("font_color", "white"),
                })
            elif params.get("image_path") or params.get("image_filename"):
                processing_ops.append({
                    "type": "image_overlay",
                    "image_path": params.get("image_path") or params.get("image_filename"),
                    "x": params.get("x", 10),
                    "y": params.get("y", 10),
                    "opacity": params.get("opacity", 1.0),
                })
        elif op_type == "fade":
            processing_ops.append({
                "type": "audio_volume",
                "volume": 1.0,
                "fade_in": params.get("duration") if params.get("fade_type") == "in" else 0,
                "fade_out": params.get("duration") if params.get("fade_type") == "out" else 0,
            })

    return processing_ops


async def execute_batch_task(
    ctx,
    batch_job_id: str,
    media_ids: list[str],
    operation: str,
    options: dict,
    job_id: str,
    user_id: str | None = None,
):
    import json
    from uuid import UUID
    from sqlalchemy import select
    import asyncio

    from app.features.media.models import Media
    from app.features.media.engine import ProcessingEngine
    from app.features.media.schemas import ProcessingRequest
    from app.features.jobs.models import ProcessingJob
    from app.features.jobs.service import (
        create_processing_job,
        update_processing_job,
        set_processing_progress,
    )
    from app.infrastructure.database import AsyncSessionLocal

    engine = ProcessingEngine()

    async with AsyncSessionLocal() as db:
        # Load batch job
        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == UUID(batch_job_id))
        )
        batch_job = result.scalar_one_or_none()

        if batch_job is None:
            return {
                "batch_job_id": batch_job_id,
                "status": "failed",
                "error": "Batch job not found",
            }

        # Load media items
        media_uuids = [UUID(mid) for mid in media_ids]
        result = await db.execute(
            select(Media).where(Media.id.in_(media_uuids))
        )
        media_items = list(result.scalars().all())

        if not media_items:
            await update_processing_job(db, batch_job, status="failed", error="No valid media found")
            return {"status": "failed", "error": "No valid media found"}

        # Map batch operation to ProcessingEngine operations
        processing_ops = _map_batch_operation(operation, options)
        if not processing_ops:
            await update_processing_job(db, batch_job, status="failed", error=f"Unknown batch operation: {operation}")
            return {"status": "failed", "error": f"Unknown batch operation: {operation}"}

        total_items = len(media_items)
        completed = 0
        failed = 0
        results = []

        # Update batch job progress
        await update_processing_job(db, batch_job, status="running", progress=5, stage=f"Starting batch {operation} for {total_items} items")
        await set_processing_progress(batch_job_id, "processing", 5, job_id=job_id, stage=f"Starting batch {operation} for {total_items} items", task_name="execute_batch_task")

        # Process items in parallel (with semaphore to limit concurrency)
        semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent processing jobs

        async def process_single_media(media_item: Media, index: int):
            nonlocal completed, failed
            media_id = str(media_item.id)

            async with semaphore:
                try:
                    # Create individual job for tracking
                    item_job_id = f"{job_id}_item_{index}"
                    await set_processing_progress(media_id, "queued", 0, job_id=item_job_id, stage=f"Queued in batch ({index+1}/{total_items})", task_name="execute_batch_task")

                    request = ProcessingRequest(media_id=media_id, operations=processing_ops)
                    result = await engine.execute(request)

                    completed += 1
                    results.append({
                        "media_id": media_id,
                        "filename": media_item.original_filename,
                        "status": "completed",
                        "output_filename": result.get("output_filename"),
                    })

                    # Update batch progress
                    progress = int(5 + (completed + failed) / total_items * 90)
                    await update_processing_job(db, batch_job, progress=progress, stage=f"Completed {completed}/{total_items}")
                    await set_processing_progress(batch_job_id, "processing", progress, job_id=job_id, stage=f"Completed {completed}/{total_items}", task_name="execute_batch_task")

                except Exception as exc:
                    failed += 1
                    results.append({
                        "media_id": media_id,
                        "filename": media_item.original_filename,
                        "status": "failed",
                        "error": str(exc)[:500],
                    })

                    # Update batch progress
                    progress = int(5 + (completed + failed) / total_items * 90)
                    await update_processing_job(db, batch_job, progress=progress, stage=f"Completed {completed}/{total_items}, Failed {failed}/{total_items}")
                    await set_processing_progress(batch_job_id, "processing", progress, job_id=job_id, stage=f"Completed {completed}/{total_items}, Failed {failed}/{total_items}", task_name="execute_batch_task")

        # Run all items concurrently
        await asyncio.gather(*[process_single_media(m, i) for i, m in enumerate(media_items)])

        # Final update
        final_status = "completed" if failed == 0 else ("failed" if completed == 0 else "completed")
        await update_processing_job(
            db,
            batch_job,
            status=final_status,
            progress=100,
            stage=f"Batch completed: {completed} succeeded, {failed} failed",
            operation_params=json.dumps({
                "operation": operation,
                "media_count": total_items,
                "options": options,
                "completed": completed,
                "failed": failed,
                "results": results,
            }),
        )
        await set_processing_progress(batch_job_id, final_status, 100, job_id=job_id, stage=f"Batch completed: {completed} succeeded, {failed} failed", task_name="execute_batch_task")

        return {
            "batch_job_id": batch_job_id,
            "status": final_status,
            "total_items": total_items,
            "completed": completed,
            "failed": failed,
            "results": results,
        }


def _map_batch_operation(operation: str, options: dict) -> list[dict]:
    """Map batch operation to ProcessingEngine operations."""
    processing_ops = []

    if operation == "convert":
        processing_ops.append({
            "type": "convert",
            "format": options.get("format", "mp4"),
            "video_codec": options.get("video_codec"),
            "audio_codec": options.get("audio_codec"),
            "video_bitrate": options.get("video_bitrate"),
            "audio_bitrate": options.get("audio_bitrate"),
            "width": options.get("width"),
            "height": options.get("height"),
            "fps": options.get("fps"),
            "quality": options.get("quality"),
            "aspect_ratio": options.get("aspect_ratio"),
        })
    elif operation == "compress":
        processing_ops.append({
            "type": "convert",
            "format": options.get("format", "mp4"),
            "video_bitrate": options.get("video_bitrate"),
            "audio_bitrate": options.get("audio_bitrate"),
            "width": options.get("width"),
            "height": options.get("height"),
            "quality": options.get("quality"),
            "video_codec": "libx264",
            "audio_codec": "aac",
        })
    elif operation == "extract_audio":
        processing_ops.append({
            "type": "extract_audio",
            "format": options.get("format", "mp3"),
            "bitrate": options.get("bitrate"),
            "sample_rate": options.get("sample_rate"),
        })
    elif operation == "generate_thumbnail":
        processing_ops.append({
            "type": "freeze",
            "timestamp": options.get("timestamp", 0),
            "duration": options.get("duration", 1),
        })
    elif operation == "generate_preview":
        processing_ops.append({
            "type": "trim",
            "start": options.get("start", 0),
            "end": options.get("start", 0) + options.get("duration", 5),
        })
    elif operation == "trim":
        processing_ops.append({
            "type": "trim",
            "start": options.get("start", 0),
            "end": options.get("end", 0),
        })
    elif operation == "cut":
        processing_ops.append({
            "type": "cut",
            "start": options.get("start", 0),
            "end": options.get("end", 0),
        })
    elif operation == "crop":
        processing_ops.append({
            "type": "crop",
            "width": options.get("width"),
            "height": options.get("height"),
            "x": options.get("x", 0),
            "y": options.get("y", 0),
        })
    elif operation == "resize":
        processing_ops.append({
            "type": "resize",
            "width": options.get("width"),
            "height": options.get("height"),
        })
    elif operation == "rotate":
        processing_ops.append({
            "type": "rotate",
            "angle": options.get("angle", 90),
        })
    elif operation == "remove_audio":
        processing_ops.append({
            "type": "convert",
            "format": options.get("format", "mp4"),
            "audio_codec": "none",
        })
    elif operation == "replace_audio":
        processing_ops.append({
            "type": "audio_replace",
            "audio_path": options.get("audio_path"),
            "fade_in": options.get("fade_in"),
            "fade_out": options.get("fade_out"),
        })
    elif operation == "add_subtitles":
        # Subtitle operations would need a different approach
        # For now, map to a basic convert
        processing_ops.append({
            "type": "convert",
            "format": options.get("format", "mp4"),
        })
    elif operation == "create_gif":
        processing_ops.append({
            "type": "convert",
            "format": "gif",
            "fps": options.get("fps", 10),
            "width": options.get("width", 480),
        })

    return processing_ops
