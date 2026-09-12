from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.workflows.models import Workflow
from app.features.workflows.service import (
    create_workflow,
    delete_workflow,
    get_workflow,
    list_workflows,
    run_workflow,
    update_workflow,
)
from app.features.workflows.schemas import WorkflowCreate, WorkflowResponse, WorkflowUpdate

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create(data: WorkflowCreate, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await create_workflow(db, data, user_id=current_user.id)


@router.get("", response_model=list[WorkflowResponse])
async def list_all(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await list_workflows(db, user_id=current_user.id)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_one(workflow_id: UUID, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    workflow = await get_workflow(db, workflow_id, user_id=current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
async def update(workflow_id: UUID, data: WorkflowUpdate, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    workflow = await get_workflow(db, workflow_id, user_id=current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await update_workflow(db, workflow, data)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(workflow_id: UUID, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    workflow = await get_workflow(db, workflow_id, user_id=current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await delete_workflow(db, workflow)


@router.post("/{workflow_id}/run")
async def run(workflow_id: UUID, media_id: UUID, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    workflow = await get_workflow(db, workflow_id, user_id=current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return await run_workflow(db, workflow, media_id)
