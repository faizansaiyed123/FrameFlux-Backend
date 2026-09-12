# app/main.py
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import get_settings
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

app = FastAPI(
    title="FrameFlux API",
)

settings = get_settings()
if settings.environment == "development":
    allowed_origins = ["http://localhost:3000"]
else:
    allowed_origins = [settings.app_origin] if settings.app_origin else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

