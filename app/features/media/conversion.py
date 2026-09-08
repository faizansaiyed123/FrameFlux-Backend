import re
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID

import ffmpeg

SUPPORTED_FORMATS = {
    "mp4": {"vcodec": "libx264", "acodec": "aac", "extension": ".mp4"},
    "webm": {"vcodec": "libvpx-vp9", "acodec": "libopus", "extension": ".webm"},
    "mkv": {"vcodec": "libx264", "acodec": "aac", "extension": ".mkv"},
    "mov": {"vcodec": "libx264", "acodec": "aac", "extension": ".mov"},
    "avi": {"vcodec": "libx264", "acodec": "libmp3lame", "extension": ".avi"},
    "flv": {"vcodec": "libx264", "acodec": "aac", "extension": ".flv"},
    "mpeg": {"vcodec": "mpeg2video", "acodec": "mp2", "extension": ".mpeg"},
    "ts": {"vcodec": "libx264", "acodec": "aac", "extension": ".ts"},
    "m4v": {"vcodec": "libx264", "acodec": "aac", "extension": ".m4v"},
    "3gp": {"vcodec": "h264", "acodec": "aac", "extension": ".3gp"},
}

RESOLUTIONS = {
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
}

CODECS = {
    "h264": "libx264",
    "h265": "libx265",
    "hevc": "libx265",
    "vp8": "libvpx",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
}

AUDIO_CODECS = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "libmp3lame": "libmp3lame",
    "opus": "libopus",
    "libopus": "libopus",
    "vorbis": "libvorbis",
    "libvorbis": "libvorbis",
    "flac": "flac",
    "pcm": "pcm_s16le",
    "wav": "pcm_s16le",
}


def validate_aspect_ratio(ratio: str) -> str:
    """
    Validates arbitrary aspect ratios such as '16:9', '16:10', '2.35:1', '4:3',
    and converts them to integer ratio representation (e.g. 2.35:1 -> 47:20)
    supported by FFmpeg's -aspect parameter.
    """
    if not ratio or not isinstance(ratio, str):
        raise ValueError("Aspect ratio must be a non-empty string")
    ratio = ratio.strip()
    pattern = r"^(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)$"
    match = re.match(pattern, ratio)
    if not match:
        raise ValueError(
            f"Invalid aspect ratio format: '{ratio}'. Expected format like '16:9', '16:10', '2.35:1', or '4:3'"
        )
    num1, num2 = float(match.group(1)), float(match.group(2))
    if num1 <= 0 or num2 <= 0:
        raise ValueError("Aspect ratio values must be greater than zero")

    # If both are integers, keep simple representation (or standard ratio)
    if match.group(1).isdigit() and match.group(2).isdigit():
        return f"{match.group(1)}:{match.group(2)}"

    # If floats are present (e.g. 2.35:1), convert to integer fraction for FFmpeg
    frac = Fraction(num1 / num2).limit_denominator(1000)
    return f"{frac.numerator}:{frac.denominator}"


def convert_media(
    input_path: str,
    output_path: str,
    *,
    output_format: str = "mp4",
    resolution: str | None = None,
    custom_width: int | None = None,
    custom_height: int | None = None,
    fps: float | None = None,
    video_codec: str | None = None,
    quality: int | None = None,
    bitrate: str | None = None,
    aspect_ratio: str | None = None,
    audio_codec: str | None = None,
    audio_bitrate: str | None = None,
) -> None:
    output_format = output_format.lower()
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {output_format}")

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    format_settings = SUPPORTED_FORMATS[output_format]

    # Resolve audio codec
    resolved_acodec = format_settings["acodec"]
    if audio_codec:
        normalized_acodec = audio_codec.lower().strip()
        resolved_acodec = AUDIO_CODECS.get(normalized_acodec, normalized_acodec)

    kwargs: dict[str, Any] = {
        "vcodec": CODECS.get(video_codec, format_settings["vcodec"]),
        "acodec": resolved_acodec,
    }

    if audio_bitrate:
        kwargs["audio_bitrate"] = audio_bitrate

    if quality is not None:
        kwargs["crf"] = quality

    if bitrate:
        kwargs["video_bitrate"] = bitrate

    if fps is not None:
        kwargs["r"] = fps

    if custom_width and custom_height:
        kwargs["vf"] = f"scale={custom_width}:{custom_height}"
    elif resolution:
        if resolution not in RESOLUTIONS:
            raise ValueError(f"Unsupported resolution: {resolution}")
        height = RESOLUTIONS[resolution]
        kwargs["vf"] = f"scale=-2:{height}"

    if aspect_ratio:
        validated_ratio = validate_aspect_ratio(aspect_ratio)
        kwargs["aspect"] = validated_ratio

    if output_format == "mp4":
        kwargs["movflags"] = "+faststart"

    try:
        (
            ffmpeg
            .input(input_path)
            .output(output_path, **kwargs)
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as exc:
        error = (
            exc.stderr.decode(errors="replace")
            if exc.stderr
            else "FFmpeg conversion failed"
        )
        raise RuntimeError(error) from exc
