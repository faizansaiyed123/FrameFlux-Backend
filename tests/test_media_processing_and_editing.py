from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.database import get_db
from app.features.media.models import Media

client = TestClient(app)


def _make_mock_media(
    media_id=None,
    status="pending",
    media_type="video",
    stored="sample_stored.mp4",
):
    m_id = media_id or uuid4()
    now = datetime.now(timezone.utc)
    return Media(
        id=m_id,
        original_filename="sample.mp4",
        stored_filename=stored,
        media_type=media_type,
        mime_type="video/mp4",
        file_size=1024,
        processing_status=status,
        processing_error=None,
        project_id=None,
        created_at=now,
    )


# ---------------------------------------------------------
# MEDIA PROCESSING ENDPOINT TESTS
# ---------------------------------------------------------

def test_process_media_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id, status="pending")

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-proc-123"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            response = client.post(f"/media/{media_id}/process")
            assert response.status_code == 200
            data = response.json()
            assert data["media_id"] == str(media_id)
            assert data["status"] == "queued"
            assert data["job_id"] == "job-proc-123"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_process_media_already_processing_returns_409() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id, status="processing")

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(f"/media/{media_id}/process")
        assert response.status_code == 409
        assert "already processing" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_process_media_already_completed_returns_409() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id, status="completed")

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(f"/media/{media_id}/process")
        assert response.status_code == 409
        assert "already processed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_process_media_not_found_returns_404() -> None:
    media_id = uuid4()

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(f"/media/{media_id}/process")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# CONVERSION & ASPECT RATIO / AUDIO OPTIONS TESTS
# ---------------------------------------------------------

def test_convert_media_with_aspect_ratio_and_audio() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-conv-456"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {
                "format": "webm",
                "aspect_ratio": "16:9",
                "audio_codec": "opus",
                "audio_bitrate": "128k",
                "video_codec": "libvpx-vp9",
                "video_bitrate": "2M",
                "resolution": "1080p",
                "quality": 28,
            }
            response = client.post(f"/media/{media_id}/convert", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["job_id"] == "job-conv-456"
            assert "converted" in data["output_filename"]
            assert data["output_filename"].endswith(".webm")

            # Verify options passed into enqueue_media_job
            call_args = mock_enq.call_args[0]
            assert call_args[0] == "convert_media_task"
            options = call_args[4]
            assert options["aspect_ratio"] == "16:9"
            assert options["audio_codec"] == "opus"
            assert options["bitrate"] == "2M"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# EDITING ENDPOINT TESTS (TRIM, CUT, EXTRACT)
# ---------------------------------------------------------

def test_edit_media_trim_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-edit-789"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"operation": "trim", "start": 2.5, "end": 8.0}
            response = client.post(f"/media/{media_id}/edit", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "trim"
            assert data["job_id"] == "job-edit-789"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_edit_media_invalid_operation_returns_400() -> None:
    media_id = uuid4()
    payload = {"operation": "unsupported_op", "start": 0.0, "end": 5.0}
    response = client.post(f"/media/{media_id}/edit", json=payload)
    assert response.status_code == 400
    assert "trim, cut, or extract" in response.json()["detail"].lower()


def test_edit_media_invalid_timestamps_returns_400() -> None:
    media_id = uuid4()
    payload = {"operation": "trim", "start": 10.0, "end": 5.0}
    response = client.post(f"/media/{media_id}/edit", json=payload)
    assert response.status_code == 400
    assert "end time must be greater than start time" in response.json()["detail"].lower()


# ---------------------------------------------------------
# CLIP OPERATIONS (SPLIT, KEEP, DELETE, REORDER, APPEND)
# ---------------------------------------------------------

def test_split_media_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-split-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"split_points": [5.0, 10.5]}
            response = client.post(f"/media/{media_id}/split", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "split"
            assert "split" in data["output_prefix"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_keep_clips_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-keep-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"clips": [{"start": 0.0, "end": 4.0}, {"start": 8.0, "end": 12.0}]}
            response = client.post(f"/media/{media_id}/clips/keep", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "keep_clips"
            assert data["job_id"] == "job-keep-1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_delete_clips_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-del-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"clips": [{"start": 4.0, "end": 8.0}]}
            response = client.post(f"/media/{media_id}/clips/delete", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "delete_clips"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_reorder_clips_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-reorder-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"media_ids": ["clip2.mp4", "clip1.mp4"]}
            response = client.post(f"/media/{media_id}/clips/reorder", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "reorder"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_append_clips_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-append-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"media_ids": ["intro.mp4", "outro.mp4"]}
            response = client.post(f"/media/{media_id}/clips/append", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "append"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# OVERLAYS (SINGLE & MULTI)
# ---------------------------------------------------------

def test_overlay_single_text_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-overlay-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {
                "operation": "text",
                "text": "Sample Title",
                "x": 50,
                "y": 100,
                "font_size": 24,
                "opacity": 0.9,
            }
            response = client.post(f"/media/{media_id}/overlay", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "text"
            assert data["job_id"] == "job-overlay-1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_overlay_multi_array_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-overlay-multi"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {
                "overlays": [
                    {"operation": "text", "text": "Top Title", "x": 10, "y": 20},
                    {"operation": "watermark", "image_filename": "logo.png", "opacity": 0.5},
                ]
            }
            response = client.post(f"/media/{media_id}/overlay", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["operation"] == "multi_overlay"
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# TRANSFORM, FREEZE FRAME, MERGE & CRUD
# ---------------------------------------------------------

def test_transform_media_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-transform-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"operation": "speed", "speed": 1.5}
            response = client.post(f"/media/{media_id}/transform", json=payload)
            assert response.status_code == 200
            assert response.json()["operation"] == "speed"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_freeze_frame_success() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-freeze-1"
        with patch("app.features.media.routes.enqueue_media_job", new_callable=AsyncMock) as mock_enq:
            mock_enq.return_value = mock_job
            payload = {"timestamp": 3.0, "duration": 2.0}
            response = client.post(f"/media/{media_id}/freeze", json=payload)
            assert response.status_code == 200
            assert response.json()["operation"] == "freeze"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_and_get_media() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_media]
        mock_res.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_res
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        list_resp = client.get("/media")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 1

        get_resp = client.get(f"/media/{media_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == str(media_id)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_delete_media() -> None:
    media_id = uuid4()
    mock_media = _make_mock_media(media_id=media_id)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_media
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.media.routes.delete_media_file", new_callable=AsyncMock):
            del_resp = client.delete(f"/media/{media_id}")
            assert del_resp.status_code == 204
    finally:
        app.dependency_overrides.pop(get_db, None)
