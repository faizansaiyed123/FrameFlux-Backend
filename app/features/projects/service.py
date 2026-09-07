from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.models import Project
from app.features.projects.schemas import ProjectCreate, ProjectUpdate


async def create_project(
    db: AsyncSession,
    data: ProjectCreate,
) -> Project:
    project = Project(
        name=data.name,
        description=data.description,
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return project


async def list_projects(
    db: AsyncSession,
) -> list[Project]:
    result = await db.execute(
        select(Project).order_by(Project.updated_at.desc())
    )

    return list(result.scalars().all())


async def get_project(
    db: AsyncSession,
    project_id: UUID,
) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )

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
