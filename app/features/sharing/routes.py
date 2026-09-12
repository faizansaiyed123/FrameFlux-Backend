from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.infrastructure.database import get_db
from app.features.sharing.models import ShareLink
from app.features.sharing.service import create_share_link, delete_share_link, disable_share_link, get_share_link, list_share_links
from app.features.sharing.schemas import ShareCreate, ShareResponse

router = APIRouter(prefix="/sharing", tags=["Sharing"])


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share(data: ShareCreate, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await create_share_link(db, data, user_id=current_user.id)


@router.get("/{token}", response_model=ShareResponse)
async def get_share(token: str, db: AsyncSession = Depends(get_db)):
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")
    return share


@router.get("", response_model=list[ShareResponse])
async def list_shares(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return await list_share_links(db, user_id=current_user.id)


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(share_id: UUID, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ShareLink).where(ShareLink.id == share_id, ShareLink.user_id == current_user.id))
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    await delete_share_link(db, share)


@router.post("/{share_id}/disable", response_model=ShareResponse)
async def disable_share(share_id: UUID, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ShareLink).where(ShareLink.id == share_id, ShareLink.user_id == current_user.id))
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return await disable_share_link(db, share)
