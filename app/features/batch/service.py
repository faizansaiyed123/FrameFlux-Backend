from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.media.models import Media
from app.infrastructure.database import AsyncSessionLocal


async def get_batch_media(db: AsyncSession, media_ids: list[UUID], user_id: UUID) -> list[Media]:
    result = await db.execute(
        select(Media).where(Media.id.in_(media_ids), Media.user_id == user_id)
    )
    return list(result.scalars().all())


async def create_batch_job(operation: str, media_ids: list[UUID], options: dict, user_id: UUID | None = None) -> str:
    from app.features.jobs.models import ProcessingJob
    from app.features.jobs.service import create_processing_job
    import json

    job = ProcessingJob(
        user_id=user_id,
        task_name=f"batch_{operation}",
        status="queued",
        progress=0,
        stage="Batch operation queued",
        operation_type="batch",
        operation_params=json.dumps({"operation": operation, "media_count": len(media_ids), "options": options}),
    )
    async with AsyncSessionLocal() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return str(job.id)
