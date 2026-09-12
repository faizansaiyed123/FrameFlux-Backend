import asyncio
import logging
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.infrastructure.worker import WorkerSettings

settings = get_settings()
logger = logging.getLogger(__name__)

UPLOAD_PROGRESS_PREFIX = "upload:progress:"
UPLOAD_PROGRESS_TTL = 3600


async def _get_redis():
    return await create_pool(WorkerSettings.redis_settings)


async def set_upload_progress(
    upload_id: str,
    user_id: UUID,
    filename: str,
    status: str = "uploading",
    progress: int = 0,
    total_size: int | None = None,
    uploaded_size: int | None = None,
    error: str | None = None,
) -> None:
    try:
        redis = await _get_redis()
        try:
            key = f"{UPLOAD_PROGRESS_PREFIX}{upload_id}"
            mapping = {
                "user_id": str(user_id),
                "filename": filename,
                "status": status,
                "progress": str(max(0, min(100, int(progress)))),
            }
            if total_size is not None:
                mapping["total_size"] = str(total_size)
            if uploaded_size is not None:
                mapping["uploaded_size"] = str(uploaded_size)
            if error is not None:
                mapping["error"] = error

            await redis.hset(key, mapping=mapping)
            await redis.expire(key, UPLOAD_PROGRESS_TTL)
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.debug("Failed to record upload progress in Redis: %s", exc)


async def get_upload_progress(upload_id: str, user_id: UUID) -> dict | None:
    try:
        redis = await _get_redis()
        try:
            key = f"{UPLOAD_PROGRESS_PREFIX}{upload_id}"
            data = await redis.hgetall(key)
            if not data:
                return None

            result = {
                k.decode() if isinstance(k, (bytes, bytearray)) else k: (
                    v.decode() if isinstance(v, (bytes, bytearray)) else v
                )
                for k, v in data.items()
            }

            if result.get("user_id") != str(user_id):
                return None

            return result
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.debug("Failed to read upload progress from Redis: %s", exc)
        return None


async def delete_upload_progress(upload_id: str) -> None:
    try:
        redis = await _get_redis()
        try:
            key = f"{UPLOAD_PROGRESS_PREFIX}{upload_id}"
            await redis.delete(key)
        finally:
            await redis.aclose()
    except Exception as exc:
        logger.debug("Failed to delete upload progress from Redis: %s", exc)
