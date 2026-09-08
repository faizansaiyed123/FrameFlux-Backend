from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.database import get_db
from app.features.projects.models import Project
from app.features.media.models import Media

client = TestClient(app)


def _make_mock_project(project_id=None, name="Sample Project"):
    p_id = project_id or uuid4()
    now = datetime.now(timezone.utc)
    return Project(
        id=p_id,
        name=name,
        description="A test project description",
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------
# PROJECT CRUD TESTS
# ---------------------------------------------------------

def test_create_project() -> None:
    mock_project = _make_mock_project(name="Documentary 2026")

    async def override_db():
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.create_project", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_project
            response = client.post(
                "/projects",
                json={"name": "Documentary 2026", "description": "A test project description"},
            )
            assert response.status_code == 201
            data = response.json()
            assert data["name"] == "Documentary 2026"
            assert data["id"] == str(mock_project.id)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_projects() -> None:
    p1 = _make_mock_project(name="Project 1")
    p2 = _make_mock_project(name="Project 2")

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.list_projects", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [p1, p2]
            response = client.get("/projects")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Project 1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_project_success() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id, name="Found Project")

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_project
            response = client.get(f"/projects/{project_id}")
            assert response.status_code == 200
            assert response.json()["name"] == "Found Project"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_project_not_found_returns_404() -> None:
    project_id = uuid4()

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            response = client.get(f"/projects/{project_id}")
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_update_project_success() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id, name="Old Name")
    updated_project = _make_mock_project(project_id=project_id, name="New Name")

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get, \
             patch("app.features.projects.routes.update_project", new_callable=AsyncMock) as mock_upd:
            mock_get.return_value = mock_project
            mock_upd.return_value = updated_project
            response = client.patch(
                f"/projects/{project_id}",
                json={"name": "New Name"},
            )
            assert response.status_code == 200
            assert response.json()["name"] == "New Name"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_delete_project_success() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id)

    async def override_db():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get, \
             patch("app.features.projects.routes.delete_project", new_callable=AsyncMock) as mock_del:
            mock_get.return_value = mock_project
            mock_del.return_value = None
            response = client.delete(f"/projects/{project_id}")
            assert response.status_code == 204
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# PROJECT MEDIA & BATCH PROCESSING TESTS
# ---------------------------------------------------------

def test_list_project_media() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id)
    mock_media = Media(
        id=uuid4(),
        original_filename="clip.mp4",
        stored_filename="clip_stored.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size=1024,
        project_id=project_id,
    )

    async def override_db():
        session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_media]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        session.execute.return_value = mock_res
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_project
            response = client.get(f"/projects/{project_id}/media")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["original_filename"] == "clip.mp4"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_process_project_batch() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id)
    media1 = Media(
        id=uuid4(),
        original_filename="c1.mp4",
        stored_filename="c1_stored.mp4",
        media_type="video",
        mime_type="video/mp4",
        file_size=1024,
        project_id=project_id,
    )

    async def override_db():
        session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [media1]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        session.execute.return_value = mock_res
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        mock_job = MagicMock()
        mock_job.job_id = "job-batch-1"
        mock_redis = AsyncMock()
        mock_redis.enqueue_job.return_value = mock_job
        mock_redis.close = AsyncMock()

        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get, \
             patch("app.features.projects.routes.create_worker_pool", new_callable=AsyncMock) as mock_pool:
            mock_get.return_value = mock_project
            mock_pool.return_value = mock_redis
            response = client.post(f"/projects/{project_id}/process")
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == str(project_id)
            assert data["status"] == "queued"
            assert len(data["jobs"]) == 1
            assert data["jobs"][0]["job_id"] == "job-batch-1"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_project_processing_status_aggregation() -> None:
    project_id = uuid4()
    mock_project = _make_mock_project(project_id=project_id)

    media1 = Media(id=uuid4(), original_filename="c1.mp4", stored_filename="s1.mp4", media_type="video", mime_type="video/mp4", file_size=10, project_id=project_id, processing_status="completed")
    media2 = Media(id=uuid4(), original_filename="c2.mp4", stored_filename="s2.mp4", media_type="video", mime_type="video/mp4", file_size=10, project_id=project_id, processing_status="processing")

    async def override_db():
        session = AsyncMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [media1, media2]
        mock_res = MagicMock()
        mock_res.scalars.return_value = mock_scalars
        session.execute.return_value = mock_res
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        with patch("app.features.projects.routes.get_project", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_project
            response = client.get(f"/projects/{project_id}/status")
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == str(project_id)
            assert data["status"] == "processing"
            assert data["total"] == 2
            assert data["completed"] == 1
            assert data["processing"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
