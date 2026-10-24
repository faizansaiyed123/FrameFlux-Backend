import json
import os
import shutil
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.features.media.upload_progress import set_upload_progress, delete_upload_progress
from app.features.media.models import Media
from app.features.media.service import get_media_type
from app.infrastructure.worker import WorkerSettings
from app.shared.validators import (
    validate_file_content,
    validate_file_size,
    validate_filename_and_extension,
    validate_mime_type,
)

settings = get_settings()

UPLOAD_KEY_PREFIX = "resumable_upload:"  


def _redis_key(upload_id: UUID) -> str:
    return f"{UPLOAD_KEY_PREFIX}{upload_id}" 


def _temp_dir(upload_id: UUID) -> Path:
    """Directory that holds chunk files for a given upload."""
    return Path(settings.upload_dir) / "resumable" / str(upload_id)


def _chunk_path(upload_id: UUID, index: int) -> Path:
    return _temp_dir(upload_id) / f"{index}.part"


class ResumableUploadService:
    """Utility class that orchestrates resumable uploads using Redis for state
    and the local filesystem for temporary chunk storage.
    """

    @staticmethod
    async def init_upload(
        original_filename: str,
        total_size: int,
        chunk_size: Optional[int] = None,
        user_id: Optional[UUID] = None,
    ) -> UUID:
        """Create a new resumable upload entry.

        Returns the generated ``upload_id`` which the client must include in
        subsequent chunk, pause/resume, cancel, and finalize calls.
        """
        ext = validate_filename_and_extension(original_filename)

        validate_file_size(total_size, settings.max_upload_size_bytes)

        if chunk_size is not None:
            if chunk_size <= 0:
                raise ValueError("chunk_size must be greater than 0")
            if chunk_size > settings.max_chunk_size_bytes:
                from fastapi import HTTPException, status
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"chunk_size {chunk_size} exceeds maximum chunk limit of {settings.max_chunk_size_bytes} bytes",
                )

        upload_id = uuid4()
        stored_filename = f"{uuid4()}{ext}"
        chunk_size = chunk_size or (1024 * 1024)  

        _temp_dir(upload_id).mkdir(parents=True, exist_ok=True)

        redis = await create_pool(WorkerSettings.redis_settings)
        await redis.hset(
            _redis_key(upload_id),
            mapping={
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "total_size": str(total_size),
                "chunk_size": str(chunk_size),
                "uploaded_chunks": "",
                "status": "in_progress",
                "user_id": str(user_id) if user_id else "",
            },
        )
        await redis.close()
        if user_id is not None:
            await set_upload_progress(
                str(upload_id),
                user_id,
                original_filename,
                status="uploading",
                progress=0,
                total_size=total_size,
                uploaded_size=0,
            )
        return upload_id

    @staticmethod
    async def _load_meta(upload_id: UUID, user_id: Optional[UUID] = None) -> dict:
        redis = await create_pool(WorkerSettings.redis_settings)
        meta = await redis.hgetall(_redis_key(upload_id))
        await redis.close()
        if not meta:
            raise ValueError("Upload ID not found")
        meta = {k.decode() if isinstance(k, (bytes, bytearray)) else k: v.decode() if isinstance(v, (bytes, bytearray)) else v for k, v in meta.items()}
        if user_id is not None and meta.get("user_id") and meta["user_id"] != str(user_id):
            raise ValueError("Upload ID not found")
        return meta

    @staticmethod
    async def store_chunk(
        upload_id: UUID,
        index: int,
        data: bytes,
        user_id: Optional[UUID] = None,
    ) -> None:
        """Persist a single chunk to the temporary directory and update state.
        The ``index`` is zero‑based.
        """
        meta = await ResumableUploadService._load_meta(upload_id, user_id=user_id)
        if meta.get("status") not in ("in_progress", "paused"):
            raise ValueError(f"Cannot store chunk when status is {meta.get('status')}")

        chunk_path = _chunk_path(upload_id, index)
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        with open(chunk_path, "wb") as f:
            f.write(data)

        existing = meta.get("uploaded_chunks", "")
        indices = set(int(i) for i in existing.split(",") if i)  
        indices.add(index)
        new_value = ",".join(str(i) for i in sorted(indices))
        redis = await create_pool(WorkerSettings.redis_settings)
        await redis.hset(_redis_key(upload_id), mapping={"uploaded_chunks": new_value})
        await redis.close()
        if user_id is not None:
            total_size = int(meta["total_size"])
            chunk_size = int(meta["chunk_size"])
            total_chunks = max((total_size + chunk_size - 1) // chunk_size, 1)
            uploaded_size = min(total_size, len(data) + sum(
                _chunk_path(upload_id, i).stat().st_size
                for i in indices
                if i != index and _chunk_path(upload_id, i).exists()
            ))
            await set_upload_progress(
                str(upload_id),
                user_id,
                meta["original_filename"],
                status="uploading",
                progress=int(len(indices) / total_chunks * 100),
                total_size=total_size,
                uploaded_size=uploaded_size,
            )

    @staticmethod
    async def pause(upload_id: UUID, user_id: Optional[UUID] = None) -> None:
        meta = await ResumableUploadService._load_meta(upload_id, user_id=user_id)
        redis = await create_pool(WorkerSettings.redis_settings)
        await redis.hset(_redis_key(upload_id), mapping={"status": "paused"})
        await set_upload_progress(
            str(upload_id),
            user_id,
            meta["original_filename"],
            status="paused",
            progress=int(meta.get("uploaded_chunks", "0")) / max(int(meta.get("total_chunks", "1")), 1) * 100,
            total_size=int(meta.get("total_size", "0")),
        )
        await redis.close()

    @staticmethod
    async def resume(upload_id: UUID, user_id: Optional[UUID] = None) -> None:
        meta = await ResumableUploadService._load_meta(upload_id, user_id=user_id)
        redis = await create_pool(WorkerSettings.redis_settings)
        await redis.hset(_redis_key(upload_id), mapping={"status": "in_progress"})
        await set_upload_progress(
            str(upload_id),
            user_id,
            meta["original_filename"],
            status="uploading",
            progress=int(meta.get("uploaded_chunks", "0")) / max(int(meta.get("total_chunks", "1")), 1) * 100,
            total_size=int(meta.get("total_size", "0")),
        )
        await redis.close()

    @staticmethod
    async def cancel(upload_id: UUID, user_id: Optional[UUID] = None) -> None:
        await ResumableUploadService._load_meta(upload_id, user_id=user_id)
        temp_dir = _temp_dir(upload_id)
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        redis = await create_pool(WorkerSettings.redis_settings)
        await redis.delete(_redis_key(upload_id))
        await delete_upload_progress(str(upload_id))
        await redis.close()


    @staticmethod
    async def finalize(
        upload_id: UUID,
        db_session,
        user_id: Optional[UUID] = None,
    ) -> Media:
        """Assemble all chunks, move the file to its final location and create a
        :class:`Media` record in PostgreSQL.
        """
        meta = await ResumableUploadService._load_meta(upload_id, user_id=user_id)
        if meta.get("status") == "canceled":
            raise ValueError("Cannot finalize a canceled upload")

        total_size = int(meta["total_size"])
        chunk_size = int(meta["chunk_size"])
        uploaded = [int(i) for i in meta.get("uploaded_chunks", "").split(",") if i]
        expected_chunks = (total_size + chunk_size - 1) // chunk_size
        if len(uploaded) != expected_chunks:
            raise ValueError(
                f"Missing chunks: expected {expected_chunks}, received {len(uploaded)}"
            )

        original_filename = meta["original_filename"]
        ext = validate_filename_and_extension(original_filename)
        validate_file_size(total_size, settings.max_upload_size_bytes)

        first_chunk = _chunk_path(upload_id, 0)
        if first_chunk.exists():
            with open(first_chunk, "rb") as f0:
                header_data = f0.read(512)
                validate_file_content(header_data, ext)

        final_path = Path(settings.upload_dir) / meta["stored_filename"]
        final_path.parent.mkdir(parents=True, exist_ok=True)
        with open(final_path, "wb") as dst:
            for idx in range(expected_chunks):
                part_path = _chunk_path(upload_id, idx)
                if not part_path.exists():
                    raise ValueError(f"Chunk {idx} is missing on disk")
                with open(part_path, "rb") as src:
                    shutil.copyfileobj(src, dst)

        effective_user_id = user_id
        if effective_user_id is None and meta.get("user_id"):
            try:
                effective_user_id = UUID(meta["user_id"])
            except (ValueError, TypeError):
                pass

        await ResumableUploadService.cancel(upload_id)

        stored_filename = meta["stored_filename"]
        media_type = get_media_type(ext)
        mime_type = validate_mime_type(None, ext)
        media = Media(
            original_filename=original_filename,
            stored_filename=stored_filename,
            media_type=media_type,
            mime_type=mime_type,
            file_size=total_size,
            user_id=effective_user_id,
        )
        db_session.add(media)
        await db_session.commit()
        await db_session.refresh(media)
        return media
