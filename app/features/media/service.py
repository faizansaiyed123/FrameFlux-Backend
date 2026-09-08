from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings
from app.features.media.models import Media
from app.shared.constants import (
    ALLOWED_EXTENSIONS,
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from app.shared.validators import (
    validate_file_content,
    validate_filename_and_extension,
    validate_mime_type,
)

settings = get_settings()

CHUNK_SIZE = 1024 * 1024  # 1 MB


async def save_upload(file: UploadFile) -> Media:
    settings = get_settings()
    max_size = settings.max_upload_size_bytes

    extension = validate_filename_and_extension(file.filename)
    mime_type = validate_mime_type(file.content_type, extension)
    media_type = get_media_type(extension)

    # Check reported size if provided
    if file.size is not None and file.size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size exceeds maximum allowed limit of {max_size} bytes",
        )

    stored_filename = f"{uuid4()}{extension}"
    destination = Path(settings.upload_dir) / stored_filename

    destination.parent.mkdir(parents=True, exist_ok=True)

    file_size = 0
    header_checked = False

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(CHUNK_SIZE):
                if not header_checked:
                    validate_file_content(chunk, extension)
                    header_checked = True

                output.write(chunk)
                file_size += len(chunk)

                if file_size > max_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File size exceeds maximum allowed limit of {max_size} bytes",
                    )
    except Exception:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        await file.close()

    if file_size == 0:
        if destination.exists():
            destination.unlink()
        raise ValueError("Uploaded file is empty")

    return Media(
        original_filename=file.filename,
        stored_filename=stored_filename,
        media_type=media_type,
        mime_type=mime_type,
        file_size=file_size,
        processing_status="pending",
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
