from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.features.media.schemas import (
    MediaConvertRequest,
    MediaEditRequest,
    MediaMergeRequest,
    MediaTransformRequest,
    MediaFreezeFrameRequest,
    MediaOverlayRequest,
    MediaResponse,
    MediaSplitRequest,
    MediaClipsRequest,
    MediaProcessingStatusResponse,
)
from app.features.jobs.schemas import JobStatusResponse
from app.features.jobs.service import (
    get_job_status,
    get_media_progress,
    set_processing_progress,
)
from app.features.media.service import delete_media_file, save_upload
from app.features.projects.service import get_project
from app.infrastructure.database import get_db
from app.features.media.processor import get_uploaded_file
from app.infrastructure.worker import create_worker_pool

from app.features.media.resumable_service import ResumableUploadService
from app.features.media.schemas import (
    ResumableInitRequest,
    ResumableInitResponse,
    ChunkUploadResponse,
    ActionResponse,
)


router = APIRouter(
    prefix="/media",
    tags=["Media"],
)


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

async def get_media_or_404(
    media_id: UUID,
    db: AsyncSession,
    user_id: UUID | None = None,
) -> Media:
    result = await db.execute(
        select(Media).where(Media.id == media_id)
    )

    media = result.scalar_one_or_none()

    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    media_user_id = getattr(media, "user_id", None)
    if user_id is not None and media_user_id is not None and media_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found",
        )

    return media


async def verify_media_references_ownership(
    media_refs: list[str],
    user_id: UUID,
    db: AsyncSession,
) -> None:
    for ref in media_refs:
        if ".." in ref or "/" in ref or "\\" in ref:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid media reference",
            )
        query = select(Media)
        try:
            val_uuid = UUID(ref)
            query = query.where((Media.id == val_uuid) | (Media.stored_filename == ref))
        except (ValueError, TypeError):
            query = query.where(Media.stored_filename == ref)

        result = await db.execute(query)
        matched_media = result.scalars().first()
        if isinstance(matched_media, Media):
            if matched_media.user_id is not None and matched_media.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot reference media belonging to another user",
                )


def verify_file_path_safety(file_path: Path, storage_dir: Path) -> Path:
    resolved_storage = storage_dir.resolve()
    resolved_file = file_path.resolve()
    try:
        resolved_file.relative_to(resolved_storage)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to path outside storage directory is forbidden",
        )
    if not resolved_file.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )
    return resolved_file


async def enqueue_media_job(
    task_name: str,
    *args,
):
    pool = await create_worker_pool()

    try:
        job = await pool.enqueue_job(
            task_name,
            *args,
        )
        if job and args:
            media_id = str(args[0])
            await set_processing_progress(
                media_id=media_id,
                status="queued",
                progress=0,
                job_id=job.job_id,
                stage="Queued for processing",
                task_name=task_name,
                redis=pool,
            )
        return job
    finally:
        await pool.close()


async def mark_processing_pending(
    media: Media,
    db: AsyncSession,
):
    media.processing_status = "pending"
    media.processing_error = None

    await db.commit()


# ---------------------------------------------------------
# UPLOAD
# ---------------------------------------------------------

@router.post(
    "/upload",
    response_model=MediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_media(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        media = await save_upload(file)
        media.user_id = current_user.id

        db.add(media)
        await db.commit()
        await db.refresh(media)

        return media

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ---------------------------------------------------------

# ---------------------------------------------------------
# RESUMABLE UPLOAD
# ---------------------------------------------------------

@router.post("/resumable/init", response_model=ResumableInitResponse)
async def resumable_init(
    data: ResumableInitRequest,
    current_user: User = Depends(get_current_active_user),
):
    """Initialize a resumable upload and return an upload_id."""
    try:
        upload_id = await ResumableUploadService.init_upload(
            original_filename=data.original_filename,
            total_size=data.total_size,
            chunk_size=data.chunk_size,
            user_id=current_user.id,
        )
        return ResumableInitResponse(upload_id=str(upload_id))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

@router.post("/resumable/{upload_id}/chunk/{index}", response_model=ChunkUploadResponse)
async def resumable_chunk(
    upload_id: UUID,
    index: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
):
    """Upload a single chunk for the given upload_id."""
    if index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk index must be non-negative")
    content = await file.read()
    try:
        await ResumableUploadService.store_chunk(upload_id, index, content, user_id=current_user.id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ChunkUploadResponse()

@router.post("/resumable/{upload_id}/pause", response_model=ActionResponse)
async def resumable_pause(
    upload_id: UUID,
    current_user: User = Depends(get_current_active_user),
):
    try:
        await ResumableUploadService.pause(upload_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="paused")

@router.post("/resumable/{upload_id}/resume", response_model=ActionResponse)
async def resumable_resume(
    upload_id: UUID,
    current_user: User = Depends(get_current_active_user),
):
    try:
        await ResumableUploadService.resume(upload_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="resumed")

@router.post("/resumable/{upload_id}/retry", response_model=ChunkUploadResponse)
async def resumable_retry(
    upload_id: UUID,
    index: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> ChunkUploadResponse:
    """Retry uploading a single chunk for the given upload_id."""
    if index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk index must be non-negative")
    content = await file.read()
    try:
        await ResumableUploadService.store_chunk(upload_id, index, content, user_id=current_user.id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ChunkUploadResponse()

@router.delete("/resumable/{upload_id}", response_model=ActionResponse)
async def resumable_cancel(
    upload_id: UUID,
    current_user: User = Depends(get_current_active_user),
):
    try:
        await ResumableUploadService.cancel(upload_id, user_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="canceled")

@router.post("/resumable/{upload_id}/finalize", response_model=MediaResponse)
async def resumable_finalize(
    upload_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Assemble chunks and create a Media record."""
    try:
        media = await ResumableUploadService.finalize(upload_id, db, user_id=current_user.id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return media

# ---------------------------------------------------------
# LIST MEDIA
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[MediaResponse],
)
async def list_media(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media)
        .where((Media.user_id == current_user.id) | (Media.user_id.is_(None)))
        .order_by(Media.created_at.desc())
    )

    return result.scalars().all()


# ---------------------------------------------------------
# GET MEDIA
# ---------------------------------------------------------

@router.get(
    "/{media_id}",
    response_model=MediaResponse,
)
async def get_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_media_or_404(media_id, db, user_id=current_user.id)


# ---------------------------------------------------------
# PROCESSING STATUS / PROGRESS & JOB MONITORING
# ---------------------------------------------------------

@router.get(
    "/{media_id}/status",
    response_model=MediaProcessingStatusResponse,
    summary="Get media processing status and progress",
)
async def get_media_status_endpoint(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    return await get_media_progress(media_id, db_media=media)


@router.get(
    "/{media_id}/progress",
    response_model=MediaProcessingStatusResponse,
    summary="Get media processing progress",
)
async def get_media_progress_endpoint(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    return await get_media_progress(media_id, db_media=media)


@router.get(
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get background job status and progress by job ID",
)
async def get_media_job_endpoint(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    job_data = await get_job_status(job_id)
    if not job_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    media_id = job_data.get("media_id")
    if media_id:
        try:
            m_uuid = UUID(media_id)
            res = await db.execute(select(Media).where(Media.id == m_uuid))
            media = res.scalar_one_or_none()
            if media and media.user_id is not None and media.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job '{job_id}' not found",
                )
        except (ValueError, TypeError):
            pass
    return job_data


# ---------------------------------------------------------
# PROCESS MEDIA
# ---------------------------------------------------------

@router.post("/{media_id}/process")
async def process_media_endpoint(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    if media.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Media is already processing",
        )

    if media.processing_status == "completed":
        raise HTTPException(
            status_code=409,
            detail="Media is already processed",
        )

    await mark_processing_pending(media, db)

    job = await enqueue_media_job(
        "process_media_task",
        str(media.id),
        media.stored_filename,
    )

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
    }


# ---------------------------------------------------------
# CONVERT
# ---------------------------------------------------------

@router.post("/{media_id}/convert")
async def convert_media_endpoint(
    media_id: UUID,
    data: MediaConvertRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    # Determine output format from request and prepare filename
    extension = data.format.lower().lstrip(".")
    output_filename = f"{media_id}_converted_{uuid4().hex[:8]}.{extension}"

    # Build options dict, excluding None values
    options = data.model_dump(exclude_none=True)
    # Remove the original 'format' key to avoid unexpected argument
    options.pop("format", None)
    # Map schema fields to conversion function parameter names
    if "width" in options:
        options["custom_width"] = options.pop("width")
    if "height" in options:
        options["custom_height"] = options.pop("height")
    if "video_bitrate" in options:
        options["bitrate"] = options.pop("video_bitrate")
    # Set the required output_format parameter
    options["output_format"] = extension

    job = await enqueue_media_job(
        "convert_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        options,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# EDIT
# ---------------------------------------------------------

@router.post("/{media_id}/edit")
async def edit_media_endpoint(
    media_id: UUID,
    data: MediaEditRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_operations = {
        "trim",
        "cut",
        "extract",
    }

    if data.operation not in allowed_operations:
        raise HTTPException(
            status_code=400,
            detail="Operation must be trim, cut, or extract",
        )

    if data.end <= data.start:
        raise HTTPException(
            status_code=400,
            detail="End time must be greater than start time",
        )

    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    output_filename = (
        f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
    )

    job = await enqueue_media_job(
        "edit_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        data.operation,
        data.start,
        data.end,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media.id),
        "status": "queued",
        "operation": data.operation,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# ATTACH TO PROJECT
# ---------------------------------------------------------

@router.patch("/{media_id}/project/{project_id}")
async def attach_media_to_project(
    media_id: UUID,
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    media.project_id = project_id

    await db.commit()
    await db.refresh(media)

    return media


# ---------------------------------------------------------
# GET ORIGINAL FILE
# ---------------------------------------------------------

@router.get("/{media_id}/file")
async def get_media_file(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    file_path = get_uploaded_file(
        media.stored_filename
    )
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))

    return FileResponse(
        path=safe_path,
        media_type=media.mime_type,
        filename=media.original_filename,
    )


# ---------------------------------------------------------
# GET PROCESSED FILE
# ---------------------------------------------------------

@router.get("/{media_id}/processed")
async def get_processed_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    if not media.processed_filename:
        raise HTTPException(
            status_code=404,
            detail="Processed media not available",
        )

    file_path = get_uploaded_file(
        media.processed_filename
    )
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))

    return FileResponse(
        path=safe_path,
        media_type=media.mime_type,
        filename=media.processed_filename,
    )


# ---------------------------------------------------------
# DELETE
# ---------------------------------------------------------

@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    await delete_media_file(
        media.stored_filename
    )

    if media.processed_filename:
        await delete_media_file(
            media.processed_filename
        )

    await db.delete(media)
    await db.commit()


# ---------------------------------------------------------
# MERGE
# ---------------------------------------------------------

@router.post("/{media_id}/merge")
async def merge_media_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    await verify_media_references_ownership(data.media_ids, current_user.id, db)

    input_filenames = data.media_ids

    output_filename = (
        f"{media_id}_merge_{uuid4().hex[:8]}.mp4"
    )

    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        input_filenames,
        output_filename,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "merge",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# TRANSFORM
# ---------------------------------------------------------

@router.post("/{media_id}/transform")
async def transform_media_endpoint(
    media_id: UUID,
    data: MediaTransformRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    output_filename = (
        f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
    )

    options = data.model_dump(exclude_none=True)

    job = await enqueue_media_job(
        "transform_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        options,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": data.operation,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# FREEZE FRAME
# ---------------------------------------------------------

@router.post("/{media_id}/freeze")
async def freeze_frame_endpoint(
    media_id: UUID,
    data: MediaFreezeFrameRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)

    output_filename = (
        f"{media_id}_freeze_{uuid4().hex[:8]}.mp4"
    )

    job = await enqueue_media_job(
        "freeze_frame_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        data.timestamp,
        data.duration,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "freeze",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# OVERLAY
# ---------------------------------------------------------

@router.post("/{media_id}/overlay")
async def overlay_media_endpoint(
    media_id: UUID,
    data: MediaOverlayRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    if data.image_filename:
        await verify_media_references_ownership([data.image_filename], current_user.id, db)
    if data.overlays:
        for ov in data.overlays:
            if ov.image_filename:
                await verify_media_references_ownership([ov.image_filename], current_user.id, db)

    operation_name = data.operation or ("multi_overlay" if data.overlays else "overlay")
    output_filename = (
        f"{media_id}_{operation_name}_{uuid4().hex[:8]}.mp4"
    )

    options = data.model_dump(exclude_none=True)

    job = await enqueue_media_job(
        "overlay_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        options,
    )

    await mark_processing_pending(media, db)

    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": operation_name,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# SPLIT
# ---------------------------------------------------------
@router.post("/{media_id}/split")
async def split_media_endpoint(
    media_id: UUID,
    data: MediaSplitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    output_prefix = f"{media_id}_split_{uuid4().hex[:8]}"
    job = await enqueue_media_job(
        "split_media_task",
        str(media_id),
        media.stored_filename,
        output_prefix,
        data.split_points,
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "split",
        "job_id": job.job_id,
        "output_prefix": output_prefix,
    }


# ---------------------------------------------------------
# KEEP SELECTED CLIPS
# ---------------------------------------------------------
@router.post("/{media_id}/clips/keep")
async def keep_clips_endpoint(
    media_id: UUID,
    data: MediaClipsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    output_filename = f"{media_id}_keep_{uuid4().hex[:8]}.mp4"
    clip_tuples = [[c.start, c.end] for c in data.clips]
    job = await enqueue_media_job(
        "clips_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        "keep",
        clip_tuples,
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "keep_clips",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# DELETE SELECTED CLIPS
# ---------------------------------------------------------
@router.post("/{media_id}/clips/delete")
async def delete_clips_endpoint(
    media_id: UUID,
    data: MediaClipsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    output_filename = f"{media_id}_delete_{uuid4().hex[:8]}.mp4"
    clip_tuples = [[c.start, c.end] for c in data.clips]
    job = await enqueue_media_job(
        "clips_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        "delete",
        clip_tuples,
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "delete_clips",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# REORDER CLIPS
# ---------------------------------------------------------
@router.post("/{media_id}/clips/reorder")
async def reorder_clips_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    await verify_media_references_ownership(data.media_ids, current_user.id, db)
    output_filename = f"{media_id}_reorder_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        data.media_ids,
        output_filename,
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "reorder",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


# ---------------------------------------------------------
# APPEND CLIPS
# ---------------------------------------------------------
@router.post("/{media_id}/clips/append")
async def append_clips_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    await verify_media_references_ownership(data.media_ids, current_user.id, db)
    ordered_ids = [media.stored_filename]
    for m_id in data.media_ids:
        if m_id != media.stored_filename:
            ordered_ids.append(m_id)
    output_filename = f"{media_id}_append_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        ordered_ids,
        output_filename,
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "append",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }
