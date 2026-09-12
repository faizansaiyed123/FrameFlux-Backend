from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.history.models import ProcessingHistory
from app.features.history.service import create_history_entry, list_history
from app.features.history.schemas import ProcessingHistoryResponse

router = APIRouter(prefix="/history", tags=["Processing History"])


@router.get("", response_model=list[ProcessingHistoryResponse])
async def get_history(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await list_history(db, user_id=current_user.id)


@router.post("", response_model=ProcessingHistoryResponse, status_code=status.HTTP_201_CREATED)
async def add_history_entry(
    media_id: UUID,
    operation: str,
    status: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_history_entry(
        db,
        user_id=current_user.id,
        media_id=media_id,
        operation=operation,
        status=status,
    )
