from pathlib import Path

from app.core.config import get_settings
from app.features.video.processor import (
    apply_fade,
    apply_video_adjustments,
    apply_video_filter,
    reverse_video,
)

settings = get_settings()


def _output_path(media_id: str, suffix: str, extension: str = "mp4") -> Path:
    return Path(settings.processed_dir) / f"{media_id}_{suffix}.{extension}"


def adjust_video(
    media_id: str,
    input_path: str,
    brightness: float | None = None,
    contrast: float | None = None,
    saturation: float | None = None,
    gamma: float | None = None,
    hue: float | None = None,
) -> str:
    output_path = _output_path(media_id, "adjusted")
    apply_video_adjustments(
        str(input_path),
        str(output_path),
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        gamma=gamma,
        hue=hue,
    )
    return output_path.name


def filter_video(
    media_id: str,
    input_path: str,
    operation: str,
    intensity: float = 1.0,
) -> str:
    output_path = _output_path(media_id, f"filter_{operation}")
    apply_video_filter(
        str(input_path),
        str(output_path),
        operation=operation,
        intensity=intensity,
    )
    return output_path.name


def fade_video(
    media_id: str,
    input_path: str,
    fade_type: str,
    duration: float,
    start_time: float = 0.0,
) -> str:
    output_path = _output_path(media_id, f"fade_{fade_type}")
    apply_fade(
        str(input_path),
        str(output_path),
        fade_type=fade_type,
        duration=duration,
        start_time=start_time,
    )
    return output_path.name


def reverse_media(media_id: str, input_path: str) -> str:
    output_path = _output_path(media_id, "reversed")
    reverse_video(str(input_path), str(output_path))
    return output_path.name
