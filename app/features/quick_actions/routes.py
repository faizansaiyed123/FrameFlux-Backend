from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID, uuid4

from app.features.auth.dependencies import get_current_active_user
from app.features.auth.models import User
from app.features.media.models import Media
from app.infrastructure.database import get_db
from app.features.media.routes import get_media_or_404, enqueue_media_job, mark_processing_pending
from app.features.media.processor import get_uploaded_file
from app.features.audio.processor import convert_audio
from app.core.config import get_settings
from pathlib import Path
import asyncio

settings = get_settings()

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
        "image": [
            {"id": "convert", "label": "Convert", "icon": "swap_horiz"},
            {"id": "compress", "label": "Compress", "icon": "compress"},
            {"id": "resize", "label": "Resize", "icon": "photo_size_select_large"},
            {"id": "crop", "label": "Crop", "icon": "crop"},
            {"id": "rotate", "label": "Rotate", "icon": "rotate_90_degrees_ccw"},
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

    # Video actions that have corresponding async tasks
    video_task_actions = {
        "convert": {"task": "convert_media_task", "format": "mp4"},
        "compress": {"task": "compress_media_task", "format": "mp4"},
        "trim": {"task": "edit_media_task", "operation": "trim", "format": "mp4"},
        "cut": {"task": "edit_media_task", "operation": "cut", "format": "mp4"},
        "crop": {"task": "transform_media_task", "operation": "crop", "format": "mp4"},
        "resize": {"task": "transform_media_task", "operation": "resize", "format": "mp4"},
        "rotate": {"task": "transform_media_task", "operation": "rotate", "format": "mp4"},
        "remove-audio": {"task": "transform_media_task", "operation": "remove_audio", "format": "mp4"},
        "split": {"task": "split_media_task", "format": "mp4"},
        "merge": {"task": "merge_media_task", "format": "mp4"},
    }

    # Audio actions that use direct synchronous endpoints
    audio_direct_actions = {
        "compress", "trim", "cut", "split", "merge",
        "change-volume", "normalize", "fade-in", "fade-out",
        "convert-to-video", "share", "download",
    }

    # Video actions that use direct synchronous endpoints
    video_direct_actions = {
        "extract-audio", "generate-thumbnail", "generate-preview",
        "replace-audio", "add-subtitles", "create-gif",
        "add-external-audio", "sync-audio",
        "share", "download",
    }

    # Image actions that use direct synchronous endpoints
    image_direct_actions = {
        "convert", "compress", "resize", "crop", "rotate",
        "share", "download",
    }

    if media.media_type == "video":
        if action_id in video_task_actions:
            action = video_task_actions[action_id]
            task_name = action["task"]
            output_format = action.get("format", "mp4")
            output_filename = f"{media_id}_{action_id}_{uuid4().hex[:8]}.{output_format}"

            options = {}
            if "operation" in action:
                options["operation"] = action["operation"]

            job = await enqueue_media_job(
                task_name,
                str(media.id),
                media.stored_filename,
                output_filename,
                options,
            )
            await mark_processing_pending(media, db)
            return {
                "media_id": str(media.id),
                "action_id": action_id,
                "status": "queued",
                "job_id": job.job_id,
                "output_filename": output_filename,
            }

        if action_id in video_direct_actions:
            return {
                "media_id": str(media.id),
                "action_id": action_id,
                "status": "direct",
                "message": f"Use direct API endpoint for {action_id}",
            }

    elif media.media_type == "audio":
        if action_id == "convert":
            output_filename = f"{media_id}_{action_id}_{uuid4().hex[:8]}.wav"
            job = await enqueue_media_job(
                "convert_audio_task",
                str(media.id),
                media.stored_filename,
                output_filename,
                {"format": "wav"},
            )
            await mark_processing_pending(media, db)
            return {
                "media_id": str(media.id),
                "action_id": action_id,
                "status": "queued",
                "job_id": job.job_id,
                "output_filename": output_filename,
            }

        if action_id in audio_direct_actions:
            return {
                "media_id": str(media.id),
                "action_id": action_id,
                "status": "direct",
                "message": f"Use direct API endpoint for {action_id}",
            }

    elif media.media_type == "image":
        if action_id in image_direct_actions:
            return {
                "media_id": str(media.id),
                "action_id": action_id,
                "status": "direct",
                "message": f"Use direct API endpoint for {action_id}",
            }

    raise HTTPException(status_code=400, detail=f"Unknown action: {action_id} for media type: {media.media_type}")
