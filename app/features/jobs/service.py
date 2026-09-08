import logging
from datetime import datetime
from uuid import UUID
from typing import Any

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus

from arq import create_pool
from arq.connections import RedisSettings
from app.core.config import get_settings


async def get_redis_pool() -> ArqRedis:
    settings = get_settings()
    return await create_pool(RedisSettings.from_dsn(settings.redis_url))

logger = logging.getLogger(__name__)

MEDIA_PROGRESS_PREFIX = "media:progress:"
JOB_PROGRESS_PREFIX = "job:progress:"
MEDIA_LAST_JOB_PREFIX = "media:last_job:"
PROGRESS_TTL = 86400  # 24 hours retention in Redis


async def set_processing_progress(
    media_id: str | UUID,
    status: str,
    progress: int,
    job_id: str | None = None,
    error: str | None = None,
    stage: str | None = None,
    task_name: str | None = None,
    redis: ArqRedis | None = None,
) -> None:
    """
    Records real-time processing progress and status into Redis.
    Fails safely without raising exceptions so task execution is never interrupted.
    """
    media_id_str = str(media_id)
    should_close = False
    try:
        if redis is None:
            redis = await get_redis_pool()
            should_close = True

        bounded_progress = max(0, min(100, int(progress)))
        now_str = datetime.utcnow().isoformat()

        data = {
            "media_id": media_id_str,
            "job_id": job_id or "",
            "status": status,
            "progress": str(bounded_progress),
            "stage": stage or "",
            "error": error or "",
            "task_name": task_name or "",
            "updated_at": now_str,
        }

        media_key = f"{MEDIA_PROGRESS_PREFIX}{media_id_str}"
        await redis.hset(media_key, mapping=data)
        await redis.expire(media_key, PROGRESS_TTL)

        if job_id:
            job_key = f"{JOB_PROGRESS_PREFIX}{job_id}"
            await redis.hset(job_key, mapping=data)
            await redis.expire(job_key, PROGRESS_TTL)

            last_job_key = f"{MEDIA_LAST_JOB_PREFIX}{media_id_str}"
            await redis.set(last_job_key, job_id, ex=PROGRESS_TTL)

    except Exception as exc:
        logger.debug("Failed to record progress in Redis: %s", exc)
    finally:
        if should_close and redis is not None:
            try:
                await redis.close()
            except Exception:
                pass


async def get_media_progress(
    media_id: str | UUID,
    db_media: Any = None,
    redis: ArqRedis | None = None,
) -> dict[str, Any]:
    """
    Fetches the combined processing status and progress for a given media ID.
    Reconciles Redis real-time progress with PostgreSQL durable state.
    """
    media_id_str = str(media_id)
    should_close = False
    redis_data: dict[str, str] = {}
    last_job_id: str | None = None

    try:
        if redis is None:
            redis = await get_redis_pool()
            should_close = True

        raw = await redis.hgetall(f"{MEDIA_PROGRESS_PREFIX}{media_id_str}")
        if raw:
            redis_data = {
                (k.decode() if isinstance(k, (bytes, bytearray)) else str(k)): (
                    v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                )
                for k, v in raw.items()
            }

        last_job_raw = await redis.get(f"{MEDIA_LAST_JOB_PREFIX}{media_id_str}")
        if last_job_raw:
            last_job_id = (
                last_job_raw.decode()
                if isinstance(last_job_raw, (bytes, bytearray))
                else str(last_job_raw)
            )
    except Exception as exc:
        logger.debug("Failed to read progress from Redis for media %s: %s", media_id_str, exc)
    finally:
        if should_close and redis is not None:
            try:
                await redis.close()
            except Exception:
                pass

    db_status = getattr(db_media, "processing_status", None)
    db_error = getattr(db_media, "processing_error", None)
    db_processed_filename = getattr(db_media, "processed_filename", None)

    # Defaults
    status = "pending"
    progress = 0
    stage = None
    error = None
    job_id = redis_data.get("job_id") or last_job_id

    if redis_data:
        status = redis_data.get("status", "pending")
        try:
            progress = int(redis_data.get("progress", 0))
        except (ValueError, TypeError):
            progress = 0
        stage = redis_data.get("stage") or None
        error = redis_data.get("error") or None

    # PostgreSQL database state is the authority on completion / final failure
    if db_status == "completed":
        status = "completed"
        progress = 100
        stage = stage or "Processing completed"
        error = None
    elif db_status == "failed":
        status = "failed"
        error = db_error or error
        stage = stage or "Processing failed"
    elif not redis_data and db_status:
        status = db_status
        if status == "pending":
            progress = 0
            stage = "Queued for processing"
        elif status == "processing":
            progress = 50
            stage = "Processing media"

    return {
        "media_id": media_id_str,
        "status": status,
        "progress": progress,
        "stage": stage,
        "job_id": job_id,
        "processed_filename": db_processed_filename,
        "error": error,
    }


async def get_job_status(
    job_id: str,
    redis: ArqRedis | None = None,
) -> dict[str, Any] | None:
    """
    Inspects ARQ job status and Redis progress cache to monitor job execution.
    Answers:
      - Did the job start?
      - Is it still running?
      - Did it finish?
      - Did it fail?
      - What media is it processing?
    """
    should_close = False
    try:
        if redis is None:
            redis = await get_redis_pool()
            should_close = True

        # Read cached progress hash from Redis
        raw_progress = await redis.hgetall(f"{JOB_PROGRESS_PREFIX}{job_id}")
        progress_data: dict[str, str] = {}
        if raw_progress:
            progress_data = {
                (k.decode() if isinstance(k, (bytes, bytearray)) else str(k)): (
                    v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                )
                for k, v in raw_progress.items()
            }

        # Inspect ARQ Job
        arq_job = Job(job_id, redis)
        job_status = await arq_job.status()
        job_info = await arq_job.info()

        if job_status == JobStatus.not_found and not progress_data:
            return None

        status = "unknown"
        progress = 0
        stage = progress_data.get("stage") or None
        error = progress_data.get("error") or None
        media_id = progress_data.get("media_id") or None
        task_name = progress_data.get("task_name") or None
        success = None
        result = None
        enqueue_time = None
        start_time = None
        finish_time = None

        if progress_data:
            try:
                progress = int(progress_data.get("progress", 0))
            except (ValueError, TypeError):
                progress = 0

        if job_info:
            task_name = getattr(job_info, "function", None) or task_name
            if not media_id and getattr(job_info, "args", None) and len(job_info.args) > 0:
                media_id = str(job_info.args[0])

            if getattr(job_info, "enqueue_time", None):
                enqueue_time = job_info.enqueue_time.isoformat()
            if getattr(job_info, "start_time", None):
                start_time = job_info.start_time.isoformat()
            if getattr(job_info, "finish_time", None):
                finish_time = job_info.finish_time.isoformat()

            if hasattr(job_info, "success"):
                success = job_info.success
                if not success and hasattr(job_info, "result"):
                    error = error or str(job_info.result)
                elif success and hasattr(job_info, "result"):
                    result = job_info.result

        if job_status == JobStatus.queued:
            status = "queued"
            stage = stage or "Queued in background"
            progress = max(0, progress)
        elif job_status == JobStatus.deferred:
            status = "deferred"
            stage = stage or "Deferred"
        elif job_status == JobStatus.in_progress:
            status = "processing"
            progress = max(progress, 15)
            stage = stage or "Processing media"
        elif job_status == JobStatus.complete:
            if success is False or (error and not success):
                status = "failed"
                stage = stage or "Processing failed"
            else:
                status = "completed"
                progress = 100
                stage = stage or "Processing completed"
                success = True
        elif progress_data:
            # Fallback to cached progress data if ARQ TTL has expired
            status = progress_data.get("status", "unknown")

        return {
            "job_id": job_id,
            "status": status,
            "progress": progress,
            "stage": stage,
            "task_name": task_name,
            "media_id": media_id,
            "enqueue_time": enqueue_time,
            "start_time": start_time,
            "finish_time": finish_time,
            "success": success,
            "result": result,
            "error": error,
        }
    except Exception as exc:
        logger.exception("Error checking job status for %s: %s", job_id, exc)
        return None
    finally:
        if should_close and redis is not None:
            try:
                await redis.close()
            except Exception:
                pass


async def list_queued_jobs(redis: ArqRedis | None = None) -> list[dict[str, Any]]:
    """
    Returns a list of currently queued jobs in ARQ.
    """
    should_close = False
    try:
        if redis is None:
            redis = await get_redis_pool()
            should_close = True

        queued = await redis.queued_jobs()
        results = []
        for job_def in queued:
            results.append({
                "job_id": job_def.job_id,
                "status": "queued",
                "progress": 0,
                "stage": "In queue",
                "task_name": job_def.function,
                "media_id": str(job_def.args[0]) if job_def.args else None,
                "enqueue_time": job_def.enqueue_time.isoformat() if job_def.enqueue_time else None,
            })
        return results
    except Exception as exc:
        logger.debug("Failed to list queued jobs: %s", exc)
        return []
    finally:
        if should_close and redis is not None:
            try:
                await redis.close()
            except Exception:
                pass
