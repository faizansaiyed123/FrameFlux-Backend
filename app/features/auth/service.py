import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
import jwt
import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_password_reset_token,
    hash_password,
    verify_password,
)
from app.features.auth.models import User
from app.features.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

BLOCKLIST_PREFIX = "token:blocklist:"
RESET_TOKEN_PREFIX = "pwd_reset:"


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(func.lower(User.email) == func.lower(email.strip()))
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def signup(db: AsyncSession, request: SignupRequest) -> User:
    existing_user = await get_user_by_email(db, request.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    hashed_pwd = hash_password(request.password)
    user = User(
        email=request.email.strip().lower(),
        password_hash=hashed_pwd,
        full_name=request.full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def login(db: AsyncSession, request: LoginRequest) -> TokenResponse:
    user = await authenticate(db, request.email, request.password)
    access_token = create_access_token(user.id)
    expires_in = settings.jwt_expire_minutes * 60
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


async def blocklist_token(redis: aioredis.Redis, token: str) -> None:
    try:
        payload = decode_access_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            now_ts = datetime.now(timezone.utc).timestamp()
            ttl = int(exp - now_ts)
            if ttl > 0:
                await redis.set(f"{BLOCKLIST_PREFIX}{jti}", "1", ex=ttl)
    except jwt.PyJWTError:
        pass
    except Exception as exc:
        logger.warning("Failed to store token blocklist in Redis: %s", exc)


async def is_token_blocklisted(redis: aioredis.Redis, jti: str) -> bool:
    try:
        val = await redis.get(f"{BLOCKLIST_PREFIX}{jti}")
        return val is not None
    except Exception as exc:
        logger.warning("Failed to check token blocklist in Redis: %s", exc)
        return False


async def request_password_reset(
    db: AsyncSession,
    redis: aioredis.Redis,
    email: str,
) -> str | None:
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None

    token = generate_password_reset_token()
    ttl = settings.password_reset_expire_minutes * 60
    key = f"{RESET_TOKEN_PREFIX}{token}"

    try:
        await redis.set(key, str(user.id), ex=ttl)
    except Exception as exc:
        logger.error("Failed to store reset token in Redis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process password reset request",
        )
    return token


async def reset_password(
    db: AsyncSession,
    redis: aioredis.Redis,
    request: ResetPasswordRequest,
) -> None:
    key = f"{RESET_TOKEN_PREFIX}{request.token}"
    try:
        user_id_str = await redis.get(key)
    except Exception as exc:
        logger.error("Failed to get reset token from Redis: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify password reset token",
        )

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # Enforce single-use by deleting the token immediately
    try:
        await redis.delete(key)
    except Exception as exc:
        logger.warning("Failed to delete reset token from Redis: %s", exc)

    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    user.password_hash = hash_password(request.new_password)
    await db.commit()


async def change_password(
    db: AsyncSession,
    user: User,
    request: ChangePasswordRequest,
) -> None:
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    user.password_hash = hash_password(request.new_password)
    await db.commit()


