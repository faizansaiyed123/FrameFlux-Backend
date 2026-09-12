from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.history.models import ProcessingHistory
from app.features.history.schemas import ProcessingHistoryResponse


async def create_history_entry(
    db: AsyncSession,
    user_id: UUID | None,
    media_id: UUID,
    operation: str,
    status: str,
    settings: str | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> ProcessingHistory:
    entry = ProcessingHistory(
        user_id=user_id,
        media_id=media_id,
        operation=operation,
        status=status,
        settings=settings,
        error=error,
        started_at=started_at,
        finished_at=finished_at,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def list_history(db: AsyncSession, user_id: UUID | None) -> list[ProcessingHistory]:
    result = await db.execute(
        select(ProcessingHistory).where(ProcessingHistory.user_id == user_id).order_by(ProcessingHistory.created_at.desc())
    )
    return result.scalars().all()
