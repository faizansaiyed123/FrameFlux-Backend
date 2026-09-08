from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.media.models import Media
from app.features.projects.schemas import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)
from app.features.projects.service import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)
from app.infrastructure.database import get_db
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)

settings = get_settings()

@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
):
    return await create_project(db, data)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
async def list_all(
    db: AsyncSession = Depends(get_db),
):
    return await list_projects(db)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_one(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    return project


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def update(
    project_id: UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    return await update_project(db, project, data)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    await delete_project(db, project)


@router.get(
    "/{project_id}/media",
)
async def list_project_media(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    # First verify that the project exists.
    project = await get_project(db, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = await db.execute(
        select(Media)
        .where(Media.project_id == project_id)
        .order_by(Media.created_at.desc())
    )

    return result.scalars().all()

@router.post("/{project_id}/process")
async def process_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = await db.execute(
        select(Media).where(Media.project_id == project_id)
    )

    media_list = result.scalars().all()

    if not media_list:
        raise HTTPException(
            status_code=404,
            detail="No media found in project",
        )

    redis = await create_pool(
        RedisSettings(
            host="localhost",
            port=6379,
            database=0,
        )
    )

    jobs = []

    try:
        for media in media_list:
            media.processing_status = "queued"
            media.processing_error = None

            job = await redis.enqueue_job(
                "process_media_task",
                str(media.id),
                media.stored_filename,
            )

            jobs.append(
                {
                    "media_id": str(media.id),
                    "job_id": job.job_id,
                }
            )

        await db.commit()

    finally:
        await redis.aclose()

    return {
        "project_id": str(project_id),
        "status": "queued",
        "jobs": jobs,
    }