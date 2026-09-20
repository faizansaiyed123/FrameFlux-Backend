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

    video_input = ffmpeg.input(input_path)
    subtitle_input = ffmpeg.input(subtitle_path)
    (
        ffmpeg
        .output(
            video_input.video,
            video_input.audio,
            subtitle_input['s'],
            str(output_path),
            vcodec="copy",
            acodec="copy",
            scodec="mov_text",
            **{
                "metadata:s:s:0": f"language={language}",
                "disposition:s:s:0": disposition_str,
            },
        )
        .overwrite_output()
        .run()
    )


def shift_subtitle_timestamps(subtitle_path: str, output_path: str, offset_seconds: float) -> None:
    """Shift SRT/VTT/ASS cue timestamps by offset_seconds, clamping at zero."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    text = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()

    def clamp(value: float) -> float:
        return max(0.0, value + offset_seconds)

    def srt_vtt_time(match: re.Match[str]) -> str:
        raw = match.group(0)
        separator = "," if "," in raw else "."
        h, m, rest = raw.replace(",", ".").split(":")
        seconds = float(rest)
        total = int(h) * 3600 + int(m) * 60 + seconds
        shifted = clamp(total)
        sh = int(shifted // 3600)
        sm = int((shifted % 3600) // 60)
        ss = shifted % 60
        return f"{sh:02d}:{sm:02d}:{ss:06.3f}".replace(".", separator)

    def ass_time(match: re.Match[str]) -> str:
        raw = match.group(0)
        h, m, s = raw.split(":")
        total = int(h) * 3600 + int(m) * 60 + float(s)
        shifted = clamp(total)
        sh = int(shifted // 3600)
        sm = int((shifted % 3600) // 60)
        ss = shifted % 60
        return f"{sh}:{sm:02d}:{ss:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        pattern = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}")
        transformed = pattern.sub(srt_vtt_time, text)
    elif extension == ".ass":
        lines = []
        for line in text.splitlines(keepends=True):
            if line.startswith("Dialogue:"):
                parts = line.rstrip("\r\n").split(",")
                if len(parts) >= 3:
                    parts[1] = ass_time(re.fullmatch(r"\d+:\d{2}:\d{2}\.\d{2}", parts[1].strip()) or re.match(r"\d+:\d{2}:\d{2}\.\d{2}", parts[1].strip()))
                    parts[2] = ass_time(re.fullmatch(r"\d+:\d{2}:\d{2}\.\d{2}", parts[2].strip()) or re.match(r"\d+:\d{2}:\d{2}\.\d{2}", parts[2].strip()))
                    line = ",".join(parts) + ("\n" if line.endswith("\n") else "")
            lines.append(line)
        transformed = "".join(lines)
    else:
        raise ValueError(f"Unsupported subtitle format for timestamp shifting: {extension}")

    Path(output_path).write_text(transformed, encoding="utf-8")
