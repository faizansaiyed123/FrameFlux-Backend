from pathlib import Path

import ffmpeg


def trim_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError("Media file not found")

    if start < 0:
        raise ValueError("Start time cannot be negative")

    if end <= start:
        raise ValueError("End time must be greater than start time")

    duration = end - start

    try:
        (
            ffmpeg
            .input(input_path, ss=start)
            .output(
                output_path,
                t=duration,
                vcodec="libx264",
                acodec="aac",
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as exc:
        error = (
            exc.stderr.decode(errors="replace")
            if exc.stderr
            else "FFmpeg trim failed"
        )
        raise RuntimeError(error) from exc


def extract_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    trim_media(
        input_path,
        output_path,
        start,
        end,
    )


def cut_media(
    input_path: str,
    output_path: str,
    start: float,
    end: float,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError("Media file not found")

    if start < 0 or end <= start:
        raise ValueError("Invalid cut range")

    try:
        (
            ffmpeg
            .input(input_path)
            .output(
                output_path,
                ss=0,
                to=start,
                vcodec="libx264",
                acodec="aac",
            )
            .overwrite_output()
            .run()
        )

        temp_output = output_path + ".part.mp4"

        (
            ffmpeg
            .input(input_path, ss=end)
            .output(
                temp_output,
                vcodec="libx264",
                acodec="aac",
            )
            .overwrite_output()
            .run()
        )

        from app.infrastructure.ffmpeg import merge_files

        merge_files(
            [output_path, temp_output],
            output_path,
        )

        Path(temp_output).unlink(missing_ok=True)

    except ffmpeg.Error as exc:
        error = (
            exc.stderr.decode(errors="replace")
            if exc.stderr
            else "FFmpeg cut failed"
        )
        raise RuntimeError(error) from exc


def merge_files(
    input_paths: list[str],
    output_path: str,
) -> None:
    concat_file = output_path + ".txt"

    try:
        with open(concat_file, "w", encoding="utf-8") as file:
            for path in input_paths:
                safe_path = Path(path).resolve().as_posix().replace("'", "'\\''")
                file.write(f"file '{safe_path}'\n")

        (
            ffmpeg
            .input(
                concat_file,
                format="concat",
                safe=0,
            )
            .output(
                output_path,
                c="copy",
                movflags="+faststart",
            )
            .overwrite_output()
            .run()
        )

    except ffmpeg.Error as exc:
        error = (
            exc.stderr.decode(errors="replace")
            if exc.stderr
            else "FFmpeg merge failed"
        )
        raise RuntimeError(error) from exc

    finally:
        Path(concat_file).unlink(missing_ok=True)
