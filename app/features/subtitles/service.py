import ffmpeg
from pathlib import Path
from typing import Any


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def burn_subtitles_into_video(
    input_path: str,
    subtitle_path: str,
    media_id: str,
    font_size: int = 24,
    font_color: str = "white",
    background_color: str = "black@0.5",
    position: str = "bottom",
    font: str | None = None,
    alignment: str | None = None,
) -> str:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(subtitle_path).exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    style = f"FontSize={font_size},PrimaryColour={font_color},OutlineColour=black,Outline=2,BackColour={background_color}"
    if font:
        style += f",FontName={font}"
    if alignment:
        style += f",Alignment={alignment}"

    vf = f"subtitles={subtitle_path}:force_style='{style}'"
    output_filename = f"{media_id}_subtitled_{Path(input_path).stem}.mp4"
    output_path = Path(input_path).parent / output_filename
    (
        ffmpeg.input(input_path)
        .output(str(output_path), vf=vf, vcodec="libx264", acodec="aac", movflags="+faststart")
        .overwrite_output()
        .run()
    )
    return str(output_path.relative_to(Path(input_path).parent.parent))


def extract_subtitle_track(input_path: str, stream_index: int = 0) -> list[dict[str, Any]]:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    probe = ffmpeg.probe(input_path)
    subtitle_streams = [
        s for s in probe.get("streams", [])
        if s.get("codec_type") == "subtitle"
    ]
    if not subtitle_streams:
        return []

    if stream_index >= len(subtitle_streams):
        raise ValueError(f"Subtitle stream index {stream_index} out of range")

    stream = subtitle_streams[stream_index]
    return [
        {
            "id": stream.get("index", stream_index),
            "codec": stream.get("codec_name"),
            "language": stream.get("tags", {}).get("language", "und"),
            "title": stream.get("tags", {}).get("title", ""),
            "is_default": stream.get("disposition", {}).get("default", 0) == 1,
            "is_forced": stream.get("disposition", {}).get("forced", 0) == 1,
        }
    ]


def mux_soft_subtitles(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    language: str = "und",
    is_default: bool = False,
    is_forced: bool = False,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(subtitle_path).exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    disposition = []
    if is_default:
        disposition.append("default")
    if is_forced:
        disposition.append("forced")
    disposition_str = "+".join(disposition) if disposition else "0"

    (
        ffmpeg.input(input_path)
        .output(
            str(output_path),
            **{
                "i": str(subtitle_path),
                "c": "copy",
                "c:s": "mov_text",
                "metadata:s:s:0": f"language={language}",
                "disposition:s:s:0": disposition_str,
            }
        )
        .overwrite_output()
        .run()
    )
