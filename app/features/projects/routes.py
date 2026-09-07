from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


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
