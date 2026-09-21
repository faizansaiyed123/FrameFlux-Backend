from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.features.health.schemas import (
    DependencyStatus,
    HealthResponse,
    ReadinessResponse,
)
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.redis import get_redis_client

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=HealthResponse)
async def liveness() -> HealthResponse:
    return HealthResponse(status="ok")


async def _check_readiness() -> ReadinessResponse:
    dependencies: list[DependencyStatus] = []

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        dependencies.append(DependencyStatus(name="database", status="ok"))
    except Exception as exc:
        dependencies.append(
            DependencyStatus(
                name="database",
                status="error",
                error=str(exc),
            )
        )

    redis_client = get_redis_client()
    try:
        await redis_client.ping()
        dependencies.append(DependencyStatus(name="redis", status="ok"))
    except Exception as exc:
        dependencies.append(
            DependencyStatus(
                name="redis",
                status="error",
                error=str(exc),
            )
        )
    finally:
        await redis_client.aclose()

    overall = "ok" if all(
        dependency.status == "ok" for dependency in dependencies
    ) else "degraded"

    return ReadinessResponse(
        status=overall,
        dependencies=dependencies,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    result = await _check_readiness()
    if result.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("", response_model=ReadinessResponse)
async def health_check(response: Response) -> ReadinessResponse:
    return await readiness(response)
