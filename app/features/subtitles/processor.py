import ffmpeg
from pathlib import Path


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def burn_subtitles(input_path: str, subtitle_path: str, output_path: str, font_size: int = 24, font_color: str = "white", background_color: str = "black@0.5") -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(subtitle_path).exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    vf = (
        f"subtitles={subtitle_path}:force_style='FontSize={font_size},PrimaryColour={font_color},OutlineColour=black,Outline=2,"
        f"BackColour={background_color}'"
    )
    (
        ffmpeg.input(input_path)
        .output(output_path, vf=vf, vcodec="libx264", acodec="aac", movflags="+faststart")
        .overwrite_output()
        .run()
    )


def extract_subtitle_track(input_path: str, output_path: str, stream_index: int = 0) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    probe = ffmpeg.probe(input_path)
    subtitle_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "subtitle"]
    if not subtitle_streams:
        raise ValueError("No subtitle tracks found")
    if stream_index >= len(subtitle_streams):
        raise ValueError(f"Subtitle stream index {stream_index} out of range")

    (
        ffmpeg.input(input_path)
        .output(output_path, map=f"0:s:{stream_index}")
        .overwrite_output()
        .run()
    )
