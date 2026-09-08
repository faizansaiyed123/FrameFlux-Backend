import asyncio
import json
from pathlib import Path
import ffmpeg


async def probe_media(file_path: str) -> dict:
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(stderr.decode().strip())

    return json.loads(stdout.decode())




def get_video_info(input_path: str) -> dict:
    try:
        probe = ffmpeg.probe(input_path)
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg probe failed"
        raise RuntimeError(error) from exc

    video_stream = next(
        (
            stream
            for stream in probe["streams"]
            if stream.get("codec_type") == "video"
        ),
        None,
    )

    if video_stream is None:
        raise ValueError("No video stream found")

    return {
        "duration": float(probe["format"].get("duration", 0)),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "codec": video_stream.get("codec_name"),
        "fps": video_stream.get("r_frame_rate"),
    }


def convert_to_mp4(input_path: str, output_path: str) -> None:
    try:
        (
            ffmpeg
            .input(input_path)
            .output(
                output_path,
                vcodec="libx264",
                acodec="aac",
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg conversion failed"
        raise RuntimeError(error) from exc