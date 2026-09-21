import logging
import secrets
import time

import redis.asyncio as aioredis


logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, redis: aioredis.Redis):
        self._redis = redis
        self._prefix = "rate_limit:"

    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        now = int(time.time())
        window_start = now - window_seconds
        try:
            pipe = self._redis.pipeline()
            member_id = f"{now}:{secrets.token_hex(8)}"
            pipe.zremrangebyscore(
                f"{self._prefix}{key}",
                0,
                window_start,
            )
            pipe.zadd(
                f"{self._prefix}{key}",
                {member_id: now},
            )
            pipe.zcard(f"{self._prefix}{key}")
            pipe.pexpire(
                f"{self._prefix}{key}",
                window_seconds * 1000,
            )
            _, _, count, _ = await pipe.execute()
            return count <= max_requests, count
        except Exception as exc:
            logger.warning(
                "Rate limiter backend unavailable; denying request",
                extra={
                    "extra_fields": {
                        "key": key,
                        "reason": str(exc),
                    }
                },
            )
            return False, 0


async def check_rate_limit(
    redis: aioredis.Redis,
    key: str,
    max_requests: int = 5,
    window_seconds: int = 60,
) -> tuple[bool, int]:
    limiter = RateLimiter(redis)
    return await limiter.is_allowed(
        key,
        max_requests,
        window_seconds,
    )
