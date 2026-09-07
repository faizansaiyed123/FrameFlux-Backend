from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings
from app.features.media.models import Media

settings = get_settings()


async def save_upload(file: UploadFile) -> Media:
    if not file.filename:
        raise ValueError("Filename is required")

    extension = Path(file.filename).suffix.lower()

    allowed_extensions = {
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

    if extension not in allowed_extensions:
        raise ValueError(f"Unsupported file type: {extension}")

    media_type = get_media_type(extension)

    stored_filename = f"{uuid4()}{extension}"
    destination = Path(settings.upload_dir) / stored_filename

    destination.parent.mkdir(parents=True, exist_ok=True)

    file_size = 0

    with destination.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)
            file_size += len(chunk)

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
    if extension in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return "video"

    if extension in {".mp3", ".wav", ".m4a"}:
        return "audio"

    if extension in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"

    if extension in {".srt", ".vtt"}:
        return "subtitle"

    raise ValueError("Unsupported media type")
