import ffmpeg
from pathlib import Path
from typing import Any


def _run(stream):
    try:
        stream.overwrite_output().run()
    except ffmpeg.Error as exc:
        error = exc.stderr.decode(errors="replace") if exc.stderr else "FFmpeg operation failed"
        raise RuntimeError(error) from exc


def burn_subtitles_into_video(
    input_path: str,
    subtitle_path: str,
    media_id: str,
    font_size: int = 24,
    font_color: str = "white",
    background_color: str = "black@0.5",
    position: str = "bottom",
    font: str | None = None,
    alignment: str | None = None,
) -> str:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(subtitle_path).exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    style = f"FontSize={font_size},PrimaryColour={font_color},OutlineColour=black,Outline=2,BackColour={background_color}"
    if font:
        style += f",FontName={font}"
    if alignment:
        style += f",Alignment={alignment}"

    vf = f"subtitles={subtitle_path}:force_style='{style}'"
    output_filename = f"{media_id}_subtitled_{Path(input_path).stem}.mp4"
    output_path = Path(input_path).parent / output_filename
    (
        ffmpeg.input(input_path)
        .output(str(output_path), vf=vf, vcodec="libx264", acodec="aac", movflags="+faststart")
        .overwrite_output()
        .run()
    )
    return str(output_path.relative_to(Path(input_path).parent.parent))


def extract_subtitle_track(input_path: str, stream_index: int = 0) -> list[dict[str, Any]]:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")

    probe = ffmpeg.probe(input_path)
    subtitle_streams = [
        s for s in probe.get("streams", [])
        if s.get("codec_type") == "subtitle"
    ]
    if not subtitle_streams:
        return []

    if stream_index >= len(subtitle_streams):
        raise ValueError(f"Subtitle stream index {stream_index} out of range")

    stream = subtitle_streams[stream_index]
    return [
        {
            "id": stream.get("index", stream_index),
            "codec": stream.get("codec_name"),
            "language": stream.get("tags", {}).get("language", "und"),
            "title": stream.get("tags", {}).get("title", ""),
            "is_default": stream.get("disposition", {}).get("default", 0) == 1,
            "is_forced": stream.get("disposition", {}).get("forced", 0) == 1,
        }
    ]


def mux_soft_subtitles(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    language: str = "und",
    is_default: bool = False,
    is_forced: bool = False,
) -> None:
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Media file not found: {input_path}")
    if not Path(subtitle_path).exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    disposition = []
    if is_default:
        disposition.append("default")
    if is_forced:
        disposition.append("forced")
    disposition_str = "+".join(disposition) if disposition else "0"

    video_input = ffmpeg.input(input_path)
    subtitle_input = ffmpeg.input(subtitle_path)
    (
        ffmpeg
        .output(
            video_input.video,
            video_input.audio,
            subtitle_input['s'],
            str(output_path),
            vcodec="copy",
            acodec="copy",
            scodec="mov_text",
            **{
                "metadata:s:s:0": f"language={language}",
                "disposition:s:s:0": disposition_str,
            },
        )
        .overwrite_output()
        .run()
    )


def shift_subtitle_timestamps(subtitle_path: str, output_path: str, offset_seconds: float) -> None:
    """Shift SRT/VTT/ASS cue timestamps by offset_seconds, clamping at zero."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")

    text = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()

    def clamp(value: float) -> float:
        return max(0.0, value + offset_seconds)

    def srt_vtt_time(match: re.Match[str]) -> str:
        raw = match.group(0)
        separator = "," if "," in raw else "."
        h, m, rest = raw.replace(",", ".").split(":")
        seconds = float(rest)
        total = int(h) * 3600 + int(m) * 60 + seconds
        shifted = clamp(total)
        sh = int(shifted // 3600)
        sm = int((shifted % 3600) // 60)
        ss = shifted % 60
        return f"{sh:02d}:{sm:02d}:{ss:06.3f}".replace(".", separator)

    def ass_time(match: re.Match[str]) -> str:
        raw = match.group(0)
        h, m, s = raw.split(":")
        total = int(h) * 3600 + int(m) * 60 + float(s)
        shifted = clamp(total)
        sh = int(shifted // 3600)
        sm = int((shifted % 3600) // 60)
        ss = shifted % 60
        return f"{sh}:{sm:02d}:{ss:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        pattern = re.compile(r"\d{2}:\d{2}:\d{2}[,.]\d{3}")
        transformed = pattern.sub(srt_vtt_time, text)
    elif extension == ".ass":
        lines = []
        for line in text.splitlines(keepends=True):
            if line.startswith("Dialogue:"):
                parts = line.rstrip("\r\n").split(",")
                if len(parts) >= 3:
                    parts[1] = ass_time(re.fullmatch(r"\d+:\d{2}:\d{2}\.\d{2}", parts[1].strip()) or re.match(r"\d+:\d{2}:\d{2}\.\d{2}", parts[1].strip()))
                    parts[2] = ass_time(re.fullmatch(r"\d+:\d{2}:\d{2}\.\d{2}", parts[2].strip()) or re.match(r"\d+:\d{2}:\d{2}\.\d{2}", parts[2].strip()))
                    line = ",".join(parts) + ("\n" if line.endswith("\n") else "")
            lines.append(line)
        transformed = "".join(lines)
    else:
        raise ValueError(f"Unsupported subtitle format for timestamp shifting: {extension}")

    Path(output_path).write_text(transformed, encoding="utf-8")

def update_subtitle_text(
    subtitle_path: str,
    output_path: str,
    entry_index: int,
    new_text: str,
) -> None:
    """Replace one subtitle cue's text while preserving its timing and format."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if entry_index < 0:
        raise ValueError("Subtitle entry index must be zero or greater")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()
    replacement = new_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    updated = False

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cue_index = -1
        out_blocks = []
        for block in blocks:
            if "-->" not in block:
                out_blocks.append(block)
                continue
            cue_index += 1
            if cue_index == entry_index:
                lines = block.splitlines()
                timing_index = next(i for i, line in enumerate(lines) if "-->" in line)
                out_blocks.append("\n".join(lines[:timing_index + 1] + (replacement.splitlines() or [""])))
                updated = True
            else:
                out_blocks.append(block)
        if not updated:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "\n\n".join(out_blocks) + "\n"

    elif extension == ".ass":
        cue_index = -1
        out_lines = []
        for line in content.splitlines(keepends=True):
            if line.startswith("Dialogue:"):
                cue_index += 1
                if cue_index == entry_index:
                    newline = "\n" if line.endswith("\n") else ""
                    raw = line.rstrip("\r\n")
                    parts = raw.split(",", 9)
                    if len(parts) < 10:
                        raise ValueError("Invalid ASS dialogue entry")
                    parts[9] = replacement.replace("\n", r"\N")
                    line = ",".join(parts) + newline
                    updated = True
            out_lines.append(line)
        if not updated:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "".join(out_lines)

    else:
        raise ValueError(f"Unsupported subtitle format for text editing: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")

def update_subtitle_timing(
    subtitle_path: str,
    output_path: str,
    entry_index: int,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Replace one subtitle cue's start/end times while preserving its text and format."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if entry_index < 0:
        raise ValueError("Subtitle entry index must be zero or greater")
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Subtitle end time must be greater than start time and both must be non-negative")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()
    updated = False

    def format_srt_vtt(value: float, separator: str) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", separator)

    def format_ass(value: float) -> str:
        centiseconds = round(value * 100)
        hours = centiseconds // 360000
        minutes = (centiseconds % 360000) // 6000
        seconds = (centiseconds % 6000) / 100
        return f"{hours:d}:{minutes:02d}:{seconds:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cue_index = -1
        out_blocks = []
        for block in blocks:
            if "-->" not in block:
                out_blocks.append(block)
                continue
            cue_index += 1
            if cue_index == entry_index:
                lines = block.splitlines()
                timing_index = next(i for i, line in enumerate(lines) if "-->" in line)
                separator = "," if "," in lines[timing_index] else "."
                lines[timing_index] = (
                    format_srt_vtt(start_seconds, separator)
                    + " --> "
                    + format_srt_vtt(end_seconds, separator)
                )
                out_blocks.append("\n".join(lines))
                updated = True
            else:
                out_blocks.append(block)
        if not updated:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "\n\n".join(out_blocks) + "\n"

    elif extension == ".ass":
        cue_index = -1
        out_lines = []
        for line in content.splitlines(keepends=True):
            if line.startswith("Dialogue:"):
                cue_index += 1
                if cue_index == entry_index:
                    newline = "\n" if line.endswith("\n") else ""
                    raw = line.rstrip("\r\n")
                    parts = raw.split(",", 9)
                    if len(parts) < 10:
                        raise ValueError("Invalid ASS dialogue entry")
                    parts[1] = format_ass(start_seconds)
                    parts[2] = format_ass(end_seconds)
                    line = ",".join(parts) + newline
                    updated = True
            out_lines.append(line)
        if not updated:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "".join(out_lines)

    else:
        raise ValueError(f"Unsupported subtitle format for timing editing: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")

def add_subtitle_entry(
    subtitle_path: str,
    output_path: str,
    insert_after_index: int | None,
    start_seconds: float,
    end_seconds: float,
    new_text: str,
) -> None:
    """Add one subtitle cue, inserting after a zero-based cue index or appending when omitted."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if start_seconds < 0 or end_seconds <= start_seconds:
        raise ValueError("Subtitle end time must be greater than start time and both must be non-negative")
    if insert_after_index is not None and insert_after_index < -1:
        raise ValueError("insert_after_index must be -1 or greater")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()
    replacement = new_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not replacement:
        raise ValueError("Subtitle text is required")

    def format_srt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", ",")

    def format_vtt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    def format_ass(value: float) -> str:
        centiseconds = round(value * 100)
        hours = centiseconds // 360000
        minutes = (centiseconds % 360000) // 6000
        seconds = (centiseconds % 6000) / 100
        return f"{hours:d}:{minutes:02d}:{seconds:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cue_blocks = [b for b in blocks if "-->" in b]
        insert_pos = len(cue_blocks) if insert_after_index is None else insert_after_index + 1
        if insert_pos < 0 or insert_pos > len(cue_blocks):
            raise ValueError("insert_after_index is outside the subtitle range")
        new_time = (
            (format_srt(start_seconds) + " --> " + format_srt(end_seconds))
            if extension == ".srt"
            else (format_vtt(start_seconds) + " --> " + format_vtt(end_seconds))
        )
        if extension == ".srt":
            new_block = "\n".join([str(insert_pos + 1), new_time] + (replacement.splitlines() or [""]))
        else:
            new_block = "\n".join([new_time] + (replacement.splitlines() or [""]))

        rebuilt = []
        seen_cues = 0
        for block in blocks:
            if "-->" in block:
                if seen_cues == insert_pos:
                    rebuilt.append(new_block)
                rebuilt.append(block)
                seen_cues += 1
            else:
                rebuilt.append(block)
        if insert_pos == len(cue_blocks):
            rebuilt.append(new_block)

        if extension == ".srt":
            cue_no = 1
            renumbered = []
            for block in rebuilt:
                if "-->" in block:
                    lines = block.splitlines()
                    if lines and lines[0].strip().isdigit():
                        lines[0] = str(cue_no)
                    cue_no += 1
                    renumbered.append("\n".join(lines))
                else:
                    renumbered.append(block)
            rebuilt = renumbered
        updated_content = "\n\n".join(rebuilt) + "\n"

    elif extension == ".ass":
        lines = content.splitlines(keepends=True)
        dialogue_positions = [i for i, line in enumerate(lines) if line.startswith("Dialogue:")]
        insert_pos = len(dialogue_positions) if insert_after_index is None else insert_after_index + 1
        if insert_pos < 0 or insert_pos > len(dialogue_positions):
            raise ValueError("insert_after_index is outside the subtitle range")
        dialogue = "Dialogue: 0," + format_ass(start_seconds) + "," + format_ass(end_seconds) + ",Default,,0,0,0,," + replacement.replace("\n", r"\N") + "\n"
        if insert_pos == len(dialogue_positions):
            lines.append(dialogue)
        else:
            lines.insert(dialogue_positions[insert_pos], dialogue)
        updated_content = "".join(lines)
    else:
        raise ValueError(f"Unsupported subtitle format for entry insertion: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")

def delete_subtitle_entry(
    subtitle_path: str,
    output_path: str,
    entry_index: int,
) -> None:
    """Delete one zero-based subtitle cue while preserving the remaining file format."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if entry_index < 0:
        raise ValueError("Subtitle entry index must be zero or greater")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cue_index = -1
        kept = []
        deleted = False
        for block in blocks:
            if "-->" not in block:
                kept.append(block)
                continue
            cue_index += 1
            if cue_index == entry_index:
                deleted = True
                continue
            kept.append(block)
        if not deleted:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")

        if extension == ".srt":
            cue_no = 1
            renumbered = []
            for block in kept:
                if "-->" in block:
                    lines = block.splitlines()
                    if lines and lines[0].strip().isdigit():
                        lines[0] = str(cue_no)
                    cue_no += 1
                    renumbered.append("\n".join(lines))
                else:
                    renumbered.append(block)
            kept = renumbered
        updated_content = "\n\n".join(kept).strip() + ("\n" if kept else "")

    elif extension == ".ass":
        lines = content.splitlines(keepends=True)
        cue_index = -1
        kept = []
        deleted = False
        for line in lines:
            if line.startswith("Dialogue:"):
                cue_index += 1
                if cue_index == entry_index:
                    deleted = True
                    continue
            kept.append(line)
        if not deleted:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "".join(kept)
    else:
        raise ValueError(f"Unsupported subtitle format for entry deletion: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")

def split_subtitle_entry(
    subtitle_path: str,
    output_path: str,
    entry_index: int,
    split_seconds: float,
) -> None:
    """Split one cue into two cues at the supplied timestamp."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if entry_index < 0:
        raise ValueError("Subtitle entry index must be zero or greater")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()

    def parse_srt_vtt(value: str) -> float:
        h, m, rest = value.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)

    def format_srt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", ",")

    def format_vtt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    def parse_ass(value: str) -> float:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def format_ass(value: float) -> str:
        centiseconds = round(value * 100)
        hours = centiseconds // 360000
        minutes = (centiseconds % 360000) // 6000
        seconds = (centiseconds % 6000) / 100
        return f"{hours:d}:{minutes:02d}:{seconds:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cue_index = -1
        rebuilt = []
        split_done = False
        for block in blocks:
            if "-->" not in block:
                rebuilt.append(block)
                continue
            cue_index += 1
            if cue_index != entry_index:
                rebuilt.append(block)
                continue

            lines = block.splitlines()
            timing_index = next(i for i, line in enumerate(lines) if "-->" in line)
            left, right = [part.strip() for part in lines[timing_index].split("-->", 1)]
            start_value = parse_srt_vtt(left)
            end_value = parse_srt_vtt(right)
            if not start_value < split_seconds < end_value:
                raise ValueError("Split time must be inside the selected subtitle cue")

            separator = "," if "," in lines[timing_index] else "."
            text_lines = lines[timing_index + 1:] or [""]
            text_block = "\n".join(text_lines)
            first_timing = (
                (format_srt(start_value) if separator == "," else format_vtt(start_value))
                + " --> "
                + (format_srt(split_seconds) if separator == "," else format_vtt(split_seconds))
            )
            second_timing = (
                (format_srt(split_seconds) if separator == "," else format_vtt(split_seconds))
                + " --> "
                + (format_srt(end_value) if separator == "," else format_vtt(end_value))
            )
            prefix = lines[:timing_index]
            rebuilt.extend([
                "\n".join(prefix + [first_timing, text_block]),
                "\n".join(prefix + [second_timing, text_block]),
            ])
            split_done = True

        if not split_done:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")

        if extension == ".srt":
            cue_no = 1
            renumbered = []
            for block in rebuilt:
                if "-->" in block:
                    lines = block.splitlines()
                    if lines and lines[0].strip().isdigit():
                        lines[0] = str(cue_no)
                    cue_no += 1
                    renumbered.append("\n".join(lines))
                else:
                    renumbered.append(block)
            rebuilt = renumbered
        updated_content = "\n\n".join(rebuilt) + "\n"

    elif extension == ".ass":
        lines = content.splitlines(keepends=True)
        cue_index = -1
        rebuilt = []
        split_done = False
        for line in lines:
            if not line.startswith("Dialogue:"):
                rebuilt.append(line)
                continue
            cue_index += 1
            if cue_index != entry_index:
                rebuilt.append(line)
                continue

            newline = "\n" if line.endswith("\n") else ""
            raw = line.rstrip("\r\n")
            parts = raw.split(",", 9)
            if len(parts) < 10:
                raise ValueError("Invalid ASS dialogue entry")
            start_value = parse_ass(parts[1].strip())
            end_value = parse_ass(parts[2].strip())
            if not start_value < split_seconds < end_value:
                raise ValueError("Split time must be inside the selected subtitle cue")

            first = parts.copy()
            second = parts.copy()
            first[2] = format_ass(split_seconds)
            second[1] = format_ass(split_seconds)
            rebuilt.append(",".join(first) + newline)
            rebuilt.append(",".join(second) + newline)
            split_done = True

        if not split_done:
            raise ValueError(f"Subtitle entry {entry_index + 1} not found")
        updated_content = "".join(rebuilt)

    else:
        raise ValueError(f"Unsupported subtitle format for entry splitting: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")

def merge_subtitle_entries(
    subtitle_path: str,
    output_path: str,
    entry_index: int,
) -> None:
    """Merge one cue with the following cue, combining their time range and text."""
    import re

    source = Path(subtitle_path)
    if not source.exists():
        raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
    if entry_index < 0:
        raise ValueError("Subtitle entry index must be zero or greater")

    content = source.read_text(encoding="utf-8-sig")
    extension = source.suffix.lower()

    def parse_srt_vtt(value: str) -> float:
        h, m, rest = value.replace(",", ".").split(":")
        return int(h) * 3600 + int(m) * 60 + float(rest)

    def format_srt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", ",")

    def format_vtt(value: float) -> str:
        total_ms = round(value * 1000)
        hours = total_ms // 3_600_000
        minutes = (total_ms % 3_600_000) // 60_000
        seconds = (total_ms % 60_000) / 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    def parse_ass(value: str) -> float:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)

    def format_ass(value: float) -> str:
        centiseconds = round(value * 100)
        hours = centiseconds // 360000
        minutes = (centiseconds % 360000) // 6000
        seconds = (centiseconds % 6000) / 100
        return f"{hours:d}:{minutes:02d}:{seconds:05.2f}"

    if extension in {".srt", ".vtt", ".sub", ".txt"}:
        blocks = re.split(r"\n{2,}", content.strip())
        cues = [(i, b) for i, b in enumerate(blocks) if "-->" in b]
        if entry_index >= len(cues) - 1:
            raise ValueError("Selected subtitle entry must have a following entry to merge")

        first_i, first_block = cues[entry_index]
        second_i, second_block = cues[entry_index + 1]
        first_lines = first_block.splitlines()
        second_lines = second_block.splitlines()
        first_timing_i = next(i for i, line in enumerate(first_lines) if "-->" in line)
        second_timing_i = next(i for i, line in enumerate(second_lines) if "-->" in line)
        first_start, _ = [part.strip() for part in first_lines[first_timing_i].split("-->", 1)]
        _, second_end = [part.strip() for part in second_lines[second_timing_i].split("-->", 1)]
        separator = "," if "," in first_lines[first_timing_i] else "."
        start_value = parse_srt_vtt(first_start)
        end_value = parse_srt_vtt(second_end)
        timing = (
            (format_srt(start_value) if separator == "," else format_vtt(start_value))
            + " --> "
            + (format_srt(end_value) if separator == "," else format_vtt(end_value))
        )
        first_text = first_lines[first_timing_i + 1:]
        second_text = second_lines[second_timing_i + 1:]
        combined_text = "\n".join(first_text + [""] + second_text)
        prefix = first_lines[:first_timing_i]
        merged = "\n".join(prefix + [timing, combined_text])

        rebuilt = []
        cue_seen = 0
        for idx, block in enumerate(blocks):
            if idx == first_i:
                rebuilt.append(merged)
            elif idx == second_i:
                continue
            else:
                rebuilt.append(block)
            if "-->" in block:
                cue_seen += 1

        if extension == ".srt":
            cue_no = 1
            renumbered = []
            for block in rebuilt:
                if "-->" in block:
                    lines = block.splitlines()
                    if lines and lines[0].strip().isdigit():
                        lines[0] = str(cue_no)
                    cue_no += 1
                    renumbered.append("\n".join(lines))
                else:
                    renumbered.append(block)
            rebuilt = renumbered
        updated_content = "\n\n".join(rebuilt) + "\n"

    elif extension == ".ass":
        lines = content.splitlines(keepends=True)
        dialogue = [i for i, line in enumerate(lines) if line.startswith("Dialogue:")]
        if entry_index >= len(dialogue) - 1:
            raise ValueError("Selected subtitle entry must have a following entry to merge")
        first_i, second_i = dialogue[entry_index], dialogue[entry_index + 1]
        first = lines[first_i].rstrip("\r\n").split(",", 9)
        second = lines[second_i].rstrip("\r\n").split(",", 9)
        if len(first) < 10 or len(second) < 10:
            raise ValueError("Invalid ASS dialogue entry")
        start_value = parse_ass(first[1].strip())
        end_value = parse_ass(second[2].strip())
        first[2] = format_ass(end_value)
        first[9] = first[9] + r"\N" + second[9]
        lines[first_i] = ",".join(first) + ("\n" if lines[first_i].endswith("\n") else "")
        del lines[second_i]
        updated_content = "".join(lines)
    else:
        raise ValueError(f"Unsupported subtitle format for entry merging: {extension}")

    Path(output_path).write_text(updated_content, encoding="utf-8")
