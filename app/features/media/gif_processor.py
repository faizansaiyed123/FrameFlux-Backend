import ffmpeg
from pathlib import Path


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def video_to_gif(input_path: str, output_path: str, start: float = 0, end: float | None = None, duration: float | None = None, width: int = 480, fps: int = 15, quality: int = 10) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    if end is not None:
        duration = end - start
    elif duration is None:
        duration = 5.0

    inp = ffmpeg.input(input_path, ss=start)
    (
        inp
        .output(output_path, t=duration, loop=0, pix_fmt="rgb24", **{"qscale:v": quality}, vf=f"fps={fps},scale={width}:-1:flags=lanczos")
        .overwrite_output()
        .run()
    )


def gif_to_frames(input_path: str, output_dir: str, prefix: str = "frame") -> list[str]:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"GIF file not found: {input_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_pattern = str(Path(output_dir) / f"{prefix}_%04d.png")
    (
        ffmpeg.input(input_path)
        .output(output_pattern)
        .overwrite_output()
        .run()
    )
    return sorted(str(p) for p in Path(output_dir).glob(f"{prefix}_*.png"))
