import ffmpeg
from pathlib import Path


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def generate_thumbnail(input_path: str, output_path: str, timestamp: float | None = None, width: int | None = None, height: int | None = None, fmt: str = "jpg") -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    out_kwargs: dict = {"vframes": 1}
    if fmt == "png":
        out_kwargs["c:v"] = "png"
    elif fmt == "webp":
        out_kwargs["c:v"] = "libwebp"

    vf_parts = []
    if width is not None or height is not None:
        w = width if width is not None else -1
        h = height if height is not None else -1
        vf_parts.append(f"scale={w}:{h}")
    if vf_parts:
        out_kwargs["vf"] = ",".join(vf_parts)

    inp = ffmpeg.input(input_path)
    if timestamp is not None:
        inp = ffmpeg.input(input_path, ss=timestamp)

    (
        inp
        .output(output_path, **out_kwargs)
        .overwrite_output()
        .run()
    )


def generate_thumbnails_interval(input_path: str, output_dir: str, interval: float = 5.0, width: int | None = None, fmt: str = "jpg") -> list[str]:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    probe = ffmpeg.probe(input_path)
    duration = float(probe["format"].get("duration", 0))
    if duration <= 0:
        return []

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if interval <= 0:
        raise ValueError("Thumbnail interval must be greater than zero")

    output_files = []
    index = 0
    timestamp = 0.0
    while timestamp < duration:
        ext = "png" if fmt == "png" else "webp" if fmt == "webp" else "jpg"
        output_file = str(Path(output_dir) / f"thumb_{index:04d}.{ext}")
        generate_thumbnail(input_path, output_file, timestamp=timestamp, width=width, fmt=fmt)
        output_files.append(output_file)
        index += 1
        timestamp += interval
    return output_files


def crop_thumbnail(input_path: str, output_path: str, x: int, y: int, width: int, height: int) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Thumbnail file not found: {input_path}")
    _run(
        ffmpeg.input(input_path)
        .output(output_path, vf=f"crop={width}:{height}:{x}:{y}")
        .overwrite_output()
    )
