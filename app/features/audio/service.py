import ffmpeg
from pathlib import Path


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def extract_audio(input_path: str, output_path: str, format: str = "mp3", bitrate: str | None = None, sample_rate: int | None = None, channels: int | None = None, quality: str | None = None, start: float | None = None, end: float | None = None) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    kwargs: dict = {}
    if format == "mp3":
        kwargs["acodec"] = "libmp3lame"
    elif format == "wav":
        kwargs["acodec"] = "pcm_s16le"
    elif format == "aac":
        kwargs["acodec"] = "aac"
    elif format == "flac":
        kwargs["acodec"] = "flac"
    elif format == "ogg":
        kwargs["acodec"] = "libvorbis"
    elif format == "m4a":
        kwargs["acodec"] = "aac"
    elif format == "opus":
        kwargs["acodec"] = "libopus"
    elif format == "aiff":
        # AIFF commonly uses big-endian PCM. Let the .aiff extension select
        # the AIFF muxer while explicitly using a compatible PCM codec.
        kwargs["acodec"] = "pcm_s16be"
    else:
        raise ValueError(f"Unsupported audio format: {format}")

    if bitrate:
        kwargs["audio_bitrate"] = bitrate
    if sample_rate:
        kwargs["ar"] = sample_rate
    if channels:
        kwargs["ac"] = channels

    codec = kwargs.get("acodec", "libmp3lame")
    other_kwargs = {k: v for k, v in kwargs.items() if k != "acodec"}
    other_kwargs["acodec"] = codec
    (
        ffmpeg.input(input_path)
        .output(output_path, **other_kwargs)
        .overwrite_output()
        .run()
    )


def adjust_volume(input_path: str, output_path: str, volume: float, fade_in: float | None = None, fade_out: float | None = None) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    stream = ffmpeg.input(input_path)
    audio = stream.audio.filter("volume", volume)

    if fade_in:
        audio = audio.filter("afade", t="in", st=0, d=fade_in)
    if fade_out:
        audio = audio.filter("afade", t="out", st=None, d=fade_out)

    output = ffmpeg.output(audio, stream.video, output_path, vcodec="libx264", acodec="aac", movflags="+faststart")
    _run(output)


def replace_audio(input_path: str, audio_path: str, output_path: str, fade_in: float | None = None, fade_out: float | None = None) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(audio_path).exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    video = ffmpeg.input(input_path)
    audio = ffmpeg.input(audio_path)

    if fade_in:
        audio = audio.filter("afade", t="in", st=0, d=fade_in)
    if fade_out:
        probe = ffmpeg.probe(audio_path)
        duration = float(probe.get("format", {}).get("duration", 0) or 0)
        fade_start = max(duration - fade_out, 0)
        audio = audio.filter("afade", t="out", st=fade_start, d=fade_out)

    output = ffmpeg.output(video.video, audio, output_path, vcodec="libx264", acodec="aac", movflags="+faststart", shortest=None)
    _run(output)
