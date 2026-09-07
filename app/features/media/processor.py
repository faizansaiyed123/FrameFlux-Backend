# app/features/media/processor.py

from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


def get_uploaded_file(filename: str) -> Path:
    return Path(settings.upload_dir) / filename
