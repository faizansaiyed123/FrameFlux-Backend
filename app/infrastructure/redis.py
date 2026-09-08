# app/infrastructure/redis.py

from collections.abc import AsyncGenerator
import redis.asyncio as aioredis

from app.core.config import get_settings

settings = get_settings()


def get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        encoding="utf-8",
    )


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    client = get_redis_client()
    try:
        yield client
    finally:
        await client.aclose()
