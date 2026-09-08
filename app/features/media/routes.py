from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
)
from app.features.media.service import delete_media_file, save_upload
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

    return media


async def enqueue_media_job(
    task_name: str,
    *args,
):
    pool = await create_worker_pool()

    try:
        return await pool.enqueue_job(
            task_name,
            *args,
        )
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
    db: AsyncSession = Depends(get_db),
):
    try:
        media = await save_upload(file)

        db.add(media)
        await db.commit()
        await db.refresh(media)

        return media

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
async def resumable_init(data: ResumableInitRequest):
    """Initialize a resumable upload and return an upload_id."""
    upload_id = await ResumableUploadService.init_upload(
        original_filename=data.original_filename,
        total_size=data.total_size,
        chunk_size=data.chunk_size,
    )
    return ResumableInitResponse(upload_id=str(upload_id))

@router.post("/resumable/{upload_id}/chunk/{index}", response_model=ChunkUploadResponse)
async def resumable_chunk(
    upload_id: UUID,
    index: int,
    file: UploadFile = File(...),
):
    """Upload a single chunk for the given upload_id."""
    content = await file.read()
    try:
        await ResumableUploadService.store_chunk(upload_id, index, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ChunkUploadResponse()

@router.post("/resumable/{upload_id}/pause", response_model=ActionResponse)
async def resumable_pause(upload_id: UUID):
    try:
        await ResumableUploadService.pause(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="paused")

@router.post("/resumable/{upload_id}/resume", response_model=ActionResponse)
async def resumable_resume(upload_id: UUID):
    try:
        await ResumableUploadService.resume(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="resumed")

@router.post("/resumable/{upload_id}/retry", response_model=ChunkUploadResponse)
async def resumable_retry(
    upload_id: UUID,
    index: int,
    file: UploadFile = File(...),
) -> ChunkUploadResponse:
    """Retry uploading a single chunk for the given upload_id."""
    content = await file.read()
    try:
        await ResumableUploadService.store_chunk(upload_id, index, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ChunkUploadResponse()

@router.delete("/resumable/{upload_id}", response_model=ActionResponse)
async def resumable_cancel(upload_id: UUID):
    try:
        await ResumableUploadService.cancel(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ActionResponse(detail="canceled")

@router.post("/resumable/{upload_id}/finalize", response_model=MediaResponse)
async def resumable_finalize(upload_id: UUID, db: AsyncSession = Depends(get_db)):
    """Assemble chunks and create a Media record."""
    try:
        media = await ResumableUploadService.finalize(upload_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return media

# ---------------------------------------------------------
# LIST MEDIA
# ---------------------------------------------------------

@router.get(
    "",
    response_model=list[MediaResponse],
)
async def list_media(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).order_by(Media.created_at.desc())
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
    db: AsyncSession = Depends(get_db),
):
    return await get_media_or_404(media_id, db)


# ---------------------------------------------------------
# PROCESS MEDIA
# ---------------------------------------------------------

@router.post("/{media_id}/process")
async def process_media_endpoint(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    # audio_bitrate and audio_codec are not used by convert_media; remove them if present
    options.pop("audio_bitrate", None)
    options.pop("audio_codec", None)
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

    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

    file_path = get_uploaded_file(
        media.stored_filename
    )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Media file not found",
        )

    return FileResponse(
        path=file_path,
        media_type=media.mime_type,
        filename=media.original_filename,
    )


# ---------------------------------------------------------
# GET PROCESSED FILE
# ---------------------------------------------------------

@router.get("/{media_id}/processed")
async def get_processed_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

    if not media.processed_filename:
        raise HTTPException(
            status_code=404,
            detail="Processed media not available",
        )

    file_path = get_uploaded_file(
        media.processed_filename
    )

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Processed media file not found",
        )

    return FileResponse(
        path=file_path,
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)

    output_filename = (
        f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
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
        "operation": data.operation,
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db)
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
