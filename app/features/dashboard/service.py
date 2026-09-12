from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.projects.models import Project
from app.features.media.models import Media
from app.features.jobs.models import ProcessingJob
from app.features.dashboard.schemas import (
    DashboardOverviewResponse,
    RecentProjectItem,
    RecentProcessingItem,
)
from app.features.media.schemas import MediaResponse


async def get_dashboard_overview(
    db: AsyncSession,
    user_id: UUID,
    recent_limit: int = 5,
) -> DashboardOverviewResponse:
    # 1. Total projects
    projects_count_stmt = (
        select(func.count())
        .select_from(Project)
        .where(Project.user_id == user_id)
    )
    total_projects = (await db.scalar(projects_count_stmt)) or 0

    # 2. Total media & total storage
    media_stats_stmt = (
        select(
            func.count(Media.id),
            func.coalesce(func.sum(Media.file_size), 0),
        )
        .where(Media.user_id == user_id)
    )
    media_stats = (await db.execute(media_stats_stmt)).one()
    total_media = media_stats[0] or 0
    total_storage_used_bytes = int(media_stats[1] or 0)

    # 3. Media by type
    media_type_stmt = (
        select(Media.media_type, func.count(Media.id))
        .where(Media.user_id == user_id)
        .group_by(Media.media_type)
    )
    media_type_results = (await db.execute(media_type_stmt)).all()
    media_by_type = {"video": 0, "audio": 0, "image": 0}
    for m_type, count in media_type_results:
        if m_type:
            media_by_type[m_type] = count

    # 4. Storage by type
    storage_by_type_stmt = (
        select(Media.media_type, func.coalesce(func.sum(Media.file_size), 0))
        .where(Media.user_id == user_id)
        .group_by(Media.media_type)
    )
    storage_by_type_results = (await db.execute(storage_by_type_stmt)).all()
    storage_by_type: dict[str, int] = {}
    for m_type, size in storage_by_type_results:
        if m_type:
            storage_by_type[m_type] = int(size)

    # 5. Processing status counts
    status_stmt = (
        select(Media.processing_status, func.count(Media.id))
        .where(Media.user_id == user_id)
        .group_by(Media.processing_status)
    )
    status_results = (await db.execute(status_stmt)).all()
    processing_status_counts = {
        "pending": 0,
        "queued": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }
    for p_status, count in status_results:
        if p_status:
            processing_status_counts[p_status] = count

    # 6. Active jobs count: media in pending, queued, or processing status
    active_jobs_count = (
        processing_status_counts.get("pending", 0)
        + processing_status_counts.get("queued", 0)
        + processing_status_counts.get("processing", 0)
    )

    # 7. Recent projects with media counts
    recent_projects_stmt = (
        select(
            Project,
            func.count(Media.id).label("media_count")
        )
        .outerjoin(Media, Media.project_id == Project.id)
        .where(Project.user_id == user_id)
        .group_by(Project.id)
        .order_by(Project.created_at.desc())
        .limit(recent_limit)
    )
    recent_projects_res = (await db.execute(recent_projects_stmt)).all()
    recent_projects = [
        RecentProjectItem(
            id=proj.id,
            user_id=proj.user_id,
            name=proj.name,
            description=proj.description,
            media_count=m_count,
            created_at=proj.created_at,
            updated_at=proj.updated_at,
        )
        for proj, m_count in recent_projects_res
    ]

    # 8. Recent media
    recent_media_stmt = (
        select(Media)
        .where(Media.user_id == user_id)
        .order_by(Media.created_at.desc())
        .limit(recent_limit)
    )
    recent_media_res = (await db.scalars(recent_media_stmt)).all()
    recent_media = [MediaResponse.model_validate(m) for m in recent_media_res]

    return DashboardOverviewResponse(
        total_projects=total_projects,
        total_media=total_media,
        media_by_type=media_by_type,
        processing_status_counts=processing_status_counts,
        total_storage_used_bytes=total_storage_used_bytes,
        storage_by_type=storage_by_type,
        recent_projects=recent_projects,
        recent_media=recent_media,
        active_jobs_count=active_jobs_count,
    )


async def get_recent_processing(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 10,
) -> list[RecentProcessingItem]:
    stmt = (
        select(ProcessingJob)
        .where(ProcessingJob.user_id == user_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    return [
        RecentProcessingItem(
            job_id=str(job.id),
            media_id=str(job.media_id) if job.media_id else None,
            task_name=job.task_name,
            status=job.status,
            progress=job.progress,
            stage=job.stage,
            error=job.error,
            enqueued_at=job.enqueued_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]
