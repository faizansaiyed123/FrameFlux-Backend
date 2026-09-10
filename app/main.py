# app/main.py
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from app.features.auth.routes import router as auth_router
from app.features.health.routes import router as health_router
from app.features.jobs.routes import router as jobs_router
from app.features.media.routes import router as media_router
from app.features.projects.routes import router as projects_router
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(
    title="FrameFlux API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # your frontend URL
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
app.include_router(projects_router)

