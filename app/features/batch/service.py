from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.media.models import Media
from app.infrastructure.database import AsyncSessionLocal
import uuid

from app.infrastructure.worker import create_worker_pool
from app.features.jobs.service import set_processing_progress


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

    # Enqueue the batch execution task
    batch_job_id = str(job.id)
    arq_job_id = str(uuid.uuid4())
    pool = await create_worker_pool()
    try:
        arq_job = await pool.enqueue_job(
            "execute_batch_task",
            batch_job_id,
            [str(mid) for mid in media_ids],
            operation,
            options,
            arq_job_id,
            str(user_id) if user_id else None,
        )
        if arq_job:
            await set_processing_progress(
                media_id=batch_job_id,
                status="queued",
                progress=0,
                job_id=arq_job_id,
                stage="Batch queued for execution",
                task_name="execute_batch_task",
                redis=pool,
            )
    finally:
        await pool.close()

    return batch_job_id
