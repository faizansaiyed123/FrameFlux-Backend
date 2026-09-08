from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.features.media.models import Media

settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".mp3",
    ".wav",
    ".m4a",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".srt",
    ".vtt",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
}

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

SUBTITLE_EXTENSIONS = {
    ".srt",
    ".vtt",
}

CHUNK_SIZE = 1024 * 1024  # 1 MB


async def save_upload(file: UploadFile) -> Media:
    if not file.filename:
        raise ValueError("Filename is required")

    extension = Path(file.filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {extension or 'unknown'}"
        )

    media_type = get_media_type(extension)

    stored_filename = f"{uuid4()}{extension}"
    destination = Path(settings.upload_dir) / stored_filename

    destination.parent.mkdir(parents=True, exist_ok=True)

    file_size = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(CHUNK_SIZE):
                output.write(chunk)
                file_size += len(chunk)
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        await file.close()

    return Media(
        original_filename=file.filename,
        stored_filename=stored_filename,
        media_type=media_type,
        mime_type=file.content_type or "application/octet-stream",
        file_size=file_size,
    )


async def delete_media_file(stored_filename: str) -> None:
    path = Path(settings.upload_dir) / stored_filename

    if path.exists():
        path.unlink()


def get_media_type(extension: str) -> str:
    if extension in VIDEO_EXTENSIONS:
        return "video"

    if extension in AUDIO_EXTENSIONS:
        return "audio"

    if extension in IMAGE_EXTENSIONS:
        return "image"

    if extension in SUBTITLE_EXTENSIONS:
        return "subtitle"

    raise ValueError(f"Unsupported media type: {extension}")
