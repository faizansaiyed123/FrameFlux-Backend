import logging
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import AppError, RateLimitedError
from app.core.logging import configure_logging, get_logger, request_id_var
from app.features.auth.routes import router as auth_router
from app.features.health.routes import router as health_router
from app.features.jobs.routes import router as jobs_router
from app.features.media.routes import router as media_router
from app.features.media.gif_routes import router as gif_router
from app.features.media.info_routes import router as media_info_router
from app.features.preview.routes import router as preview_router
from app.features.projects.routes import router as projects_router
from app.features.audio.routes import router as audio_router
from app.features.thumbnails.routes import router as thumbnails_router
from app.features.subtitles.routes import router as subtitles_router
from app.features.dashboard.routes import router as dashboard_router
from app.features.favorites.routes import router as favorites_router
from app.features.quick_actions.routes import router as quick_actions_router
from app.features.batch.routes import router as batch_router
from app.features.presets.routes import router as presets_router
from app.features.video.routes import router as video_router
from app.features.workflows.routes import router as workflows_router
from app.features.comparisons.routes import router as comparisons_router
from app.features.sharing.routes import router as sharing_router
from app.features.history.routes import router as history_router
from app.features.storage.routes import router as storage_router
from app.features.search.routes import router as search_router
from app.features.notifications.routes import router as notifications_router
from app.features.ui.routes import router as ui_router
from app.features.images.routes import router as images_router
from app.features.export.routes import router as export_router
from app.features.metadata.routes import router as metadata_router

settings = get_settings()
configure_logging(level="DEBUG" if settings.debug else "INFO")
logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

_allowed_origins = list(
    dict.fromkeys(
        origin.strip()
        for origin in (
            f"{settings.app_origin},http://localhost:3000"
        ).split(",")
        if origin.strip()
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        # Public share players are intentionally embeddable. Setting DENY
        # globally would silently break the product's iframe sharing feature.
        if not request.url.path.startswith("/sharing/player/"):
            response.headers["x-frame-options"] = "DENY"
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = request_id
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)


def _error_envelope(
    code: str,
    message: str,
    details: dict | None = None,
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "request_id": request_id_var.get(),
    }


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    headers: dict[str, str] | None = None
    if isinstance(exc, RateLimitedError) and exc.retry_after_seconds is not None:
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(exc.code, exc.message, exc.details),
        headers=headers,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    headers = dict(exc.headers or {})
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_envelope(
            f"HTTP_{exc.status_code}",
            detail,
        ),
        headers=headers or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_envelope(
            "VALIDATION_ERROR",
            "Request validation failed",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.error(
        "Unhandled exception",
        exc_info=exc,
        extra={
            "extra_fields": {
                "path": request.url.path,
                "method": request.method,
            }
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_envelope(
            "INTERNAL_ERROR",
            "An unexpected error occurred",
        ),
    )


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


app.include_router(auth_router)
app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(media_router)
app.include_router(gif_router)
app.include_router(media_info_router)
app.include_router(preview_router)
app.include_router(projects_router)
app.include_router(audio_router)
app.include_router(thumbnails_router)
app.include_router(subtitles_router)
app.include_router(dashboard_router)
app.include_router(favorites_router)
app.include_router(quick_actions_router)
app.include_router(batch_router)
app.include_router(presets_router)
app.include_router(video_router)
app.include_router(workflows_router)
app.include_router(comparisons_router)
app.include_router(sharing_router)
app.include_router(history_router)
app.include_router(storage_router)
app.include_router(search_router)
app.include_router(notifications_router)
app.include_router(ui_router)
app.include_router(images_router)
app.include_router(export_router)
app.include_router(metadata_router)
