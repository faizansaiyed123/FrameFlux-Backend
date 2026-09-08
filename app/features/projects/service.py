from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.models import Project
from app.features.projects.schemas import ProjectCreate, ProjectUpdate


async def create_project(
    db: AsyncSession,
    data: ProjectCreate,
    user_id: UUID | None = None,
) -> Project:
    project = Project(
        name=data.name,
        description=data.description,
        user_id=user_id,
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return project


async def list_projects(
    db: AsyncSession,
    user_id: UUID | None = None,
) -> list[Project]:
    query = select(Project)
    if user_id is not None:
        query = query.where(Project.user_id == user_id)
    query = query.order_by(Project.updated_at.desc())
    result = await db.execute(query)

    return list(result.scalars().all())


async def get_project(
    db: AsyncSession,
    project_id: UUID,
    user_id: UUID | None = None,
) -> Project | None:
    query = select(Project).where(Project.id == project_id)
    if user_id is not None:
        query = query.where(Project.user_id == user_id)
    result = await db.execute(query)

    return result.scalar_one_or_none()


async def update_project(
    db: AsyncSession,
    project: Project,
    data: ProjectUpdate,
) -> Project:
    if data.name is not None:
        project.name = data.name

    if data.description is not None:
        project.description = data.description

    await db.commit()
    await db.refresh(project)

    return project


async def delete_project(
    db: AsyncSession,
    project: Project,
) -> None:
    await db.delete(project)
    await db.commit()
