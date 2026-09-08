from datetime import datetime, timezone
import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.database import get_db
from app.features.media.models import Media
from app.shared.validators import (
    validate_filename_and_extension,
    validate_mime_type,
    validate_file_content,
    validate_file_size,
)
from app.core.config import get_settings

client = TestClient(app)


# ---------------------------------------------------------
# UNIT TESTS: VALIDATION LOGIC
# ---------------------------------------------------------

def test_validate_filename_and_extension_success() -> None:
    assert validate_filename_and_extension("video.mp4") == ".mp4"
    assert validate_filename_and_extension("track.MP3") == ".mp3"
    assert validate_filename_and_extension("photo.PNG") == ".png"
    assert validate_filename_and_extension("subtitles.srt") == ".srt"


def test_validate_filename_and_extension_failures() -> None:
    with pytest.raises(ValueError, match="Filename is required"):
        validate_filename_and_extension("")

    with pytest.raises(ValueError, match="Filename is required"):
        validate_filename_and_extension("   ")

    with pytest.raises(ValueError, match="File must have a valid extension"):
        validate_filename_and_extension("no_extension_file")

    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_filename_and_extension("malware.exe")

    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_filename_and_extension("document.pdf")


def test_validate_mime_type_success() -> None:
    assert validate_mime_type("video/mp4", ".mp4") == "video/mp4"
    assert validate_mime_type("image/png", ".png") == "image/png"
    assert validate_mime_type("audio/mpeg; charset=utf-8", ".mp3") == "audio/mpeg"
    # Fallback to extension inferred mime for octet-stream
    assert validate_mime_type("application/octet-stream", ".mp4") == "video/mp4"
    assert validate_mime_type(None, ".mp4") == "video/mp4"


def test_validate_mime_type_disallowed_and_mismatched() -> None:
    # Disallowed dangerous types
    with pytest.raises(ValueError, match="Disallowed or dangerous MIME type"):
        validate_mime_type("application/x-executable", ".mp4")

    with pytest.raises(ValueError, match="Disallowed or dangerous MIME type"):
        validate_mime_type("text/html", ".mp4")

    # Mismatched media category
    with pytest.raises(ValueError, match="invalid for video extension"):
        validate_mime_type("image/png", ".mp4")

    with pytest.raises(ValueError, match="invalid for image extension"):
        validate_mime_type("video/mp4", ".png")


def test_validate_file_content_signatures() -> None:
    # Dangerous executable headers
    with pytest.raises(ValueError, match="PE/MZ"):
        validate_file_content(b"MZ\x90\x00\x03\x00\x00\x00", ".mp4")

    with pytest.raises(ValueError, match="ELF"):
        validate_file_content(b"\x7fELF\x02\x01\x01\x00", ".mp4")

    with pytest.raises(ValueError, match="Mach-O"):
        validate_file_content(b"\xfe\xed\xfa\xce\x00\x00", ".mp4")

    with pytest.raises(ValueError, match="Script or HTML"):
        validate_file_content(b"<!DOCTYPE html><html>", ".mp4")

    # Safe media chunks pass without exception
    validate_file_content(b"\x00\x00\x00 ftypisom\x00\x00\x02\x00", ".mp4")
    validate_file_content(b"\x89PNG\r\n\x1a\n", ".png")


def test_validate_file_size() -> None:
    with pytest.raises(ValueError, match="must be greater than 0"):
        validate_file_size(0, 1000)

    with pytest.raises(ValueError, match="must be greater than 0"):
        validate_file_size(-5, 1000)

    # Within limit -> ok
    validate_file_size(500, 1000)

    # Exceeds limit -> 413
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        validate_file_size(1500, 1000)
    assert exc_info.value.status_code == 413


# ---------------------------------------------------------
# ENDPOINT TESTS: NORMAL UPLOAD (/media/upload)
# ---------------------------------------------------------

def test_upload_valid_media() -> None:
    now = datetime.now(timezone.utc)
    mock_media = Media(
        id=uuid4(),
        original_filename="sample.mp4",
        stored_filename="sample_stored.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size=1024,
        processing_status="pending",
        created_at=now,
    )

    async def override_db():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.media.routes.save_upload", new_callable=AsyncMock) as mock_save:
            mock_save.return_value = mock_media
            file_content = b"\x00\x00\x00\x18ftypmp42" + b"A" * 100
            response = client.post(
                "/media/upload",
                files={"file": ("sample.mp4", io.BytesIO(file_content), "video/mp4")},
            )
            assert response.status_code == 201
            data = response.json()
            assert data["original_filename"] == "sample.mp4"
            assert data["media_type"] == "video"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_unsupported_file_extension_returns_400() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        file_content = b"Binary executable content"
        response = client.post(
            "/media/upload",
            files={"file": ("program.exe", io.BytesIO(file_content), "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "unsupported file type" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_disallowed_mime_type_returns_400() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        file_content = b"Some text content"
        response = client.post(
            "/media/upload",
            files={"file": ("clip.mp4", io.BytesIO(file_content), "text/html")},
        )
        assert response.status_code == 400
        assert "disallowed or dangerous" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_mismatched_mime_type_returns_400() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        file_content = b"Image bytes"
        response = client.post(
            "/media/upload",
            files={"file": ("video.mp4", io.BytesIO(file_content), "image/png")},
        )
        assert response.status_code == 400
        assert "invalid for video" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_executable_signature_returns_400() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        # Renamed EXE as .mp4 with MZ header
        file_content = b"MZ\x90\x00\x03\x00\x00\x00dummy"
        response = client.post(
            "/media/upload",
            files={"file": ("sneaky.mp4", io.BytesIO(file_content), "video/mp4")},
        )
        assert response.status_code == 400
        assert "executable binary" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_empty_file_returns_400() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/media/upload",
            files={"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_upload_file_exceeding_size_limit_returns_413() -> None:
    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    settings = get_settings()
    original_limit = settings.max_upload_size_bytes
    try:
        # Temporarily lower max_upload_size_bytes for test
        settings.max_upload_size_bytes = 100
        file_content = b"\x00\x00\x00\x18ftypmp42" + b"X" * 150
        response = client.post(
            "/media/upload",
            files={"file": ("big.mp4", io.BytesIO(file_content), "video/mp4")},
        )
        assert response.status_code == 413
        assert "exceeds maximum allowed limit" in response.json()["detail"].lower()
    finally:
        settings.max_upload_size_bytes = original_limit
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# ENDPOINT TESTS: RESUMABLE UPLOADS
# ---------------------------------------------------------

def test_resumable_init_success() -> None:
    mock_upload_id = uuid4()
    with patch("app.features.media.resumable_service.ResumableUploadService.init_upload", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = mock_upload_id
        response = client.post(
            "/media/resumable/init",
            json={
                "original_filename": "video.mp4",
                "total_size": 1048576,
                "chunk_size": 524288,
            },
        )
        assert response.status_code == 200
        assert response.json() == {"upload_id": str(mock_upload_id)}


def test_resumable_init_invalid_extension_returns_400() -> None:
    response = client.post(
        "/media/resumable/init",
        json={
            "original_filename": "script.sh",
            "total_size": 1024,
        },
    )
    assert response.status_code == 400
    assert "unsupported file type" in response.json()["detail"].lower()


def test_resumable_init_zero_size_returns_400() -> None:
    response = client.post(
        "/media/resumable/init",
        json={
            "original_filename": "sample.mp4",
            "total_size": 0,
        },
    )
    assert response.status_code == 400
    assert "greater than 0" in response.json()["detail"].lower()


def test_resumable_init_exceeds_size_limit_returns_413() -> None:
    settings = get_settings()
    huge_size = settings.max_upload_size_bytes + 1024
    response = client.post(
        "/media/resumable/init",
        json={
            "original_filename": "huge.mp4",
            "total_size": huge_size,
        },
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed limit" in response.json()["detail"].lower()


def test_resumable_chunk_upload_success() -> None:
    upload_id = uuid4()
    with patch("app.features.media.resumable_service.ResumableUploadService.store_chunk", new_callable=AsyncMock):
        response = client.post(
            f"/media/resumable/{upload_id}/chunk/0",
            files={"file": ("chunk0.part", io.BytesIO(b"part0_bytes"), "application/octet-stream")},
        )
        assert response.status_code == 200
        assert response.json() == {"detail": "Chunk stored"}


def test_resumable_chunk_negative_index_returns_400() -> None:
    upload_id = uuid4()
    response = client.post(
        f"/media/resumable/{upload_id}/chunk/-1",
        files={"file": ("chunk0.part", io.BytesIO(b"part_bytes"), "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "non-negative" in response.json()["detail"].lower()


def test_resumable_pause_and_resume() -> None:
    upload_id = uuid4()
    with patch("app.features.media.resumable_service.ResumableUploadService.pause", new_callable=AsyncMock), \
         patch("app.features.media.resumable_service.ResumableUploadService.resume", new_callable=AsyncMock):
        pause_resp = client.post(f"/media/resumable/{upload_id}/pause")
        assert pause_resp.status_code == 200
        assert pause_resp.json() == {"detail": "paused"}

        resume_resp = client.post(f"/media/resumable/{upload_id}/resume")
        assert resume_resp.status_code == 200
        assert resume_resp.json() == {"detail": "resumed"}


def test_resumable_retry_and_cancel() -> None:
    upload_id = uuid4()
    with patch("app.features.media.resumable_service.ResumableUploadService.store_chunk", new_callable=AsyncMock), \
         patch("app.features.media.resumable_service.ResumableUploadService.cancel", new_callable=AsyncMock):
        retry_resp = client.post(
            f"/media/resumable/{upload_id}/retry?index=0",
            files={"file": ("chunk0.part", io.BytesIO(b"retry_bytes"), "application/octet-stream")},
        )
        assert retry_resp.status_code == 200

        cancel_resp = client.delete(f"/media/resumable/{upload_id}")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json() == {"detail": "canceled"}


def test_resumable_finalize_success() -> None:
    upload_id = uuid4()
    now = datetime.now(timezone.utc)
    mock_media = Media(
        id=uuid4(),
        original_filename="assembled.mp4",
        stored_filename="assembled_stored.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size=2048,
        processing_status="pending",
        created_at=now,
    )

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.media.resumable_service.ResumableUploadService.finalize", new_callable=AsyncMock) as mock_final:
            mock_final.return_value = mock_media
            response = client.post(f"/media/resumable/{upload_id}/finalize")
            assert response.status_code == 200
            data = response.json()
            assert data["original_filename"] == "assembled.mp4"
            assert data["file_size"] == 2048
    finally:
        app.dependency_overrides.pop(get_db, None)
