import json
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.presets.models import Preset


BUILTIN_PRESETS = {
    "youtube": {
        "name": "YouTube",
        "description": "Optimized for YouTube uploads (1080p, H.264, AAC)",
        "settings": {"format": "mp4", "resolution": "1080p", "video_codec": "h264", "audio_codec": "aac", "quality": 23},
    },
    "youtube_shorts": {
        "name": "YouTube Shorts",
        "description": "Vertical video optimized for YouTube Shorts (1080x1920, 30fps)",
        "settings": {"format": "mp4", "resolution": "1080p", "width": 1080, "height": 1920, "fps": 30, "video_codec": "h264", "audio_codec": "aac"},
    },
    "instagram": {
        "name": "Instagram",
        "description": "Optimized for Instagram feed (1080p, H.264)",
        "settings": {"format": "mp4", "resolution": "1080p", "video_codec": "h264", "audio_codec": "aac", "quality": 23},
    },
    "tiktok": {
        "name": "TikTok",
        "description": "Vertical video optimized for TikTok (1080x1920, 30fps)",
        "settings": {"format": "mp4", "width": 1080, "height": 1920, "fps": 30, "video_codec": "h264", "audio_codec": "aac"},
    },
    "web": {
        "name": "Web",
        "description": "Optimized for web delivery (720p, H.264, smaller file size)",
        "settings": {"format": "mp4", "resolution": "720p", "video_codec": "h264", "audio_codec": "aac", "quality": 28},
    },
    "mobile": {
        "name": "Mobile",
        "description": "Optimized for mobile playback (720p, H.264)",
        "settings": {"format": "mp4", "resolution": "720p", "video_codec": "h264", "audio_codec": "aac", "quality": 25},
    },
    "podcast": {
        "name": "Podcast",
        "description": "Audio-focused settings for podcast distribution (AAC, 128kbps)",
        "settings": {"format": "mp4", "audio_codec": "aac", "audio_bitrate": "128k", "video_codec": "none"},
    },
    "archive": {
        "name": "Archive",
        "description": "High quality archival (lossless where possible)",
        "settings": {"format": "mkv", "video_codec": "h265", "audio_codec": "flac", "quality": 18},
    },
    "high_quality": {
        "name": "High Quality",
        "description": "Maximum quality output (H.265, high bitrate)",
        "settings": {"format": "mp4", "video_codec": "h265", "audio_codec": "aac", "quality": 18},
    },
    "small_file": {
        "name": "Small File",
        "description": "Smallest file size possible (high compression)",
        "settings": {"format": "mp4", "video_codec": "h264", "audio_codec": "aac", "quality": 32, "compression_preset": "maximum"},
    },
}


async def get_builtin_presets() -> list[dict]:
    return [{"id": str(uuid4()), **value} for key, value in BUILTIN_PRESETS.items()]


async def get_user_presets(db: AsyncSession, user_id: UUID) -> list[Preset]:
    result = await db.execute(select(Preset).where(Preset.user_id == user_id))
    return list(result.scalars().all())


async def create_preset(db: AsyncSession, user_id: UUID, name: str, description: str | None, settings: dict) -> Preset:
    preset = Preset(
        user_id=user_id,
        name=name,
        description=description,
        is_builtin=False,
        settings=json.dumps(settings),
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


async def update_preset(db: AsyncSession, preset_id: UUID, user_id: UUID, name: str | None, description: str | None, settings: dict | None) -> Preset | None:
    result = await db.execute(select(Preset).where(Preset.id == preset_id, Preset.user_id == user_id))
    preset = result.scalar_one_or_none()
    if preset is None:
        return None

    if name is not None:
        preset.name = name
    if description is not None:
        preset.description = description
    if settings is not None:
        preset.settings = json.dumps(settings)

    await db.commit()
    await db.refresh(preset)
    return preset


async def delete_preset(db: AsyncSession, preset_id: UUID, user_id: UUID) -> bool:
    result = await db.execute(select(Preset).where(Preset.id == preset_id, Preset.user_id == user_id))
    preset = result.scalar_one_or_none()
    if preset is None:
        return False

    db.delete(preset)
    await db.commit()
    return True
