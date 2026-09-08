# app/features/media/processor.py

from pathlib import Path
from uuid import UUID

from app.core.config import get_settings
from app.infrastructure.ffmpeg import convert_to_mp4

settings = get_settings()


def get_uploaded_file(filename: str) -> Path:
    return Path(settings.upload_dir) / filename


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
