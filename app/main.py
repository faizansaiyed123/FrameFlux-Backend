# app/main.py

from fastapi import FastAPI

from app.features.health.routes import router as health_router
from app.features.media.routes import router as media_router

app = FastAPI(
    title="FrameFlux API",
)

app.include_router(health_router)
app.include_router(media_router)
