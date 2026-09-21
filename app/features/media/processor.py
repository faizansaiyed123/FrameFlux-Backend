# app/features/media/processor.py

from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.infrastructure.ffmpeg import convert_to_mp4

settings = get_settings()


def get_uploaded_file(filename: str) -> Path:
    """Resolve a stored filename strictly inside the configured upload directory."""
    if not filename or not isinstance(filename, str):
        raise ValueError("Media filename is required")

    storage_dir = Path(settings.upload_dir).resolve()
    candidate = (storage_dir / filename).resolve()
    try:
        candidate.relative_to(storage_dir)
    except ValueError as exc:
        raise ValueError("Invalid media filename") from exc
    return candidate


def process_media(media_id: UUID, stored_filename: str) -> str:
    input_path = get_uploaded_file(stored_filename)

    if not input_path.exists():
        raise FileNotFoundError("Media file not found")

    output_filename = f"{media_id}_processed.mp4"
    output_path = get_uploaded_file(output_filename)

    convert_to_mp4(
        str(input_path),
        str(output_path),
    )

    return output_filename
