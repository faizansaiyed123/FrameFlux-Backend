from pathlib import Path

import ffmpeg


def apply_video_adjustments(
    input_path: str,
    output_path: str,
    brightness: float | None = None,
    contrast: float | None = None,
    saturation: float | None = None,
    gamma: float | None = None,
    hue: float | None = None,
) -> None:
    filters = []
    if brightness is not None:
        filters.append(f"eq=brightness={brightness}")
    if contrast is not None:
        filters.append(f"eq=contrast={contrast}")
    if saturation is not None:
        filters.append(f"eq=saturation={saturation}")
    if gamma is not None:
        filters.append(f"eq=gamma={gamma}")
    if hue is not None:
        filters.append(f"hue=h={hue}")

    vf = ",".join(filters) if filters else None
    if vf:
        (
            ffmpeg.input(input_path)
            .output(
                output_path,
                vf=vf,
                vcodec="libx264",
                acodec="aac",
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )
    else:
        (
            ffmpeg.input(input_path)
            .output(
                output_path,
                vcodec="copy",
                acodec="copy",
            )
            .overwrite_output()
            .run()
        )


def apply_video_filter(
    input_path: str,
    output_path: str,
    operation: str,
    intensity: float = 1.0,
) -> None:
    if operation == "sharpen":
        vf = f"unsharp=5:5:{intensity}:5:5:0.0"
    elif operation == "blur":
        vf = f"boxblur={intensity}:{intensity}"
    else:
        raise ValueError(f"Unsupported filter operation: {operation}")

    (
        ffmpeg.input(input_path)
        .output(
            output_path,
            vf=vf,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
        .overwrite_output()
        .run()
    )


def apply_fade(
    input_path: str,
    output_path: str,
    fade_type: str,
    duration: float,
    start_time: float = 0.0,
) -> None:
    if fade_type not in {"in", "out"}:
        raise ValueError("fade_type must be 'in' or 'out'")

    if fade_type == "in":
        vf = f"fade=t=in:st={start_time}:d={duration}"
    else:
        vf = f"fade=t=out:st={start_time}:d={duration}"

    (
        ffmpeg.input(input_path)
        .output(
            output_path,
            vf=vf,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
        .overwrite_output()
        .run()
    )


def reverse_video(input_path: str, output_path: str) -> None:
    (
        ffmpeg.input(input_path)
        .output(
            output_path,
            vf="reverse",
            af="areverse",
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
        .overwrite_output()
        .run()
    )
