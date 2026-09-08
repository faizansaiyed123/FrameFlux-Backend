from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.infrastructure.database import get_db
from app.features.auth.dependencies import get_current_active_user, get_current_user
from app.features.auth.models import User
from app.features.projects.models import Project
from app.features.media.models import Media

client = TestClient(app)

USER_A_ID = uuid4()
USER_B_ID = uuid4()

USER_A = User(
    id=USER_A_ID,
    email="alice@example.com",
    password_hash="mock_hash",
    full_name="Alice",
    is_active=True,
)

USER_B = User(
    id=USER_B_ID,
    email="bob@example.com",
    password_hash="mock_hash",
    full_name="Bob",
    is_active=True,
)


def _make_project(user_id, project_id=None, name="Project"):
    p_id = project_id or uuid4()
    now = datetime.now(timezone.utc)
    return Project(
        id=p_id,
        user_id=user_id,
        name=name,
        description="Desc",
        created_at=now,
        updated_at=now,
    )


def _make_media(user_id, media_id=None, stored="file.mp4"):
    m_id = media_id or uuid4()
    now = datetime.now(timezone.utc)
    return Media(
        id=m_id,
        user_id=user_id,
        original_filename="test.mp4",
        stored_filename=stored,
        media_type="video",
        mime_type="video/mp4",
        file_size=1024,
        processing_status="pending",
        created_at=now,
    )


# ---------------------------------------------------------
# UNAUTHENTICATED REQUESTS REQUIRE AUTH (401)
# ---------------------------------------------------------

def test_unauthenticated_requests_fail_with_401():
    # Ensure no dependency override
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_current_user, None)

    # Projects
    assert client.get("/projects").status_code == 401
    assert client.post("/projects", json={"name": "Test"}).status_code == 401

    # Media
    assert client.get("/media").status_code == 401
    assert client.get(f"/media/{uuid4()}").status_code == 401
    assert client.delete(f"/media/{uuid4()}").status_code == 401

    # Jobs
    assert client.get("/jobs").status_code == 401


# ---------------------------------------------------------
# IDOR PROTECTION: USER CANNOT ACCESS ANOTHER USER'S PROJECT
# ---------------------------------------------------------

def test_user_cannot_access_other_users_project():
    app.dependency_overrides[get_current_active_user] = lambda: USER_B
    app.dependency_overrides[get_current_user] = lambda: USER_B

    project_a_id = uuid4()

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        # Simulates DB returning None when queried for project belonging to USER_B
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        # GET returns 404
        resp = client.get(f"/projects/{project_a_id}")
        assert resp.status_code == 404

        # PATCH returns 404
        resp = client.patch(f"/projects/{project_a_id}", json={"name": "Hacked"})
        assert resp.status_code == 404

        # DELETE returns 404
        resp = client.delete(f"/projects/{project_a_id}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------
# IDOR PROTECTION: USER CANNOT ACCESS ANOTHER USER'S MEDIA
# ---------------------------------------------------------

def test_user_cannot_access_other_users_media():
    app.dependency_overrides[get_current_active_user] = lambda: USER_B
    app.dependency_overrides[get_current_user] = lambda: USER_B

    media_a = _make_media(user_id=USER_A_ID)

    async def override_db():
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = media_a
        session.execute.return_value = mock_result
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        # GET another user's media returns 404
        resp = client.get(f"/media/{media_a.id}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Media not found"

        # Status returns 404
        resp = client.get(f"/media/{media_a.id}/status")
        assert resp.status_code == 404

        # DELETE returns 404
        resp = client.delete(f"/media/{media_a.id}")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------
# IDOR PROTECTION: USER CANNOT MERGE ANOTHER USER'S MEDIA
# ---------------------------------------------------------

def test_user_cannot_cross_reference_other_users_media():
    app.dependency_overrides[get_current_active_user] = lambda: USER_B
    app.dependency_overrides[get_current_user] = lambda: USER_B

    media_b = _make_media(user_id=USER_B_ID)
    media_a = _make_media(user_id=USER_A_ID, stored="victim_file.mp4")

    async def override_db():
        session = AsyncMock()

        async def fake_execute(statement, *args, **kwargs):
            mock_res = MagicMock()
            # If query is selecting by ID or stored_filename:
            sql_str = str(statement)
            if "media.id = :id_1" in sql_str:
                mock_res.scalar_one_or_none.return_value = media_b
            else:
                # Referencing another user's media
                mock_res.scalars.return_value.first.return_value = media_a
            return mock_res

        session.execute = AsyncMock(side_effect=fake_execute)
        yield session

    app.dependency_overrides[get_db] = override_db
    try:
        resp = client.post(
            f"/media/{media_b.id}/merge",
            json={"media_ids": ["my_file.mp4", "victim_file.mp4"]},
        )
        assert resp.status_code == 403
        assert "Cannot reference media belonging to another user" in resp.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)
