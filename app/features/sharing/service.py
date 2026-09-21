from datetime import datetime, timedelta
from uuid import UUID, uuid4
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.sharing.models import ShareLink
from app.features.sharing.schemas import ShareCreate
from app.core.config import get_settings
from app.core.security import hash_password


async def create_share_link(db: AsyncSession, data: ShareCreate, user_id: UUID | None) -> ShareLink:
    token = uuid4().hex
    expires_at = None
    if data.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=data.expires_in_hours)
    share = ShareLink(
        user_id=user_id,
        media_id=data.media_id,
        token=token,
        password=hash_password(data.password) if data.password else None,
        expires_at=expires_at,
        allow_download=data.allow_download,
        allowed_domains=data.allowed_domains,
    )
    db.add(share)
    await db.commit()
    await db.refresh(share)
    return share


async def get_share_link(db: AsyncSession, token: str) -> ShareLink | None:
    result = await db.execute(select(ShareLink).where(ShareLink.token == token))
    share = result.scalar_one_or_none()
    if share is None:
        return None
    if share.expires_at is not None:
        expires_at = share.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
    return share


async def list_share_links(db: AsyncSession, user_id: UUID | None) -> list[ShareLink]:
    result = await db.execute(select(ShareLink).where(ShareLink.user_id == user_id))
    return result.scalars().all()


async def delete_share_link(db: AsyncSession, share: ShareLink) -> None:
    await db.delete(share)
    await db.commit()


async def disable_share_link(db: AsyncSession, share: ShareLink) -> ShareLink:
    share.is_active = False
    await db.commit()
    await db.refresh(share)
    return share


async def increment_view_count(db: AsyncSession, share: ShareLink) -> None:
    share.view_count += 1
    await db.commit()


async def check_domain_allowed(share: ShareLink, referer: str | None) -> bool:
    if not share.allowed_domains:
        return True
    if not referer:
        return False
    from urllib.parse import urlparse
    try:
        domain = urlparse(referer).netloc
        allowed = [d.strip() for d in share.allowed_domains.split(",")]
        return any(domain == a or domain.endswith("." + a) for a in allowed)
    except Exception:
        return False


async def get_embed_info(db: AsyncSession, token: str) -> dict | None:
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        return None
    from app.features.media.models import Media
    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        return None
    settings = get_settings()
    base_url = settings.api_base_url or "http://localhost:8000"
    embed_url = f"{base_url}/sharing/embed/{token}"
    embed_code = f'<iframe src="{embed_url}" width="640" height="360" frameborder="0" allowfullscreen></iframe>'
    return {
        "embed_url": embed_url,
        "embed_code": embed_code,
        "media_title": media.original_filename,
    }
