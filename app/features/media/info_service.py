import ffmpeg
from pathlib import Path
from typing import Any
from app.features.media.processor import get_uploaded_file
from app.infrastructure.ffmpeg import probe_media


async def get_media_info(stored_filename: str) -> dict[str, Any]:
    input_path = get_uploaded_file(stored_filename)
    if not input_path.exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    probe = await probe_media(str(input_path))
    format_info = probe.get("format", {})
    streams = probe.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    width = video_stream.get("width") if video_stream else None
    height = video_stream.get("height") if video_stream else None
    resolution = f"{width}x{height}" if width and height else None

    bitrate = format_info.get("bit_rate")
    if bitrate:
        bitrate_str = f"{int(bitrate) // 1000}kbps"
    else:
        bitrate_str = None

    metadata = {
        "format": format_info.get("format_name"),
        "duration": format_info.get("duration"),
        "size": format_info.get("size"),
        "bit_rate": bitrate_str,
        "tags": format_info.get("tags", {}),
    }

    creation_metadata = {
        "creation_time": format_info.get("tags", {}).get("creation_time"),
        "encoder": format_info.get("tags", {}).get("encoder"),
        "software": format_info.get("tags", {}).get("software"),
    }

    return {
        "file_name": Path(input_path).name,
        "file_size": int(format_info.get("size", 0)),
        "duration": float(format_info.get("duration", 0)) if format_info.get("duration") else None,
        "resolution": resolution,
        "fps": video_stream.get("r_frame_rate") if video_stream else None,
        "video_codec": video_stream.get("codec_name") if video_stream else None,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "bitrate": bitrate_str,
        "audio_channels": audio_stream.get("channels") if audio_stream else None,
        "sample_rate": int(audio_stream.get("sample_rate")) if audio_stream and audio_stream.get("sample_rate") else None,
        "container_format": format_info.get("format_name"),
        "audio_tracks": sum(1 for s in streams if s.get("codec_type") == "audio"),
        "subtitle_tracks": len(subtitle_streams),
        "available_streams": [
            {
                "index": s.get("index"),
                "codec_type": s.get("codec_type"),
                "codec_name": s.get("codec_name"),
                "language": s.get("tags", {}).get("language", "und"),
            }
            for s in streams
        ],
        "metadata": metadata,
        "creation_metadata": creation_metadata,
    }
