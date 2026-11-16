from fastapi.testclient import TestClient

from app.demo.main import app
from app.demo.state import store


client = TestClient(app)


def setup_function():
    store.reset()


def test_health_and_seeded_dashboard():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "demo"

    dashboard = client.get("/dashboard/overview")
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["total_projects"] == 3
    assert body["total_media"] == 8
    assert body["processing_status_counts"]["completed"] >= 1


def test_project_and_media_workflow_is_mutable():
    project = client.post("/projects", json={"name": "Recruiter Demo Project", "description": "Created in demo"})
    assert project.status_code == 201
    project_id = project.json()["id"]

    projects = client.get("/projects").json()
    assert any(item["id"] == project_id for item in projects)

    attach = client.patch(f"/media/demo-media-008/project/{project_id}")
    assert attach.status_code == 200
    assert attach.json()["project_id"] == project_id

    folders = client.post(f"/projects/{project_id}/folders?name=Exports")
    assert folders.status_code == 200
    assert folders.json()["name"] == "Exports"


def test_processing_job_progresses_and_completes():
    response = client.post("/media/demo-media-001/convert", json={"format": "webm"})
    assert response.status_code == 200
    job_id = response.json()["job_id"]

    jobs = client.get("/jobs").json()
    job = next(item for item in jobs if item["job_id"] == job_id)
    assert job["status"] in {"processing", "completed"}

    for _ in range(8):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] == "completed":
            break
        store.state["jobs"][0]["_last_touch"] = 0

    final = client.get(f"/jobs/{job_id}").json()
    assert final["status"] == "completed"


def test_reset_restores_seed():
    client.post("/projects", json={"name": "Temporary"})
    assert len(client.get("/projects").json()) == 4

    reset = client.post("/demo/reset")
    assert reset.status_code == 200
    assert len(client.get("/projects").json()) == 3


def test_browser_cors_accepts_credentialed_frontend_origin():
    response = client.options(
        "/dashboard/overview",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_frontend_binary_and_collection_response_shapes():
    thumbnail = client.get("/thumbnails/demo-media-001")
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/svg+xml")

    audio = client.get("/audio/demo-media-003/extract")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content[:4] == b"RIFF"

    subtitle_tracks = client.get("/subtitles/demo-media-001/tracks")
    assert subtitle_tracks.status_code == 200
    assert subtitle_tracks.json() == []

    media_info = client.get("/media-info/demo-media-001")
    assert media_info.status_code == 200
    assert media_info.json()["file_name"] == "product-launch-master.mp4"


def test_resumable_upload_progress_uses_uploaded_chunk_bytes():
    initialized = client.post(
        "/media/resumable/init",
        json={"original_filename": "large-upload.mp4", "total_size": 10, "chunk_size": 4},
    )
    assert initialized.status_code == 200
    upload_id = initialized.json()["upload_id"]

    chunk = client.post(
        f"/media/resumable/{upload_id}/chunk/0",
        files={"file": ("chunk.bin", b"1234", "application/octet-stream")},
    )
    assert chunk.status_code == 200
    assert chunk.json()["detail"]

    progress = client.get(f"/media/uploads/{upload_id}/progress")
    assert progress.status_code == 200
    assert progress.json()["progress"] == 40
