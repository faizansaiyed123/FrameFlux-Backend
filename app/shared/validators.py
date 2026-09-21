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
    if not content_type or not content_type.strip():
        return EXTENSION_TO_MIME.get(extension, "application/octet-stream")

    cleaned_mime = content_type.split(";")[0].strip().lower()

    for prefix in DISALLOWED_MIME_PREFIXES:
        if cleaned_mime.startswith(prefix):
            raise ValueError(
                f"Disallowed or dangerous MIME type: '{content_type}'"
            )

    if cleaned_mime == "application/octet-stream":
        return EXTENSION_TO_MIME.get(extension, cleaned_mime)

    if extension in VIDEO_EXTENSIONS:
        valid = cleaned_mime.startswith("video/") or cleaned_mime in (
            "application/x-matroska",
            "application/octet-stream",
        )
    elif extension in AUDIO_EXTENSIONS:
        valid = cleaned_mime.startswith("audio/") or cleaned_mime in (
            "video/mp4",
            "application/ogg",
            "application/octet-stream",
        )
    elif extension in IMAGE_EXTENSIONS:
        valid = cleaned_mime.startswith("image/") or cleaned_mime == "application/octet-stream"
    elif extension in SUBTITLE_EXTENSIONS:
        valid = (
            cleaned_mime.startswith("text/")
            or "subrip" in cleaned_mime
            or cleaned_mime == "application/octet-stream"
        )
    else:
        valid = cleaned_mime in ALLOWED_MIME_TYPES

    if not valid:
        raise ValueError(
            f"MIME type '{content_type}' is invalid for extension '{extension}'"
        )
    return cleaned_mime


def validate_file_content(header_chunk: bytes, extension: str) -> None:
    if not header_chunk:
        return

    if header_chunk.startswith(b"MZ"):
        raise ValueError("Invalid file content: Executable binary (PE/MZ) detected")
    if header_chunk.startswith(b"\x7fELF"):
        raise ValueError("Invalid file content: Executable binary (ELF) detected")

    macho_headers = (
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
    )
    if any(header_chunk.startswith(sig) for sig in macho_headers):
        raise ValueError("Invalid file content: Executable binary (Mach-O) detected")

    if header_chunk.startswith(b"\xca\xfe\xba\xbe"):
        raise ValueError("Invalid file content: Compiled bytecode detected")

    if extension not in SUBTITLE_EXTENSIONS:
        lower_snippet = header_chunk[:256].strip().lower()
        if lower_snippet.startswith((
            b"<!doctype html",
            b"<html",
            b"<script",
            b"<?php",
            b"#!/bin/sh",
            b"#!/bin/bash",
        )):
            raise ValueError(
                "Invalid file content: Script or HTML payload detected in media file"
            )


def validate_file_size(size: int, max_size: int) -> None:
    if size <= 0:
        raise ValueError("File size must be greater than 0")
    if size > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=(
                f"File size of {size} bytes exceeds maximum allowed limit "
                f"of {max_size} bytes"
            ),
        )
