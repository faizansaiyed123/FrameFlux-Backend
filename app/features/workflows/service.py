import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.workflows.models import Workflow
from app.features.workflows.schemas import WorkflowCreate, WorkflowUpdate, WorkflowOperation


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
    ops = json.loads(workflow.operations) if workflow.operations else []
    return {
        "workflow_id": str(workflow.id),
        "media_id": str(media_id),
        "operations_count": len(ops),
        "status": "queued",
    }
