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


def _has_audio(input_path: str) -> bool:
    try:
        probe = ffmpeg.probe(input_path)
        return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))
    except Exception:
        return False


def trim_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if start < 0:
        raise ValueError("Start time must be >= 0")
    if end <= start:
        raise ValueError("End time must be greater than start time")

    stream = ffmpeg.input(input_path)
    v = stream.video.filter("trim", start=start, end=end).filter("setpts", "PTS-STARTPTS")
    if _has_audio(input_path):
        a = stream.audio.filter("atrim", start=start, end=end).filter("asetpts", "PTS-STARTPTS")
        output = ffmpeg.output(
            v,
            a,
            output_path,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
    else:
        output = ffmpeg.output(
            v,
            output_path,
            vcodec="libx264",
            movflags="+faststart",
        )
    _run(output)


def extract_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    trim_media(input_path, output_path, start, end)


def cut_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if start < 0:
        raise ValueError("Start time must be >= 0")
    if end <= start:
        raise ValueError("End time must be greater than start time")

    probe = ffmpeg.probe(input_path)
    total_duration = float(probe["format"].get("duration", 0))
    if end > total_duration:
        end = total_duration

    segments = []
    if start > 0:
        segments.append((0.0, start))
    if end < total_duration:
        segments.append((end, total_duration))

    if not segments:
        raise ValueError("Cut range covers the entire video duration")

    if len(segments) == 1:
        seg_start, seg_end = segments[0]
        trim_media(input_path, output_path, seg_start, seg_end)
        return

    keep_selected_clips(input_path, output_path, segments)


def split_media(
    input_path: str,
    split_points: list[float],
    output_paths: list[str],
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not split_points:
        raise ValueError("At least one split point is required")

    sorted_points = sorted(split_points)
    for p in sorted_points:
        if p <= 0:
            raise ValueError("Split points must be greater than 0")

    probe = ffmpeg.probe(input_path)
    total_duration = float(probe["format"].get("duration", 0))

    intervals = []
    prev = 0.0
    for pt in sorted_points:
        if pt >= total_duration:
            break
        if pt > prev:
            intervals.append((prev, pt))
            prev = pt
    if prev < total_duration:
        intervals.append((prev, total_duration))

    if len(intervals) != len(output_paths):
        raise ValueError(
            f"Expected {len(intervals)} output paths for {len(intervals)} clips, got {len(output_paths)}"
        )

    for (st, en), out_p in zip(intervals, output_paths):
        trim_media(input_path, out_p, st, en)


def keep_selected_clips(
    input_path: str,
    output_path: str,
    clips: list[tuple[float, float]],
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not clips:
        raise ValueError("At least one clip interval is required")

    valid_clips = []
    for st, en in clips:
        if st < 0:
            raise ValueError("Clip start must be >= 0")
        if en <= st:
            raise ValueError(f"Clip end ({en}) must be greater than start ({st})")
        valid_clips.append((st, en))

    if len(valid_clips) == 1:
        trim_media(input_path, output_path, valid_clips[0][0], valid_clips[0][1])
        return

    has_audio = _has_audio(input_path)
    stream = ffmpeg.input(input_path)
    v_streams = []
    a_streams = []
    for st, en in valid_clips:
        v_streams.append(
            stream.video.filter("trim", start=st, end=en).filter("setpts", "PTS-STARTPTS")
        )
        if has_audio:
            a_streams.append(
                stream.audio.filter("atrim", start=st, end=en).filter("asetpts", "PTS-STARTPTS")
            )

    if has_audio:
        concat_inputs = []
        for v, a in zip(v_streams, a_streams):
            concat_inputs.extend([v, a])
        joined = ffmpeg.concat(*concat_inputs, v=1, a=1).node
        output = ffmpeg.output(
            joined[0],
            joined[1],
            output_path,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
    else:
        joined = ffmpeg.concat(*v_streams, v=1, a=0).node
        output = ffmpeg.output(
            joined[0],
            output_path,
            vcodec="libx264",
            movflags="+faststart",
        )
    _run(output)


def delete_selected_clips(
    input_path: str,
    output_path: str,
    clips: list[tuple[float, float]],
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not clips:
        raise ValueError("At least one clip to delete is required")

    probe = ffmpeg.probe(input_path)
    total_duration = float(probe["format"].get("duration", 0))

    sorted_deletions = sorted(clips, key=lambda x: x[0])
    merged = []
    for st, en in sorted_deletions:
        if st < 0:
            raise ValueError("Clip start must be >= 0")
        if en <= st:
            raise ValueError(f"Clip end ({en}) must be greater than start ({st})")
        en = min(en, total_duration)
        if not merged:
            merged.append([st, en])
        else:
            if st <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], en)
            else:
                merged.append([st, en])

    kept_clips = []
    curr = 0.0
    for d_start, d_end in merged:
        if d_start > curr:
            kept_clips.append((curr, d_start))
        curr = max(curr, d_end)
    if curr < total_duration:
        kept_clips.append((curr, total_duration))

    if not kept_clips:
        raise ValueError("Selected deletions cover the entire video duration")

    keep_selected_clips(input_path, output_path, kept_clips)


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


def _get_system_font() -> str | None:
    candidate_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for font in candidate_fonts:
        if Path(font).exists():
            return font
    return None


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

    font_path = _get_system_font()

    drawtext_kwargs = {
        "text": text,
        "x": x,
        "y": y,
        "fontsize": font_size,
        "fontcolor": "white",
        "box": 1,
        "boxcolor": "black@0.65",
        "boxborderw": 12,
    }
    if font_path:
        drawtext_kwargs["fontfile"] = font_path

    stream = ffmpeg.input(input_path)
    video = stream.video.filter(
        "drawtext",
        **drawtext_kwargs,
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


def apply_multiple_overlays(
    input_path: str,
    output_path: str,
    overlays: list[dict],
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not overlays:
        raise ValueError("At least one overlay is required")

    font_path = _get_system_font()
    stream = ffmpeg.input(input_path)
    video = stream.video

    for item in overlays:
        op = item.get("operation")
        x = item.get("x", 10)
        y = item.get("y", 10)

        if op == "text":
            text = item.get("text")
            if not text:
                raise ValueError("Text is required for text overlay")
            font_size = item.get("font_size", 32)
            drawtext_kwargs = {
                "text": text,
                "x": x,
                "y": y,
                "fontsize": font_size,
                "fontcolor": "white",
                "box": 1,
                "boxcolor": "black@0.65",
                "boxborderw": 12,
            }
            if font_path:
                drawtext_kwargs["fontfile"] = font_path
            video = video.filter("drawtext", **drawtext_kwargs)

        elif op in ("image", "watermark"):
            img_path = item.get("image_path")
            if not img_path or not Path(img_path).exists():
                raise FileNotFoundError(f"Overlay image file not found: {img_path}")
            opacity = item.get("opacity", 1.0)
            overlay_stream = ffmpeg.input(img_path)
            overlay_video = overlay_stream.video.filter("format", "rgba")
            if opacity < 1.0:
                overlay_video = overlay_video.filter("colorchannelmixer", aa=opacity)
            video = ffmpeg.overlay(video, overlay_video, x=x, y=y)

        else:
            raise ValueError(f"Unsupported overlay operation: {op}")

    if _has_audio(input_path):
        output = ffmpeg.output(
            video,
            stream.audio,
            output_path,
            vcodec="libx264",
            acodec="aac",
            movflags="+faststart",
        )
    else:
        output = ffmpeg.output(
            video,
            output_path,
            vcodec="libx264",
            movflags="+faststart",
        )
    _run(output)
