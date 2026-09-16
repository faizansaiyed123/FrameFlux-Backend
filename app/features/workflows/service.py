import json
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.workflows.models import Workflow
from app.features.workflows.schemas import WorkflowCreate, WorkflowUpdate, WorkflowOperation
from app.infrastructure.tasks import execute_workflow_task
from app.infrastructure.worker import create_worker_pool
from app.features.jobs.service import set_processing_progress


async def create_workflow(db: AsyncSession, data: WorkflowCreate, user_id: UUID | None) -> Workflow:
    workflow = Workflow(
        user_id=user_id,
        name=data.name,
        description=data.description,
        operations=json.dumps([op.model_dump() for op in data.operations]),
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


async def get_workflow(db: AsyncSession, workflow_id: UUID, user_id: UUID | None) -> Workflow | None:
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if workflow is None:
        return None
    if workflow.user_id is not None and workflow.user_id != user_id:
        return None
    return workflow


async def list_workflows(db: AsyncSession, user_id: UUID | None) -> list[Workflow]:
    result = await db.execute(select(Workflow).where((Workflow.user_id == user_id) | Workflow.user_id.is_(None)))
    return result.scalars().all()


async def update_workflow(db: AsyncSession, workflow: Workflow, data: WorkflowUpdate) -> Workflow:
    if data.name is not None:
        workflow.name = data.name
    if data.description is not None:
        workflow.description = data.description
    if data.operations is not None:
        workflow.operations = json.dumps([op.model_dump() for op in data.operations])
    await db.commit()
    await db.refresh(workflow)
    return workflow


async def delete_workflow(db: AsyncSession, workflow: Workflow) -> None:
    await db.delete(workflow)
    await db.commit()


async def run_workflow(db: AsyncSession, workflow: Workflow, media_id: UUID) -> dict:
    # Create a job ID for tracking
    job_id = str(uuid.uuid4())

    # Enqueue the workflow execution task
    pool = await create_worker_pool()
    try:
        arq_job = await pool.enqueue_job(
            "execute_workflow_task",
            str(workflow.id),
            str(media_id),
            job_id,
            str(workflow.user_id) if workflow.user_id else None,
        )
        if arq_job:
            await set_processing_progress(
                media_id=str(media_id),
                status="queued",
                progress=0,
                job_id=job_id,
                stage="Workflow queued for execution",
                task_name="execute_workflow_task",
                redis=pool,
            )
    finally:
        await pool.close()

    return {
        "workflow_id": str(workflow.id),
        "media_id": str(media_id),
        "job_id": job_id,
        "arq_job_id": arq_job.job_id if arq_job else None,
        "status": "queued",
    }
