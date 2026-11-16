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
