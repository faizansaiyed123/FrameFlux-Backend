# app/features/media/service.py

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.features.media.models import Media

settings = get_settings()


ALLOWED_MEDIA_TYPES = {
    "video": {
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-matroska",
    },
    "audio": {
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/mp4",
        "audio/aac",
    },
    "image": {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    },
    "subtitle": {
        "text/vtt",
        "application/x-subrip",
        "text/plain",
    },
}


def detect_media_type(content_type: str | None) -> str:
    if not content_type:
        raise ValueError("Missing content type")

    for media_type, mime_types in ALLOWED_MEDIA_TYPES.items():
        if content_type in mime_types:
            return media_type

    raise ValueError(f"Unsupported media type: {content_type}")


async def save_upload(file: UploadFile) -> Media:
    media_type = detect_media_type(file.content_type)

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(file.filename or "").suffix
    stored_filename = f"{uuid4()}{extension}"

    destination = upload_dir / stored_filename

    file_size = 0

    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)
            file_size += len(chunk)

    return Media(
        original_filename=file.filename or "unknown",
        stored_filename=stored_filename,
        media_type=media_type,
        mime_type=file.content_type or "application/octet-stream",
        file_size=file_size,
    )
