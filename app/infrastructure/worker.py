from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.infrastructure.tasks import (
    process_media_task,
    convert_media_task,
    edit_media_task,
    merge_media_task,
    transform_media_task,
    freeze_frame_task,
    overlay_media_task,
    split_media_task,
    clips_media_task,
)

settings = get_settings()


async def on_startup(ctx):
    try:
        ctx["redis"] = await create_worker_pool()
    except Exception:
        pass


async def on_shutdown(ctx):
    redis = ctx.get("redis")
    if redis:
        try:
            await redis.close()
        except Exception:
            pass


class WorkerSettings:
    functions = [
        process_media_task,
        convert_media_task,
        edit_media_task,
        merge_media_task,
        transform_media_task,
        freeze_frame_task,
        overlay_media_task,
        split_media_task,
        clips_media_task,
    ]

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = on_startup
    on_shutdown = on_shutdown


async def create_worker_pool():
    return await create_pool(
        WorkerSettings.redis_settings
    )
