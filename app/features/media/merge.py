from pathlib import Path

import ffmpeg


def merge_media(
    input_paths: list[str],
    output_path: str,
) -> None:
    if len(input_paths) < 2:
        raise ValueError("At least 2 media files are required")

    for path in input_paths:
        if not Path(path).exists():
            raise FileNotFoundError(f"Media file not found: {path}")

    concat_file = output_path + ".txt"

    try:
        with open(concat_file, "w", encoding="utf-8") as file:
            for path in input_paths:
                safe_path = (
                    Path(path)
                    .resolve()
                    .as_posix()
                    .replace("'", "'\\''")
                )
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
            else "FFmpeg merge failed"
        )
        raise RuntimeError(error) from exc

    finally:
        Path(concat_file).unlink(missing_ok=True)
