from fastapi import FastAPI

app = FastAPI(title="FrameFlux API")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
from fastapi import FastAPI

from app.features.health.routes import router as health_router

app = FastAPI(title="FrameFlux API")
app.include_router(health_router)
