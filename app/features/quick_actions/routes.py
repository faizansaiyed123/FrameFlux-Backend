from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.routes import get_media_or_404

router = APIRouter(prefix="/quick-actions", tags=["Quick Actions"])


@router.get("")
async def get_quick_actions(
    current_user: User = Depends(get_current_active_user),
):
    return {
        "video": [
            {"id": "convert", "label": "Convert", "icon": "swap_horiz"},
            {"id": "compress", "label": "Compress", "icon": "compress"},
            {"id": "extract-audio", "label": "Extract Audio", "icon": "audio_file"},
            {"id": "generate-thumbnail", "label": "Generate Thumbnail", "icon": "image"},
            {"id": "generate-preview", "label": "Generate Preview", "icon": "movie"},
            {"id": "trim", "label": "Trim", "icon": "content_cut"},
            {"id": "cut", "label": "Cut", "icon": "scissors"},
            {"id": "crop", "label": "Crop", "icon": "crop"},
            {"id": "resize", "label": "Resize", "icon": "photo_size_select_large"},
            {"id": "rotate", "label": "Rotate", "icon": "rotate_90_degrees_ccw"},
            {"id": "remove-audio", "label": "Remove Audio", "icon": "volume_off"},
            {"id": "replace-audio", "label": "Replace Audio", "icon": "audiotrack"},
            {"id": "add-subtitles", "label": "Add Subtitles", "icon": "subtitles"},
            {"id": "create-gif", "label": "Create GIF", "icon": "gif"},
            {"id": "add-external-audio", "label": "Add External Audio", "icon": "playlist_add"},
            {"id": "sync-audio", "label": "Sync External Audio", "icon": "sync"},
            {"id": "share", "label": "Share", "icon": "share"},
            {"id": "download", "label": "Download", "icon": "download"},
        ],
        "audio": [
            {"id": "convert", "label": "Convert", "icon": "swap_horiz"},
            {"id": "compress", "label": "Compress", "icon": "compress"},
            {"id": "trim", "label": "Trim", "icon": "content_cut"},
            {"id": "cut", "label": "Cut", "icon": "scissors"},
            {"id": "split", "label": "Split", "icon": "call_split"},
            {"id": "merge", "label": "Merge", "icon": "merge"},
            {"id": "change-volume", "label": "Change Volume", "icon": "volume_up"},
            {"id": "normalize", "label": "Normalize", "icon": "graphic_eq"},
            {"id": "fade-in", "label": "Fade In", "icon": "trending_up"},
            {"id": "fade-out", "label": "Fade Out", "icon": "trending_down"},
            {"id": "convert-to-video", "label": "Convert to Video", "icon": "videocam"},
            {"id": "download", "label": "Download", "icon": "download"},
            {"id": "share", "label": "Share", "icon": "share"},
        ],
    }


@router.post("/{media_id}/execute")
async def execute_quick_action(
    media_id: UUID,
    action_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    media = await get_media_or_404(media_id, db, user_id=current_user.id)
    return {
        "media_id": str(media.id),
        "action_id": action_id,
        "status": "queued",
    }
