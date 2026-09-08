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


async def create_worker_pool():
    return await create_pool(
        WorkerSettings.redis_settings
    )
