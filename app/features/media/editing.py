from pathlib import Path

import ffmpeg


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = (
            exc.stderr.decode(errors="replace")
            if exc.stderr
            else "FFmpeg operation failed"
        )
        raise RuntimeError(error) from exc


def transform_media(
    input_path: str,
    output_path: str,
    operation: str,
    width: int | None = None,
    height: int | None = None,
    x: int | None = None,
    y: int | None = None,
    angle: int | None = None,
    speed: float | None = None,
):
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)

    stream = ffmpeg.input(input_path)

    video = stream.video
    audio = stream.audio

    if operation == "crop":
        if width is None or height is None:
            raise ValueError("Crop requires width and height")

        video = video.crop(
            x=x or 0,
            y=y or 0,
            width=width,
            height=height,
        )

    elif operation == "resize":
        if width is None and height is None:
            raise ValueError("Resize requires width or height")

        video = video.filter(
            "scale",
            width or -1,
            height or -1,
        )

    elif operation == "rotate":
        if angle not in {90, 180, 270, -90, -180, -270}:
            raise ValueError(
                "Rotate angle must be 90, 180, 270, -90, -180 or -270"
            )

        normalized = angle % 360

        if normalized == 90:
            video = video.filter("transpose", 1)
        elif normalized == 180:
            video = video.filter("hflip").filter("vflip")
        elif normalized == 270:
            video = video.filter("transpose", 2)

    elif operation == "flip":
        video = video.filter("hflip")

    elif operation == "flop":
        video = video.filter("vflip")

    elif operation == "speed":
        if speed is None:
            raise ValueError("Speed is required")

        if speed <= 0:
            raise ValueError("Speed must be greater than zero")

        video = video.filter(
            "setpts",
            f"{1 / speed}*PTS",
        )

        audio = audio.filter(
            "atempo",
            speed,
        )

    else:
        raise ValueError(f"Unsupported transform: {operation}")

    output = ffmpeg.output(
        video,
        audio,
        output_path,
        vcodec="libx264",
        acodec="aac",
        movflags="+faststart",
    )

    _run(output)


def freeze_frame(
    input_path: str,
    output_path: str,
    timestamp: float,
    duration: float,
):
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)

    if timestamp < 0:
        raise ValueError("Timestamp must be >= 0")

    if duration <= 0:
        raise ValueError("Duration must be > 0")

    stream = ffmpeg.input(input_path)

    video = (
        stream.video
        .filter(
            "tpad",
            start_mode="clone",
            start_duration=duration,
        )
    )

    output = ffmpeg.output(
        video,
        stream.audio,
        output_path,
        vcodec="libx264",
        acodec="aac",
        movflags="+faststart",
    )

    _run(output)


def add_text_overlay(
    input_path: str,
    output_path: str,
    text: str,
    x: int,
    y: int,
    font_size: int,
):
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)

    if not text:
        raise ValueError("Text is required")

    if font_size <= 0:
        raise ValueError("Font size must be greater than 0")

    font_path = r"C:\Windows\Fonts\arial.ttf"

    if not Path(font_path).exists():
        raise FileNotFoundError(
            f"Windows font not found: {font_path}"
        )

    stream = ffmpeg.input(input_path)

    video = stream.video.filter(
        "drawtext",
        fontfile=font_path,
        text=text,
        x=x,
        y=y,
        fontsize=font_size,
        fontcolor="white",
        box=1,
        boxcolor="black@0.65",
        boxborderw=12,
    )

    output = ffmpeg.output(
        video,
        stream.audio,
        output_path,
        vcodec="libx264",
        acodec="aac",
        movflags="+faststart",
    )

    _run(output)

def add_image_overlay(
    input_path: str,
    overlay_path: str,
    output_path: str,
    x: int,
    y: int,
    opacity: float,
):
    if not Path(input_path).exists():
        raise FileNotFoundError(input_path)

    if not Path(overlay_path).exists():
        raise FileNotFoundError(overlay_path)

    main = ffmpeg.input(input_path)
    overlay = ffmpeg.input(overlay_path)

    overlay_video = overlay.video.filter(
        "format",
        "rgba",
    )

    if opacity < 1:
        overlay_video = overlay_video.filter(
            "colorchannelmixer",
            aa=opacity,
        )

    video = ffmpeg.overlay(
        main.video,
        overlay_video,
        x=x,
        y=y,
    )

    output = ffmpeg.output(
        video,
        main.audio,
        output_path,
        vcodec="libx264",
        acodec="aac",
        movflags="+faststart",
    )

    _run(output)


def add_watermark(
    input_path: str,
    watermark_path: str,
    output_path: str,
    x: int,
    y: int,
    opacity: float,
):
    return add_image_overlay(
        input_path,
        watermark_path,
        output_path,
        x,
        y,
        opacity,
    )