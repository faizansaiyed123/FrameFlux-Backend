import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, status
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.auth.rate_limiter import check_rate_limit
from app.features.demo.schemas import DemoSessionEndResponse, DemoSessionResponse
from app.features.demo.service import (
    create_demo_workspace,
    end_demo_session,
    hash_client_ip,
)
from app.infrastructure.database import get_db
from app.infrastructure.redis import get_redis

router = APIRouter(prefix="/demo", tags=["Demo"])
settings = get_settings()


def _client_ip(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"

    # Railway's public HTTP edge overwrites X-Real-IP with the observed client
    # address. It is preferable to X-Forwarded-For there because Railway does
    # not guarantee a fixed XFF hop count. This opt-in mode must not be enabled
    # for private-network or TCP-proxy ingress, where the edge is bypassed.
    if settings.trust_railway_x_real_ip:
        real_ip = request.headers.get("x-real-ip", "").strip()
        if not real_ip:
            return client_host
        try:
            return str(ipaddress.ip_address(real_ip))
        except ValueError:
            return client_host

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            if candidate:
                return candidate
        real_ip = request.headers.get("x-real-ip")
        if real_ip and real_ip.strip():
            return real_ip.strip()
    return client_host


@router.post(
    "/session",
    response_model=DemoSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an isolated temporary recruiter workspace",
)
async def create_demo_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> DemoSessionResponse:
    if not settings.demo_enabled:
        raise HTTPException(status_code=404, detail="Demo mode is unavailable")

    ip_hash = hash_client_ip(_client_ip(request))
    allowed, count = await check_rate_limit(
        redis,
        f"demo:bootstrap:{ip_hash}",
        settings.demo_bootstrap_requests_per_ip,
        settings.demo_bootstrap_window_seconds,
    )
    if count < 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo session service is temporarily unavailable.",
            headers={"Retry-After": "5"},
        )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many demo workspaces have been requested from this network. Try again later.",
            headers={"Retry-After": str(settings.demo_bootstrap_window_seconds)},
        )

    demo_session, user, project, sample_media, token = await create_demo_workspace(
        db,
        client_ip_hash=ip_hash,
    )
    return DemoSessionResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.demo_session_ttl_minutes * 60,
        demo_session_id=str(demo_session.id),
        expires_at=demo_session.expires_at,
        user=user,
        project=project,
        sample_media=sample_media,
    )


@router.post(
    "/session/end",
    response_model=DemoSessionEndResponse,
    summary="End and clean up the current recruiter workspace",
)
async def finish_demo_session(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DemoSessionEndResponse:
    cleanup_state = await end_demo_session(db, current_user.id)
    return DemoSessionEndResponse(
        detail="Demo session ended. Its data will be removed after active processing finishes.",
        cleanup_state=cleanup_state,
    )
