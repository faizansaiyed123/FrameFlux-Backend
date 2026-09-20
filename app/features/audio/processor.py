import ffmpeg
from pathlib import Path
from typing import Optional


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def sync_audio_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    audio_offset: float = 0.0,
    video_duration: Optional[float] = None,
    audio_duration: Optional[float] = None,
    fade_in: float | None = None,
    fade_out: float | None = None,
    volume: float = 1.0,
    mix: bool = False,
    mix_volume: float = 0.5,
) -> None:
    """
    Sync external audio with video.
    
    Args:
        video_path: Path to input video
        audio_path: Path to external audio file
        output_path: Path for output video
        audio_offset: Audio offset in seconds (positive = delay audio, negative = advance audio)
        video_duration: Optional video duration to limit output
        audio_duration: Optional audio duration to limit output
        fade_in: Fade in duration for external audio
        fade_out: Fade out duration for external audio
        volume: Volume multiplier for external audio
        mix: If True, mix external audio with original video audio
        mix_volume: Volume of original audio when mixing (0-1)
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    video = ffmpeg.input(video_path)
    audio = ffmpeg.input(audio_path)

    # Apply offset to audio
    if audio_offset != 0:
        if audio_offset > 0:
            # Delay audio: add silence at start
            silence = ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi", t=audio_offset)
            audio = ffmpeg.concat(silence, audio, v=0, a=1)
        else:
            # Advance audio: trim from start
            audio = audio.filter("atrim", start=-audio_offset)

    # Apply duration limits
    if audio_duration:
        audio = audio.filter("atrim", duration=audio_duration)

    # Apply volume to external audio
    audio = audio.filter("volume", volume)

    # Apply fade in/out to external audio
    if fade_in:
        audio = audio.filter("afade", t="in", st=0, d=fade_in)
    if fade_out:
        audio = audio.filter("afade", t="out", st=None, d=fade_out)

    if mix:
        # Mix external audio with original video audio
        original_audio = video.audio.filter("volume", mix_volume)
        mixed_audio = ffmpeg.filter([original_audio, audio], "amix", inputs=2, duration="longest")
        output_audio = mixed_audio
    else:
        # Replace video audio entirely
        output_audio = audio

    # Apply video duration limit to the video stream itself. Reset timestamps so
    # downstream muxing remains valid when the requested duration is shorter.
    video_stream = video.video
    if video_duration:
        video_stream = video_stream.filter("trim", duration=video_duration).filter("setpts", "PTS-STARTPTS")

    _run(
        ffmpeg.output(video_stream, output_audio, output_path, vcodec="libx264", acodec="aac", movflags="+faststart", shortest=None)
        .overwrite_output()
    )


def convert_audio(
    input_path: str,
    output_path: str,
    format: str = "mp3",
    bitrate: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    quality: str | None = None,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")

    codec_map = {
        "mp3": "libmp3lame",
        "wav": "pcm_s16le",
        "aac": "aac",
        "flac": "flac",
        "ogg": "libvorbis",
        "m4a": "aac",
        "opus": "libopus",
        "aiff": "pcm_s16be",
        "wma": "wmav2",
    }
    acodec = codec_map.get(format)
    if not acodec:
        raise ValueError(f"Unsupported audio format: {format}")

    kwargs: dict = {"acodec": acodec, "vn": None}
    if bitrate:
        kwargs["audio_bitrate"] = bitrate
    if sample_rate:
        kwargs["ar"] = sample_rate
    if channels:
        kwargs["ac"] = channels
    if quality:
        q_map = {"low": 5, "medium": 2, "high": 0}
        if format == "mp3":
            kwargs["qscale"] = q_map.get(quality, 2)

    _run(ffmpeg.input(input_path).output(output_path, **kwargs))


def trim_audio(input_path: str, output_path: str, start: float, end: float) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    if end <= start:
        raise ValueError("End time must be greater than start time")
    _run(
        ffmpeg.input(input_path, ss=start, to=end)
        .output(output_path, acodec="copy")
        .overwrite_output()
    )


def cut_audio(input_path: str, output_path: str, start: float, end: float) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    if end <= start:
        raise ValueError("End time must be greater than start time")
    _run(
        ffmpeg.input(input_path, ss=start, to=end)
        .output(output_path, acodec="copy")
        .overwrite_output()
    )


def split_audio(input_path: str, output_dir: str, start: float, end: float) -> list[str]:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    if end <= start:
        raise ValueError("End time must be greater than start time")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(output_dir) / "split.mp3")
    _run(
        ffmpeg.input(input_path, ss=start, to=end)
        .output(output_path, acodec="libmp3lame")
        .overwrite_output()
    )
    return [output_path]


def merge_audio(input_files: list[str], output_path: str) -> None:
    for f in input_files:
        if not Path(f).exists():
            raise FileNotFoundError(f"Audio file not found: {f}")
    inputs = [ffmpeg.input(f) for f in input_files]
    _run(
        ffmpeg.concat(*inputs, v=0, a=1)
        .output(output_path, acodec="libmp3lame")
        .overwrite_output()
    )


def change_audio_speed(input_path: str, output_path: str, speed: float) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    if speed <= 0:
        raise ValueError("Speed must be greater than 0")
    _run(
        ffmpeg.input(input_path)
        .output(output_path, filter="atempo={}".format(speed), acodec="libmp3lame")
        .overwrite_output()
    )


def normalize_audio(input_path: str, output_path: str) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    _run(
        ffmpeg.input(input_path)
        .output(output_path, filter="loudnorm", acodec="libmp3lame")
        .overwrite_output()
    )


def apply_fade(
    input_path: str,
    output_path: str,
    fade_in: float | None = None,
    fade_out: float | None = None,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    stream = ffmpeg.input(input_path)
    kwargs: dict = {"acodec": "libmp3lame"}
    if fade_in:
        stream = stream.filter("afade", t="in", st=0, d=fade_in)
    if fade_out:
        # Let FFmpeg derive the start time from the stream duration by using no explicit `st`.
        stream = stream.filter("afade", t="out", d=fade_out)
    _run(stream.output(output_path, **kwargs).overwrite_output())


def add_silence(input_path: str, output_path: str, silence_duration: float, position: str = "end") -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Audio file not found: {input_path}")
    if silence_duration <= 0:
        raise ValueError("Silence duration must be greater than 0")
    silence = ffmpeg.input("anullsrc=r=44100:cl=stereo", f="lavfi", t=silence_duration)
    if position == "start":
        _run(
            ffmpeg.concat(silence, ffmpeg.input(input_path), v=0, a=1)
            .output(output_path, acodec="libmp3lame")
            .overwrite_output()
        )
    else:
        _run(
            ffmpeg.concat(ffmpeg.input(input_path), silence, v=0, a=1)
            .output(output_path, acodec="libmp3lame")
            .overwrite_output()
        )


def create_video_from_audio(
    audio_path: str,
    output_path: str,
    background_image: str | None = None,
    background_color: str = "#000000",
    title: str | None = None,
    text: str | None = None,
    watermark: str | None = None,
    show_waveform: bool = False,
    visualizer_style: str | None = None,
    resolution: str = "1920x1080",
    fps: int = 30,
    aspect_ratio: str = "16:9",
    duration: float | None = None,
    output_format: str = "mp4",
) -> None:
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    width, height = map(int, resolution.split("x"))
    vcodec = "libx264" if output_format == "mp4" else "libvpx-vp9"
    acodec = "aac" if output_format == "mp4" else "libopus"

    if background_image:
        bg = ffmpeg.input(background_image, loop=1, framerate=fps)
        video = bg.filter("scale", width, height).filter("fps", fps=fps)
    else:
        video = ffmpeg.input(
            "color=c={}:s={}x{}:r={}".format(background_color.lstrip("#"), width, height, fps),
            f="lavfi",
        )

    audio = ffmpeg.input(audio_path)

    if duration:
        video = video.filter("trim", duration=duration)

    overlay_expr = []
    if title:
        overlay_expr.append(f"drawtext=text='{title}':fontcolor=white:fontsize=24:x=(w-text_w)/2:y=h-50")
    if text:
        overlay_expr.append(f"drawtext=text='{text}':fontcolor=white:fontsize=18:x=(w-text_w)/2:y=h-100")
    if watermark and Path(watermark).exists():
        video = ffmpeg.overlay(video, ffmpeg.input(watermark))

    if show_waveform and visualizer_style:
        video = video.filter("showwaves", mode=visualizer_style, rate=30)

    if overlay_expr:
        video = video.filter(",".join(overlay_expr))

    _run(
        ffmpeg.output(video, audio, output_path, vcodec=vcodec, acodec=acodec, shortest=True, pix_fmt="yuv420p")
        .overwrite_output()
    )
