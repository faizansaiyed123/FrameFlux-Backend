from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.media.models import Media

router = APIRouter(prefix="/storage", tags=["Storage"])


@router.get("/usage")
async def get_storage_usage(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            func.sum(Media.file_size).label("total_size"),
            func.count(Media.id).label("total_files"),
        ).where(Media.user_id == current_user.id)
    )
    row = result.one_or_none()
    total_size = row[0] if row and row[0] is not None else 0
    total_files = row[1] if row and row[1] is not None else 0
    return {
        "total_size": total_size,
        "total_files": total_files,
        "user_id": str(current_user.id),
    }


@router.get("/usage/by-type")
async def get_storage_by_type(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Media.media_type,
            func.sum(Media.file_size).label("total_size"),
            func.count(Media.id).label("count"),
        )
        .where(Media.user_id == current_user.id)
        .group_by(Media.media_type)
    )
    rows = result.all()
    return [
        {"media_type": row[0], "total_size": row[1], "count": row[2]}
        for row in rows
    ]


@router.get("/usage/by-folder")
async def get_storage_by_folder(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Media.folder,
            func.sum(Media.file_size).label("total_size"),
            func.count(Media.id).label("count"),
        )
        .where(Media.user_id == current_user.id)
        .group_by(Media.folder)
    )
    rows = result.all()
    return [
        {"folder": row[0] or "root", "total_size": row[1], "count": row[2]}
        for row in rows
    ]
