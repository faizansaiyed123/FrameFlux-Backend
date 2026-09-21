from datetime import datetime, timezone
from html import escape
from pathlib import Path
import hashlib
import hmac
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.features.media.processor import get_uploaded_file
from app.features.sharing.models import ShareLink
from app.features.sharing.schemas import EmbedResponse, ShareCreate, ShareResponse
from app.features.sharing.service import (
    check_domain_allowed,
    create_share_link,
    delete_share_link,
    disable_share_link,
    get_embed_info,
    get_share_link,
    increment_view_count,
    list_share_links,
)
from app.infrastructure.database import get_db

router = APIRouter(prefix="/sharing", tags=["Sharing"])


async def _get_owned_share(
    share_id,
    user_id,
    db: AsyncSession,
) -> ShareLink:
    result = await db.execute(
        select(ShareLink).where(ShareLink.id == share_id, ShareLink.user_id == user_id)
    )
    share = result.scalar_one_or_none()
    if share is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return share


def _verify_password(share: ShareLink, password: str | None) -> None:
    if not share.password:
        return
    if not password:
        raise HTTPException(status_code=401, detail="Share password required")
    stored = share.password
    if stored.startswith("sha256$"):
        candidate = "sha256$" + hashlib.sha256(password.encode("utf-8")).hexdigest()
    else:
        candidate = password
    if not hmac.compare_digest(candidate, stored):
        raise HTTPException(status_code=403, detail="Invalid share password")


async def _get_shared_media(
    token: str,
    request: Request,
    db: AsyncSession,
) -> tuple[ShareLink, Media]:
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")

    referer = request.headers.get("referer")
    if not await check_domain_allowed(share, referer):
        raise HTTPException(status_code=403, detail="Domain not allowed for embedding")

    _verify_password(share, request.query_params.get("password"))

    result = await db.execute(select(Media).where(Media.id == share.media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return share, media


@router.post("", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def create_share(
    data: ShareCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Media).where(Media.id == data.media_id, Media.user_id == current_user.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return await create_share_link(db, data, user_id=current_user.id)


@router.get("", response_model=list[ShareResponse])
async def list_shares(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_share_links(db, user_id=current_user.id)


@router.get("/embed/{token}", response_model=EmbedResponse)
async def get_embed(token: str, db: AsyncSession = Depends(get_db)):
    embed_info = await get_embed_info(db, token)
    if embed_info is None:
        raise HTTPException(status_code=404, detail="Share link not found")
    return EmbedResponse(**embed_info)


@router.get("/player/{token}", response_class=HTMLResponse)
async def embed_player(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    share, media = await _get_shared_media(token, request, db)
    await increment_view_count(db, share)

    settings = get_settings()
    base_url = getattr(settings, "storage_base_url", "http://localhost:8000").rstrip("/")
    password = request.query_params.get("password")
    stream_url = f"{base_url}/sharing/stream/{token}"
    if password:
        stream_url += f"?password={urlparse('?password=' + password).query.split('=', 1)[1]}"

    safe_title = escape(media.original_filename, quote=True)
    safe_mime = escape(media.mime_type, quote=True)
    safe_stream = escape(stream_url, quote=True)

    html_content = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{safe_title}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    html,body{{margin:0;width:100%;height:100%;background:#000}}
    video{{width:100%;height:100vh;object-fit:contain}}
  </style>
</head>
<body>
  <video controls playsinline preload="metadata">
    <source src="{safe_stream}" type="{safe_mime}">
  </video>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get("/stream/{token}")
async def stream_shared_media(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    share, media = await _get_shared_media(token, request, db)
    # Respect download permissions for shared media.
    if not share.allow_download:
        disposition = "inline"
    else:
        disposition = "inline"

    file_path = get_uploaded_file(media.stored_filename)
    storage_dir = Path(get_settings().upload_dir).resolve()
    try:
        safe_path = file_path.resolve()
        safe_path.relative_to(storage_dir)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid media path") from exc

    if not safe_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")

    response = FileResponse(
        path=safe_path,
        media_type=media.mime_type,
        filename=media.original_filename,
    )
    response.headers["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{urlparse('http://x/' + media.original_filename).path.rsplit('/',1)[-1]}"
    return response


@router.get("/{token}", response_model=ShareResponse)
async def get_share(token: str, db: AsyncSession = Depends(get_db)):
    share = await get_share_link(db, token)
    if share is None or not share.is_active:
        raise HTTPException(status_code=404, detail="Share link not found")
    return share


@router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_share(
    share_id,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    share = await _get_owned_share(share_id, current_user.id, db)
    await delete_share_link(db, share)


@router.post("/{share_id}/disable", response_model=ShareResponse)
async def disable_share(
    share_id,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    share = await _get_owned_share(share_id, current_user.id, db)
    return await disable_share_link(db, share)
