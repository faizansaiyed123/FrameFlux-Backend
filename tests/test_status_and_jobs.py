from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient
from arq.jobs import JobStatus, JobResult, JobDef
from datetime import datetime

from app.main import app
from app.infrastructure.database import get_db

client = TestClient(app)


def test_get_nonexistent_job() -> None:
    with patch("app.features.jobs.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = None
        response = client.get("/jobs/nonexistent-job-id")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


def test_get_job_status_queued() -> None:
    mock_data = {
        "job_id": "job-123",
        "status": "queued",
        "progress": 0,
        "stage": "Queued in background",
        "task_name": "convert_media_task",
        "media_id": "media-abc",
        "enqueue_time": datetime.utcnow().isoformat(),
        "start_time": None,
        "finish_time": None,
        "success": None,
        "result": None,
        "error": None,
    }
    with patch("app.features.jobs.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = mock_data
        response = client.get("/jobs/job-123")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job-123"
        assert data["status"] == "queued"
        assert data["progress"] == 0
        assert data["task_name"] == "convert_media_task"
        assert data["media_id"] == "media-abc"


def test_get_job_status_processing() -> None:
    mock_data = {
        "job_id": "job-456",
        "status": "processing",
        "progress": 65,
        "stage": "Processing media with FFmpeg",
        "task_name": "convert_media_task",
        "media_id": "media-xyz",
        "enqueue_time": datetime.utcnow().isoformat(),
        "start_time": datetime.utcnow().isoformat(),
        "finish_time": None,
        "success": None,
        "result": None,
        "error": None,
    }
    with patch("app.features.jobs.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = mock_data
        response = client.get("/jobs/job-456")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing"
        assert data["progress"] == 65
        assert data["stage"] == "Processing media with FFmpeg"


def test_get_job_status_completed() -> None:
    mock_data = {
        "job_id": "job-789",
        "status": "completed",
        "progress": 100,
        "stage": "Processing completed",
        "task_name": "convert_media_task",
        "media_id": "media-xyz",
        "enqueue_time": datetime.utcnow().isoformat(),
        "start_time": datetime.utcnow().isoformat(),
        "finish_time": datetime.utcnow().isoformat(),
        "success": True,
        "result": {"output_filename": "converted.mp4"},
        "error": None,
    }
    with patch("app.features.jobs.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = mock_data
        response = client.get("/jobs/job-789")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert data["success"] is True
        assert data["result"]["output_filename"] == "converted.mp4"


def test_get_job_status_failed() -> None:
    mock_data = {
        "job_id": "job-failed",
        "status": "failed",
        "progress": 42,
        "stage": "Processing failed",
        "task_name": "convert_media_task",
        "media_id": "media-xyz",
        "enqueue_time": datetime.utcnow().isoformat(),
        "start_time": datetime.utcnow().isoformat(),
        "finish_time": datetime.utcnow().isoformat(),
        "success": False,
        "result": None,
        "error": "FFmpeg processing failed",
    }
    with patch("app.features.jobs.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = mock_data
        response = client.get("/jobs/job-failed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"
        assert data["progress"] == 42
        assert data["error"] == "FFmpeg processing failed"


def test_get_media_job_alias() -> None:
    mock_data = {
        "job_id": "job-alias",
        "status": "processing",
        "progress": 50,
        "stage": "Working",
        "task_name": "edit_media_task",
        "media_id": "media-1",
        "enqueue_time": None,
        "start_time": None,
        "finish_time": None,
        "success": None,
        "result": None,
        "error": None,
    }
    with patch("app.features.media.routes.get_job_status", new_callable=AsyncMock) as mock_status:
        mock_status.return_value = mock_data
        response = client.get("/media/jobs/job-alias")
        assert response.status_code == 200
        assert response.json()["job_id"] == "job-alias"


def test_list_jobs() -> None:
    mock_queued = [
        {
            "job_id": "q-1",
            "status": "queued",
            "progress": 0,
            "stage": "In queue",
            "task_name": "process_media_task",
            "media_id": "m-1",
            "enqueue_time": datetime.utcnow().isoformat(),
        }
    ]
    with patch("app.features.jobs.routes.list_queued_jobs", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_queued
        response = client.get("/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["job_id"] == "q-1"


def test_media_status_endpoint() -> None:
    media_id = str(uuid4())
    mock_progress = {
        "media_id": media_id,
        "status": "processing",
        "progress": 65,
        "stage": "Processing media with FFmpeg",
        "job_id": "job-100",
        "processed_filename": None,
        "error": None,
    }

    class DummyMedia:
        id = media_id
        processing_status = "processing"
        processing_error = None
        processed_filename = None

    async def override_get_db():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = DummyMedia()
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("app.features.media.routes.get_media_progress", new_callable=AsyncMock) as mock_get_prog:
            mock_get_prog.return_value = mock_progress
            response = client.get(f"/media/{media_id}/status")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "processing"
            assert data["progress"] == 65
            assert data["job_id"] == "job-100"

            # Check /media/{media_id}/progress returns identical structure
            response_prog = client.get(f"/media/{media_id}/progress")
            assert response_prog.status_code == 200
            assert response_prog.json()["progress"] == 65
    finally:
        app.dependency_overrides.clear()


def test_media_status_not_found() -> None:
    media_id = str(uuid4())

    async def override_get_db():
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = client.get(f"/media/{media_id}/status")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
