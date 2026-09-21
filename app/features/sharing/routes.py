from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, FileResponse
from html import escape
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.sharing.models import ShareLink
from app.features.sharing.service import (
    create_share_link,
    delete_share_link,
    disable_share_link,
    get_share_link,
    list_share_links,
    increment_view_count,
    check_domain_allowed,
    get_embed_info,
)
from app.features.sharing.schemas import ShareCreate, ShareResponse, EmbedResponse

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


@router.get("/stream/{token}")
async def stream_shared_media(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")
    referer = request.headers.get("referer")
    if not await check_domain_allowed(share, referer):
        raise HTTPException(status_code=403, detail="Domain not allowed for embedding")
    if share.password:
        import hashlib, hmac
        provided_password = request.query_params.get("password")
        if not provided_password:
            raise HTTPException(status_code=401, detail="Share password required")
        stored = share.password
        expected = "sha256$" + hashlib.sha256(provided_password.encode("utf-8")).hexdigest() if stored.startswith("sha256$") else stored
        if not hmac.compare_digest(expected, stored):
            raise HTTPException(status_code=403, detail="Invalid share password")
    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    from app.features.media.processor import get_uploaded_file
    file_path = get_uploaded_file(media.stored_filename)
    settings = get_settings()
    storage_dir = Path(settings.upload_dir).resolve()
    safe_path = file_path.resolve()
    try:
        safe_path.relative_to(storage_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid media path") from exc
    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path=safe_path, media_type=media.mime_type, filename=media.original_filename)


@router.get("/embed/{token}", response_model=EmbedResponse)
async def get_embed(token: str, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    embed_info = await get_embed_info(db, token)
    if embed_info is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return EmbedResponse(**embed_info)


@router.get("/player/{token}", response_class=HTMLResponse)
async def embed_player(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")
    
    # Check domain allowlist
    referer = request.headers.get("referer")
    if not await check_domain_allowed(share, referer):
        raise HTTPException(status_code=403, detail="Domain not allowed for embedding")
    
    # Password-protected shares require the supplied password.
    if share.password:
        import hashlib, hmac
        provided_password = request.query_params.get('password')
        if not provided_password:
            raise HTTPException(status_code=401, detail='Share password required')
        stored = share.password
        if stored.startswith('sha256
    
    # Increment view count
    await increment_view_count(db, share)
    
    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    
    from app.core.config import get_settings
    settings = get_settings()
    base_url = getattr(settings, 'storage_base_url', 'http://localhost:8000').rstrip('/')
    video_url = f"{base_url}/sharing/stream/{token}?password={request.query_params.get('password', '')}"
    
    safe_title = escape(media.original_filename, quote=True)
    safe_mime = escape(media.mime_type, quote=True)

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{safe_title}</title>
        <style>
            body {{ margin: 0; padding: 0; background: #000; font-family: system-ui; }}
            video {{ width: 100%; height: 100vh; object-fit: contain; }}
            .controls {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,0.8)); color: white; }}
        </style>
    </head>
    <body>
        <video controls playsinline>
            <source src="{escape(video_url, quote=True)}" type="{safe_mime}">
        </video>
        <div class="controls">
            <div style="font-weight: 500;">{safe_title}</div>
            <div style="font-size: 0.875rem; opacity: 0.7;">Shared via FrameFlux</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
):
            candidate = 'sha256
    
    # Increment view count
    await increment_view_count(db, share)
    
    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    
    from app.core.config import get_settings
    settings = get_settings()
    base_url = settings.storage_base_url or "http://localhost:8000"
    video_url = f"{base_url}/media/{media.stored_filename}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{media.original_filename}</title>
        <style>
            body {{ margin: 0; padding: 0; background: #000; font-family: system-ui; }}
            video {{ width: 100%; height: 100vh; object-fit: contain; }}
            .controls {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,0.8)); color: white; }}
        </style>
    </head>
    <body>
        <video controls playsinline>
            <source src="{video_url}" type="{media.mime_type}">
        </video>
        <div class="controls">
            <div style="font-weight: 500;">{media.original_filename}</div>
            <div style="font-size: 0.875rem; opacity: 0.7;">Shared via FrameFlux</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
 + hashlib.sha256(provided_password.encode('utf-8')).hexdigest()
            valid = hmac.compare_digest(candidate, stored)
        else:
            valid = hmac.compare_digest(provided_password, stored)
        if not valid:
            raise HTTPException(status_code=403, detail='Invalid share password')
    
    # Increment view count
    await increment_view_count(db, share)
    
    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    
    from app.core.config import get_settings
    settings = get_settings()
    base_url = settings.storage_base_url or "http://localhost:8000"
    video_url = f"{base_url}/media/{media.stored_filename}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{media.original_filename}</title>
        <style>
            body {{ margin: 0; padding: 0; background: #000; font-family: system-ui; }}
            video {{ width: 100%; height: 100vh; object-fit: contain; }}
            .controls {{ position: absolute; bottom: 0; left: 0; right: 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,0.8)); color: white; }}
        </style>
    </head>
    <body>
        <video controls playsinline>
            <source src="{video_url}" type="{media.mime_type}">
        </video>
        <div class="controls">
            <div style="font-weight: 500;">{media.original_filename}</div>
            <div style="font-size: 0.875rem; opacity: 0.7;">Shared via FrameFlux</div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
