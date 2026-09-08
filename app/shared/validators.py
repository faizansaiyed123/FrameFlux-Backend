from pathlib import Path
from fastapi import HTTPException, status

from app.shared.constants import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    AUDIO_EXTENSIONS,
    DISALLOWED_MIME_PREFIXES,
    EXTENSION_TO_MIME,
    IMAGE_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
)


def validate_filename_and_extension(filename: str | None) -> str:
    """Validate that the filename exists and has a supported extension.

    Returns the normalized lower-case extension (e.g. '.mp4').
    Raises ValueError if missing or unsupported.
    """
    if not filename or not filename.strip():
        raise ValueError("Filename is required")

    extension = Path(filename.strip()).suffix.lower()

    if not extension:
        raise ValueError("File must have a valid extension")

    if extension not in ALLOWED_EXTENSIONS:
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type: '{extension}'. Allowed extensions: {allowed_list}"
        )

    return extension


def validate_mime_type(content_type: str | None, extension: str) -> str:
    """Validate and normalize the MIME type for the given file extension.

    Returns a clean, valid MIME type string.
    Raises ValueError if MIME type is disallowed or incompatible with the file type.
    """
    if not content_type or not content_type.strip():
        return EXTENSION_TO_MIME.get(extension, "application/octet-stream")

    # Clean off parameters such as '; charset=utf-8'
    cleaned_mime = content_type.split(";")[0].strip().lower()

    # Reject explicitly dangerous or disallowed formats
    for prefix in DISALLOWED_MIME_PREFIXES:
        if cleaned_mime.startswith(prefix):
            raise ValueError(f"Disallowed or dangerous MIME type: '{content_type}'")

    # If generic binary stream, infer from extension
    if cleaned_mime == "application/octet-stream":
        return EXTENSION_TO_MIME.get(extension, cleaned_mime)

    # Check category compatibility
    if extension in VIDEO_EXTENSIONS:
        if not (
            cleaned_mime.startswith("video/")
            or cleaned_mime in ("application/x-matroska", "application/octet-stream")
        ):
            raise ValueError(
                f"MIME type '{content_type}' is invalid for video extension '{extension}'"
            )

    elif extension in AUDIO_EXTENSIONS:
        # Note: audio/mp4 and video/mp4 may both be used for m4a/aac containers
        if not (
            cleaned_mime.startswith("audio/")
            or cleaned_mime in ("video/mp4", "application/ogg", "application/octet-stream")
        ):
            raise ValueError(
                f"MIME type '{content_type}' is invalid for audio extension '{extension}'"
            )

    elif extension in IMAGE_EXTENSIONS:
        if not (cleaned_mime.startswith("image/") or cleaned_mime == "application/octet-stream"):
            raise ValueError(
                f"MIME type '{content_type}' is invalid for image extension '{extension}'"
            )

    elif extension in SUBTITLE_EXTENSIONS:
        if not (
            cleaned_mime.startswith("text/")
            or "subrip" in cleaned_mime
            or cleaned_mime == "application/octet-stream"
        ):
            raise ValueError(
                f"MIME type '{content_type}' is invalid for subtitle extension '{extension}'"
            )

    return cleaned_mime


def validate_file_content(header_chunk: bytes, extension: str) -> None:
    """Inspect initial file bytes to detect forbidden executable, shell, or script payloads.

    Raises ValueError if the content signature is disallowed.
    """
    if not header_chunk:
        return

    # Check for executable and script binary signatures
    # 1. DOS / Windows PE executable (MZ header)
    if header_chunk.startswith(b"MZ"):
        raise ValueError("Invalid file content: Executable binary (PE/MZ) detected")

    # 2. Linux ELF binary
    if header_chunk.startswith(b"\x7fELF"):
        raise ValueError("Invalid file content: Executable binary (ELF) detected")

    # 3. Mach-O binary
    macho_headers = (
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
    )
    if any(header_chunk.startswith(sig) for sig in macho_headers):
        raise ValueError("Invalid file content: Executable binary (Mach-O) detected")

    # 4. Java bytecode
    if header_chunk.startswith(b"\xca\xfe\xba\xbe"):
        raise ValueError("Invalid file content: Compiled bytecode detected")

    # 5. Dangerous script/HTML tags if not a subtitle
    if extension not in SUBTITLE_EXTENSIONS:
        lower_snippet = header_chunk[:256].strip().lower()
        if lower_snippet.startswith((b"<!doctype html", b"<html", b"<script", b"<?php", b"#!/bin/sh", b"#!/bin/bash")):
            raise ValueError("Invalid file content: Script or HTML payload detected in media file")


def validate_file_size(size: int, max_size: int) -> None:
    """Validate that file size is within limits.

    Raises HTTPException(413) if size exceeds max_size.
    Raises ValueError(400) if size is 0 or negative.
    """
    if size <= 0:
        raise ValueError("File size must be greater than 0")

    if size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size of {size} bytes exceeds maximum allowed limit of {max_size} bytes",
        )
