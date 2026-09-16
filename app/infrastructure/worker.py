from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.infrastructure.tasks import (
    compress_media_task,
    process_media_task,
    convert_media_task,
    edit_media_task,
    merge_media_task,
    transform_media_task,
    freeze_frame_task,
    overlay_media_task,
    split_media_task,
    clips_media_task,
    process_media_unified_task,
    execute_workflow_task,
    execute_batch_task,
)

settings = get_settings()


async def on_startup(ctx):
    ctx["redis"] = await create_pool(
        WorkerSettings.redis_settings,
    )


async def on_shutdown(ctx):
    redis = ctx.get("redis")
    if redis is not None:
        try:
            await redis.close()
        except Exception:
            pass


class WorkerSettings:
    functions = [
        compress_media_task,
        process_media_task,
        convert_media_task,
        edit_media_task,
        merge_media_task,
        transform_media_task,
        freeze_frame_task,
        overlay_media_task,
        split_media_task,
        clips_media_task,
        process_media_unified_task,
        execute_workflow_task,
        execute_batch_task,
    ]

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown
    job_timeout = settings.get_worker_job_timeout()
    max_jobs = settings.get_worker_max_jobs()
    keep_result = 3600


async def create_worker_pool():
    return await create_pool(WorkerSettings.redis_settings)
