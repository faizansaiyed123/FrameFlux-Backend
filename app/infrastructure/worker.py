
from arq import create_pool
from arq.connections import RedisSettings

from app.infrastructure.tasks import (
    process_media_task,
    convert_media_task,
    edit_media_task,
    merge_media_task,
    transform_media_task,
    freeze_frame_task,
    overlay_media_task,
)


class WorkerSettings:
    functions = [
        process_media_task,
        convert_media_task,
        edit_media_task,
        merge_media_task,
        transform_media_task,
        freeze_frame_task,
        overlay_media_task,
    ]

    redis_settings = RedisSettings(
        host="localhost",
        port=6379,
        database=0,
    )


async def create_worker_pool():
    return await create_pool(
        WorkerSettings.redis_settings
    )