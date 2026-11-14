from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.demo.service import enforce_demo_upload_quota, enforce_demo_job_quota
from app.features.media.models import Media, MediaVersion
from app.features.media.schemas import (
    BatchDownloadRequest,
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
    ProcessingRequest,
    UploadProgressResponse,
)
from app.features.jobs.schemas import JobStatusResponse
from app.features.jobs.service import (
    get_job_status,
    get_media_progress,
    set_processing_progress,
)
from app.features.media.service import delete_media_file, save_multiple_uploads, save_upload
from app.features.media.upload_progress import delete_upload_progress, get_upload_progress, set_upload_progress
from app.features.media.conversion import ASPECT_RATIO_PRESETS, FPS_PRESETS
from app.features.projects.service import get_project
from app.infrastructure.database import AsyncSessionLocal, get_db
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


async def get_media_or_404(
    media_id: UUID,
    db: AsyncSession,
    user_id: UUID | None = None,
    is_demo_user: bool = False,
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
    if user_id is not None:
        if (
            (is_demo_user and media_user_id != user_id)
            or (not is_demo_user and media_user_id is not None and media_user_id != user_id)
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media not found",
            )

    return media


async def verify_media_references_ownership(
    media_refs: list[str],
    user_id: UUID,
    db: AsyncSession,
    is_demo_user: bool = False,
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
            if (
                (is_demo_user and matched_media.user_id != user_id)
                or (not is_demo_user and matched_media.user_id is not None and matched_media.user_id != user_id)
            ):
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
    demo_user_id: UUID | None = None,
):
    media_id = None
    if args:
        try:
            media_id = UUID(str(args[0]))
        except (ValueError, TypeError):
            media_id = None

    # Persist the queued state before publishing the job. Expiry cleanup must
    # never remove an input file while its job is waiting in the shared queue.
    if media_id is not None and demo_user_id is not None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Media).where(Media.id == media_id))
            media = result.scalar_one_or_none()
            if media is None or media.user_id != demo_user_id:
                raise HTTPException(status_code=404, detail="Media not found")
            await enforce_demo_job_quota(
                db,
                demo_user_id,
                exclude_media_id=media.id,
            )
            media.processing_status = "queued"
            media.processing_error = None
            await db.commit()

    pool = await create_worker_pool()
    try:
        try:
            job = await pool.enqueue_job(task_name, *args)
        except Exception:
            if demo_user_id is not None and media_id is not None:
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Media).where(Media.id == media_id))
                    media = result.scalar_one_or_none()
                    if media is not None and media.user_id == demo_user_id:
                        media.processing_status = "failed"
                        media.processing_error = "The background queue did not accept this job."
                        await db.commit()
            raise

        if job and args:
            await set_processing_progress(
                media_id=str(args[0]),
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
    # "queued" is persisted before the worker starts; "pending" means not yet submitted.
    media.processing_status = "queued"
    media.processing_error = None
    await db.commit()


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
    upload_id = str(uuid4())
    media = None
    try:
        if file.size is not None:
            await enforce_demo_upload_quota(db, current_user.id, file.size, is_demo_user=getattr(current_user, "is_demo_session", False))
        await set_upload_progress(
            upload_id=upload_id,
            user_id=current_user.id,
            filename=file.filename or "unknown",
            status="uploading",
            progress=0,
            total_size=file.size,
            uploaded_size=0,
        )
        media = await save_upload(file)
        await enforce_demo_upload_quota(db, current_user.id, media.file_size, is_demo_user=getattr(current_user, "is_demo_session", False))
        media.user_id = current_user.id

        db.add(media)
        await db.commit()
        await db.refresh(media)

        await set_upload_progress(
            upload_id=upload_id,
            user_id=current_user.id,
            filename=file.filename or "unknown",
            status="completed",
            progress=100,
            total_size=file.size,
            uploaded_size=media.file_size,
        )
        return media

    except HTTPException:
        if media is not None:
            await delete_media_file(media.stored_filename)
        await delete_upload_progress(upload_id)
        raise
    except ValueError as exc:
        await set_upload_progress(
            upload_id=upload_id,
            user_id=current_user.id,
            filename=file.filename or "unknown",
            status="failed",
            progress=0,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post(
    "/upload-multiple",
    response_model=list[MediaResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple media files in a single request",
)
async def upload_multiple_media(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided",
        )

    try:
        known_sizes = [item.size for item in files]
        if all(size is not None for size in known_sizes):
            await enforce_demo_upload_quota(
                db,
                current_user.id,
                max(int(size or 0) for size in known_sizes),
                incoming_files=len(files),
                is_demo_user=getattr(current_user, "is_demo_session", False),
                total_incoming_bytes=sum(int(size or 0) for size in known_sizes),
            )
        media_list = await save_multiple_uploads(files)
        await enforce_demo_upload_quota(
            db,
            current_user.id,
            max(item.file_size for item in media_list),
            incoming_files=len(media_list),
            is_demo_user=getattr(current_user, "is_demo_session", False),
            total_incoming_bytes=sum(item.file_size for item in media_list),
        )
        for media in media_list:
            media.user_id = current_user.id
            db.add(media)
        await db.commit()
        for media in media_list:
            await db.refresh(media)
        return media_list
    except HTTPException:
        if "media_list" in locals():
            for uploaded_media in media_list:
                await delete_media_file(uploaded_media.stored_filename)
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get(
    "/uploads/{upload_id}/progress",
    response_model=UploadProgressResponse,
    summary="Get upload progress for a specific upload ID",
)
async def get_upload_progress_endpoint(
    upload_id: str,
    current_user: User = Depends(get_current_active_user),
):
    progress = await get_upload_progress(upload_id, current_user.id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Upload progress not found")
    return UploadProgressResponse(
        upload_id=progress.get("upload_id", upload_id),
        user_id=progress.get("user_id", str(current_user.id)),
        filename=progress.get("filename", ""),
        status=progress.get("status", "unknown"),
        progress=int(progress.get("progress", 0)),
        total_size=progress.get("total_size"),
        uploaded_size=progress.get("uploaded_size"),
        error=progress.get("error"),
    )


@router.post("/resumable/init", response_model=ResumableInitResponse)
async def resumable_init(
    data: ResumableInitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        is_demo_user = getattr(current_user, "is_demo_session", False)
        await enforce_demo_upload_quota(
            db,
            current_user.id,
            data.total_size,
            is_demo_user=is_demo_user,
        )
        if is_demo_user and data.chunk_size is not None and data.chunk_size > get_settings().demo_max_chunk_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Demo upload chunks are limited to 2 MB.",
            )
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
    db: AsyncSession = Depends(get_db),
):
    if index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk index must be non-negative")
    is_demo_user = getattr(current_user, "is_demo_session", False)
    if is_demo_user and file.size is not None and file.size > get_settings().demo_max_chunk_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Demo upload chunks are limited to 2 MB.",
        )
    content = await file.read()
    if is_demo_user and len(content) > get_settings().demo_max_chunk_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Demo upload chunks are limited to 2 MB.",
        )
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
    db: AsyncSession = Depends(get_db),
) -> ChunkUploadResponse:
    if index < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chunk index must be non-negative")
    is_demo_user = getattr(current_user, "is_demo_session", False)
    if is_demo_user and file.size is not None and file.size > get_settings().demo_max_chunk_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Demo upload chunks are limited to 2 MB.",
        )
    content = await file.read()
    if is_demo_user and len(content) > get_settings().demo_max_chunk_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Demo upload chunks are limited to 2 MB.",
        )
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
    try:
        media = await ResumableUploadService.finalize(upload_id, db, user_id=current_user.id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return media


@router.get(
    "",
    response_model=list[MediaResponse],
)
async def list_media(
    search: str | None = None,
    media_type: str | None = None,
    folder: str | None = None,
    tag: str | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if getattr(current_user, "is_demo_session", False):
        query = select(Media).where(Media.user_id == current_user.id)
    else:
        query = select(Media).where((Media.user_id == current_user.id) | (Media.user_id.is_(None)))
    if search:
        query = query.where(Media.original_filename.ilike(f"%{search}%"))
    if media_type:
        query = query.where(Media.media_type == media_type)
    if folder:
        query = query.where(Media.folder == folder)
    if tag:
        query = query.where(Media.tags.ilike(f"%{tag}%"))
    query = query.order_by(Media.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/{media_id}",
    response_model=MediaResponse,
)
async def get_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))


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
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
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
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
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
    is_demo_user = getattr(current_user, "is_demo_session", False)
    if is_demo_user and not media_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found",
        )
    if media_id:
        try:
            m_uuid = UUID(media_id)
            res = await db.execute(select(Media).where(Media.id == m_uuid))
            media = res.scalar_one_or_none()
            if media and (
                (is_demo_user and media.user_id != current_user.id)
                or (not is_demo_user and media.user_id is not None and media.user_id != current_user.id)
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Job '{job_id}' not found",
                )
        except (ValueError, TypeError):
            pass
    return job_data


@router.post("/{media_id}/process")
async def process_media_endpoint(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))

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
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
    }


@router.post("/{media_id}/convert")
async def convert_media_endpoint(
    media_id: UUID,
    data: MediaConvertRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    extension = data.format.lower().lstrip(".")
    output_filename = f"{media_id}_converted_{uuid4().hex[:8]}.{extension}"
    options = data.model_dump(exclude_none=True)
    options.pop("format", None)
    if "width" in options:
        options["custom_width"] = options.pop("width")
    if "height" in options:
        options["custom_height"] = options.pop("height")
    if "video_bitrate" in options:
        options["bitrate"] = options.pop("video_bitrate")
    if "fps_preset" in options:
        preset = options.pop("fps_preset")
        if "fps" not in options:
            options["fps"] = FPS_PRESETS.get(preset)
    if "aspect_ratio_preset" in options:
        preset = options.pop("aspect_ratio_preset")
        if "aspect_ratio" not in options:
            options["aspect_ratio"] = ASPECT_RATIO_PRESETS.get(preset)
    options["output_format"] = extension

    job = await enqueue_media_job(
        "convert_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        options,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/compress")
async def compress_media_endpoint(
    media_id: UUID,
    data: MediaConvertRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    extension = data.format.lower().lstrip(".") if data.format else "mp4"
    output_filename = f"{media_id}_compressed_{uuid4().hex[:8]}.{extension}"
    options = data.model_dump(exclude_none=True)
    options.pop("format", None)
    options["output_format"] = extension
    options["compression_preset"] = options.pop("compression_preset", "balanced")
    target_size_mb = options.pop("target_size_mb", None)

    job = await enqueue_media_job(
        "compress_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        options,
        target_size_mb,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
        "output_filename": output_filename,
        "target_size_mb": target_size_mb,
    }


@router.post("/{media_id}/edit")
async def edit_media_endpoint(
    media_id: UUID,
    data: MediaEditRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    allowed_operations = {"trim", "cut", "extract"}

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

    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_filename = f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "edit_media_task",
        str(media.id),
        media.stored_filename,
        output_filename,
        data.operation,
        data.start,
        data.end,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media.id),
        "status": "queued",
        "operation": data.operation,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.patch("/{media_id}/project/{project_id}")
async def attach_media_to_project(
    media_id: UUID,
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    media.project_id = project_id
    await db.commit()
    await db.refresh(media)
    return media


@router.get("/{media_id}/file")
async def get_media_file(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    file_path = get_uploaded_file(media.stored_filename)
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))
    return FileResponse(path=safe_path, media_type=media.mime_type, filename=media.original_filename)


@router.get("/{media_id}/processed")
async def get_processed_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    if not media.processed_filename:
        raise HTTPException(status_code=404, detail="Processed media not available")
    file_path = get_uploaded_file(media.processed_filename)
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))
    return FileResponse(path=safe_path, media_type=media.mime_type, filename=media.processed_filename)


@router.get("/{media_id}/download")
async def download_processed_media(
    media_id: UUID,
    version_id: UUID | None = None,
    download_type: str = "processed",
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    if version_id:
        result = await db.execute(select(MediaVersion).where(MediaVersion.id == version_id, MediaVersion.media_id == media_id))
        version = result.scalar_one_or_none()
        if version is None:
            raise HTTPException(status_code=404, detail="Version not found")
        file_path = get_uploaded_file(version.stored_filename)
        filename = version.original_filename
    elif download_type == "original":
        file_path = get_uploaded_file(media.stored_filename)
        filename = media.original_filename
    else:
        if not media.processed_filename:
            raise HTTPException(status_code=404, detail="Processed media not available")
        file_path = get_uploaded_file(media.processed_filename)
        filename = media.original_filename
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))
    return FileResponse(path=safe_path, media_type=media.mime_type, filename=filename)


@router.post("/batch-download")
async def batch_download_media(
    data: BatchDownloadRequest,
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
            "original_filename": media.original_filename,
            "file_size": media.file_size,
        })
    return {"jobs": jobs, "total": len(jobs)}


@router.delete(
    "/{media_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))

    await delete_media_file(media.stored_filename)

    if media.processed_filename:
        await delete_media_file(media.processed_filename)

    await db.delete(media)
    await db.commit()


@router.post("/{media_id}/merge")
async def merge_media_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    await verify_media_references_ownership(data.media_ids, current_user.id, db, is_demo_user=getattr(current_user, "is_demo_session", False))

    input_filenames: list[str] = []
    for ref in data.media_ids:
        try:
            ref_uuid = UUID(ref)
            query = select(Media).where((Media.id == ref_uuid) | (Media.stored_filename == ref))
        except (ValueError, TypeError):
            query = select(Media).where(Media.stored_filename == ref)
        result = await db.execute(query)
        referenced_media = result.scalar_one_or_none()
        if referenced_media is None:
            raise HTTPException(status_code=404, detail=f"Media reference not found: {ref}")
        input_filenames.append(referenced_media.stored_filename)

    output_filename = f"{media_id}_merge_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        input_filenames,
        output_filename,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "merge",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/transform")
async def transform_media_endpoint(
    media_id: UUID,
    data: MediaTransformRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_filename = f"{media_id}_{data.operation}_{uuid4().hex[:8]}.mp4"
    options = data.model_dump(exclude_none=True)
    job = await enqueue_media_job(
        "transform_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        options,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": data.operation,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/freeze")
async def freeze_frame_endpoint(
    media_id: UUID,
    data: MediaFreezeFrameRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_filename = f"{media_id}_freeze_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "freeze_frame_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        data.timestamp,
        data.duration,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "freeze",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/overlay")
async def overlay_media_endpoint(
    media_id: UUID,
    data: MediaOverlayRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    if data.image_filename:
        await verify_media_references_ownership([data.image_filename], current_user.id, db, is_demo_user=getattr(current_user, "is_demo_session", False))
    if data.overlays:
        for ov in data.overlays:
            if ov.image_filename:
                await verify_media_references_ownership([ov.image_filename], current_user.id, db, is_demo_user=getattr(current_user, "is_demo_session", False))

    operation_name = data.operation or ("multi_overlay" if data.overlays else "overlay")
    output_filename = f"{media_id}_{operation_name}_{uuid4().hex[:8]}.mp4"
    options = data.model_dump(exclude_none=True)
    job = await enqueue_media_job(
        "overlay_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        options,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": operation_name,
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/split")
async def split_media_endpoint(
    media_id: UUID,
    data: MediaSplitRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_prefix = f"{media_id}_split_{uuid4().hex[:8]}"
    job = await enqueue_media_job(
        "split_media_task",
        str(media_id),
        media.stored_filename,
        output_prefix,
        data.split_points,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "split",
        "job_id": job.job_id,
        "output_prefix": output_prefix,
    }


@router.post("/{media_id}/clips/keep")
async def keep_clips_endpoint(
    media_id: UUID,
    data: MediaClipsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_filename = f"{media_id}_keep_{uuid4().hex[:8]}.mp4"
    clip_tuples = [[c.start, c.end] for c in data.clips]
    job = await enqueue_media_job(
        "clips_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        "keep",
        clip_tuples,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "keep_clips",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/clips/delete")
async def delete_clips_endpoint(
    media_id: UUID,
    data: MediaClipsRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    output_filename = f"{media_id}_delete_{uuid4().hex[:8]}.mp4"
    clip_tuples = [[c.start, c.end] for c in data.clips]
    job = await enqueue_media_job(
        "clips_media_task",
        str(media_id),
        media.stored_filename,
        output_filename,
        "delete",
        clip_tuples,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "delete_clips",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/clips/reorder")
async def reorder_clips_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))

    resolved_filenames: list[str] = []
    for ref in data.media_ids:
        query = select(Media)
        try:
            ref_uuid = UUID(ref)
            query = query.where((Media.id == ref_uuid) | (Media.stored_filename == ref))
        except (ValueError, TypeError):
            query = query.where(Media.stored_filename == ref)

        result = await db.execute(query)
        referenced_media = result.scalar_one_or_none()

        if referenced_media is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Media reference not found: {ref}",
            )
        if referenced_media.user_id is not None and referenced_media.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot reference media belonging to another user",
            )

        resolved_filenames.append(referenced_media.stored_filename)

    if len(resolved_filenames) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 clips are required for reorder",
        )

    output_filename = f"{media_id}_reorder_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        resolved_filenames,
        output_filename,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "reorder",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/clips/append")
async def append_clips_endpoint(
    media_id: UUID,
    data: MediaMergeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    await verify_media_references_ownership(data.media_ids, current_user.id, db, is_demo_user=getattr(current_user, "is_demo_session", False))
    ordered_ids = [media.stored_filename]
    for ref in data.media_ids:
        try:
            ref_uuid = UUID(ref)
            query = select(Media).where((Media.id == ref_uuid) | (Media.stored_filename == ref))
        except (ValueError, TypeError):
            query = select(Media).where(Media.stored_filename == ref)
        result = await db.execute(query)
        referenced_media = result.scalars().first()
        if referenced_media is None:
            raise HTTPException(status_code=404, detail=f"Media reference not found: {ref}")
        if referenced_media.stored_filename not in ordered_ids:
            ordered_ids.append(referenced_media.stored_filename)
    output_filename = f"{media_id}_append_{uuid4().hex[:8]}.mp4"
    job = await enqueue_media_job(
        "merge_media_task",
        str(media_id),
        ordered_ids,
        output_filename,
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )
    await mark_processing_pending(media, db)
    return {
        "media_id": str(media_id),
        "status": "queued",
        "operation": "append",
        "job_id": job.job_id,
        "output_filename": output_filename,
    }


@router.post("/{media_id}/process-unified")
async def process_media_unified_endpoint(
    media_id: UUID,
    data: ProcessingRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))

    if media.processing_status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Media is already processing",
        )

    await mark_processing_pending(media, db)

    job = await enqueue_media_job(
        "process_media_unified_task",
        str(media.id),
        [op.model_dump() for op in data.operations],
        str(uuid4()),
        str(current_user.id),
        demo_user_id=(current_user.id if getattr(current_user, "is_demo_session", False) else None),
    )

    return {
        "media_id": str(media.id),
        "status": "queued",
        "job_id": job.job_id,
        "operations_count": len(data.operations),
    }


@router.get("/{media_id}/versions")
async def list_media_versions(
    media_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    result = await db.execute(
        select(MediaVersion).where(MediaVersion.media_id == media_id).order_by(MediaVersion.created_at.desc())
    )
    versions = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "version_number": v.version_number,
            "label": v.label,
            "stored_filename": v.stored_filename,
            "processing_status": v.processing_status,
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


@router.get("/{media_id}/versions/{version_id}")
async def get_media_version(
    media_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    result = await db.execute(select(MediaVersion).where(MediaVersion.id == version_id, MediaVersion.media_id == media_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "label": version.label,
        "stored_filename": version.stored_filename,
        "processing_status": version.processing_status,
        "created_at": version.created_at.isoformat(),
    }


@router.delete("/{media_id}/versions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_version(
    media_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    result = await db.execute(select(MediaVersion).where(MediaVersion.id == version_id, MediaVersion.media_id == media_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    await delete_media_file(version.stored_filename)
    await db.delete(version)
    await db.commit()


@router.post("/{media_id}/versions/{version_id}/restore")
async def restore_media_version(
    media_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    result = await db.execute(select(MediaVersion).where(MediaVersion.id == version_id, MediaVersion.media_id == media_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    media.stored_filename = version.stored_filename
    media.original_filename = version.original_filename
    media.file_size = version.file_size
    media.mime_type = version.mime_type
    media.duration = version.duration
    media.width = version.width
    media.height = version.height
    media.video_codec = version.video_codec
    media.audio_codec = version.audio_codec
    media.fps = version.fps
    await db.commit()
    await db.refresh(media)
    return media


@router.get("/{media_id}/versions/{version_id}/download")
async def download_media_version(
    media_id: UUID,
    version_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    result = await db.execute(select(MediaVersion).where(MediaVersion.id == version_id, MediaVersion.media_id == media_id))
    version = result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    file_path = get_uploaded_file(version.stored_filename)
    settings = get_settings()
    safe_path = verify_file_path_safety(file_path, Path(settings.upload_dir))
    return FileResponse(path=safe_path, media_type=version.mime_type, filename=version.original_filename)


@router.post("/{media_id}/versions")
async def create_media_version(
    media_id: UUID,
    data: dict,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new version for a media file."""
    media = await get_media_or_404(media_id, db, user_id=current_user.id, is_demo_user=getattr(current_user, "is_demo_session", False))
    
    stored_filename = data.get("stored_filename")
    label = data.get("label", "Processed")
    file_size = data.get("file_size")
    mime_type = data.get("mime_type", media.mime_type)
    duration = data.get("duration")
    width = data.get("width")
    height = data.get("height")
    video_codec = data.get("video_codec")
    audio_codec = data.get("audio_codec")
    fps = data.get("fps")
    
    if not stored_filename or file_size is None:
        raise HTTPException(status_code=400, detail="stored_filename and file_size are required")
    
    result = await db.execute(
        select(MediaVersion).where(MediaVersion.media_id == media_id).order_by(MediaVersion.version_number.desc())
    )
    last_version = result.scalars().first()
    version_number = (last_version.version_number + 1) if last_version else 1
    
    file_path = Path(settings.processed_dir) / stored_filename
    if not file_path.exists():
        file_path = Path(settings.upload_dir) / stored_filename
    
    if file_path.exists():
        actual_size = file_path.stat().st_size
    else:
        actual_size = file_size
    
    version = MediaVersion(
        media_id=media_id,
        version_number=version_number,
        label=label,
        stored_filename=stored_filename,
        original_filename=media.original_filename,
        file_size=actual_size,
        mime_type=mime_type,
        duration=duration,
        width=width,
        height=height,
        video_codec=video_codec,
        audio_codec=audio_codec,
        fps=fps,
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