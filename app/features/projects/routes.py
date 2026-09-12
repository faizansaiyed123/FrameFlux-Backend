from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
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
from app.infrastructure.worker import create_worker_pool


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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_project(db, data, user_id=current_user.id)


@router.get(
    "",
    response_model=list[ProjectResponse],
)
async def list_all(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_projects(db, user_id=current_user.id)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
async def get_one(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)

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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)

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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)

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
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # First verify that the project exists and belongs to the current user.
    project = await get_project(db, project_id, user_id=current_user.id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = await db.execute(
        select(Media)
        .where(
            Media.project_id == project_id,
            (Media.user_id == current_user.id) | (Media.user_id.is_(None)),
        )
        .order_by(Media.created_at.desc())
    )

    return result.scalars().all()

@router.post("/{project_id}/process")
async def process_project(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = await db.execute(
        select(Media).where(
            Media.project_id == project_id,
            (Media.user_id == current_user.id) | (Media.user_id.is_(None)),
        )
    )

    media_list = result.scalars().all()

    if not media_list:
        raise HTTPException(
            status_code=404,
            detail="No media found in project",
        )

    redis = await create_worker_pool()

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
        await redis.close()

    return {
        "project_id": str(project_id),
        "status": "queued",
        "jobs": jobs,
    }


@router.get("/{project_id}/status")
async def project_processing_status(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    result = await db.execute(
        select(Media).where(
            Media.project_id == project_id,
            (Media.user_id == current_user.id) | (Media.user_id.is_(None)),
        )
    )

    media_list = result.scalars().all()

    total = len(media_list)
    completed = sum(
        1 for media in media_list
        if media.processing_status == "completed"
    )
    processing = sum(
        1 for media in media_list
        if media.processing_status == "processing"
    )
    queued = sum(
        1 for media in media_list
        if media.processing_status == "queued"
    )
    failed = sum(
        1 for media in media_list
        if media.processing_status == "failed"
    )

    if total == 0:
        status_value = "empty"
    elif completed == total:
        status_value = "completed"
    elif failed > 0:
        status_value = "failed"
    elif processing > 0:
        status_value = "processing"
    else:
        status_value = "queued"

    return {
        "project_id": str(project_id),
        "status": status_value,
        "total": total,
        "completed": completed,
        "processing": processing,
        "queued": queued,
        "failed": failed,
    }


# Project folders
@router.post("/{project_id}/folders")
async def create_project_folder(
    project_id: UUID,
    name: str,
    parent_id: UUID | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.features.projects.folder_models import ProjectFolder
    from uuid import uuid4
    folder = ProjectFolder(project_id=project_id, name=name, parent_id=parent_id)
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


@router.get("/{project_id}/folders")
async def list_project_folders(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.features.projects.folder_models import ProjectFolder
    result = await db.execute(select(ProjectFolder).where(ProjectFolder.project_id == project_id))
    folders = result.scalars().all()
    return [{"id": str(f.id), "name": f.name, "parent_id": str(f.parent_id) if f.parent_id else None} for f in folders]


# Project workflows
@router.get("/{project_id}/workflows")
async def list_project_workflows(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.features.workflows.models import Workflow
    result = await db.execute(select(Workflow).where(Workflow.user_id == current_user.id))
    workflows = result.scalars().all()
    return [{"id": str(w.id), "name": w.name} for w in workflows]


# Project history
@router.get("/{project_id}/history")
async def list_project_history(
    project_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id, user_id=current_user.id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.features.history.models import ProcessingHistory
    result = await db.execute(
        select(ProcessingHistory)
        .where(ProcessingHistory.user_id == current_user.id)
        .order_by(ProcessingHistory.created_at.desc())
    )
    entries = result.scalars().all()
    return [
        {
            "id": str(h.id),
            "operation": h.operation,
            "status": h.status,
            "created_at": h.created_at.isoformat(),
        }
        for h in entries
    ]
