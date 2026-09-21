"""Application exception hierarchy.

The API registers handlers in app.main that normalize errors into a stable
JSON envelope with a machine-readable code and request ID. Existing
HTTPException call sites continue to work; new code can use these typed
exceptions instead of string-matching error messages.
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for application-raised errors."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class MediaNotFoundError(NotFoundError):
    code = "MEDIA_NOT_FOUND"

    def __init__(self, media_id: Any):
        super().__init__("Media not found", details={"media_id": str(media_id)})


class ValidationAppError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_ERROR"


class AuthorizationError(AppError):
    status_code = 403
    code = "AUTHORIZATION_ERROR"


class ConflictError(AppError):
    """Use for state conflicts such as duplicate resources or busy jobs."""

    status_code = 409
    code = "CONFLICT"


class RateLimitedError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(
        self,
        message: str = "Too many requests",
        *,
        retry_after_seconds: int | None = None,
    ):
        details = (
            {"retry_after_seconds": retry_after_seconds}
            if retry_after_seconds is not None
            else {}
        )
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class StorageError(AppError):
    status_code = 500
    code = "STORAGE_ERROR"


class MediaProcessingError(AppError):
    status_code = 422
    code = "PROCESSING_ERROR"


class QuotaExceededError(AppError):
    status_code = 429
    code = "QUOTA_EXCEEDED"
