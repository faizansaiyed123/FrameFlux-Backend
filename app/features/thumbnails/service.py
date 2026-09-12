from pathlib import Path

from app.core.config import get_settings
from app.features.thumbnails.processor import generate_thumbnail, generate_thumbnails_interval

settings = get_settings()


async def create_thumbnail(input_path: str, media_id: str, timestamp: float | None = None, width: int | None = None, fmt: str = "jpg") -> str:
    output_dir = Path(settings.processed_dir) / "thumbnails" / str(media_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{int(timestamp)}s" if timestamp is not None else "_auto"
    width_suffix = f"_{width}w" if width else ""
    output_filename = f"thumb{suffix}{width_suffix}.{fmt}"
    output_path = output_dir / output_filename
    generate_thumbnail(input_path, str(output_path), timestamp=timestamp, width=width)
    return str(output_path.relative_to(Path(settings.processed_dir)))


async def create_thumbnail_set(input_path: str, media_id: str, interval: float = 5.0, width: int | None = None, fmt: str = "jpg") -> list[str]:
    output_dir = Path(settings.processed_dir) / "thumbnails" / str(media_id) / "set"
    output_dir.mkdir(parents=True, exist_ok=True)
    width_suffix = f"_{width}w" if width else ""
    output_dir_final = output_dir / f"set{width_suffix}"
    output_dir_final.mkdir(parents=True, exist_ok=True)
    files = generate_thumbnails_interval(input_path, str(output_dir_final), interval=interval, width=width)
    return [str(Path(f).relative_to(Path(settings.processed_dir))) for f in files]
