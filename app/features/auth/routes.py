from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_db
from app.infrastructure.redis import get_redis
from app.features.auth.dependencies import (
    bearer_scheme,
    get_current_active_user,
)
from app.features.auth.models import User
from app.features.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.features.auth.service import (
    blocklist_token,
    change_password as svc_change_password,
    login as svc_login,
    request_password_reset,
    reset_password as svc_reset_password,
    signup as svc_signup,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def signup_route(
    request: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> User:
    return await svc_signup(db, request)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Log in and retrieve JWT access token",
)
async def login_route(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    return await svc_login(db, request)


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and revoke current access token",
)
async def logout_route(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: User = Depends(get_current_active_user),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    if credentials is not None and credentials.credentials:
        await blocklist_token(redis, credentials.credentials)
    return MessageResponse(detail="Successfully logged out.")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Request a password reset token",
)
async def forgot_password_route(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    await request_password_reset(db, redis, request.email)
    return MessageResponse(
        detail="If this email is registered, password reset instructions have been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset password using a valid reset token",
)
async def reset_password_route(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> MessageResponse:
    await svc_reset_password(db, redis, request)
    return MessageResponse(detail="Password has been reset successfully.")


@router.post(
    "/change-password",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password for authenticated user",
)
async def change_password_route(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    await svc_change_password(db, current_user, request)
    return MessageResponse(detail="Password changed successfully.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me_route(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user
