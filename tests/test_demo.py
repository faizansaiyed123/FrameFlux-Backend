from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from starlette.requests import Request

from app.core.security import create_access_token, decode_access_token
from app.features.demo import routes as demo_routes
from app.features.demo.service import hash_client_ip
from app.features.media.resumable_service import ResumableUploadService
from app.main import app


client = TestClient(app)


def _request_with_headers(headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/demo/session",
            "raw_path": b"/demo/session",
            "query_string": b"",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in (headers or {}).items()
            ],
            "client": ("100.64.0.10", 12345),
            "server": ("frameflux.example", 443),
            "root_path": "",
        }
    )


def test_demo_ip_hash_is_stable_and_not_the_raw_address():
    address = "203.0.113.10"
    first = hash_client_ip(address)
    second = hash_client_ip(address)

    assert first == second
    assert len(first) == 64
    assert first != address
    assert address not in first


def test_demo_access_token_has_the_session_claim_and_requested_expiry():
    user_id = uuid4()
    session_id = uuid4()

    token = create_access_token(
        user_id,
        extra_claims={"demo_session_id": str(session_id)},
        expires_minutes=120,
    )
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["demo_session_id"] == str(session_id)
    assert payload["type"] == "access"
    assert 7199 <= payload["exp"] - payload["iat"] <= 7200


def test_demo_uses_railway_x_real_ip_and_ignores_forwarded_for(monkeypatch):
    monkeypatch.setattr(demo_routes.settings, "trust_railway_x_real_ip", True)
    monkeypatch.setattr(demo_routes.settings, "trust_proxy_headers", True)
    request = _request_with_headers(
        {
            "x-real-ip": "203.0.113.10",
            "x-forwarded-for": "198.51.100.22",
        }
    )

    assert demo_routes._client_ip(request) == "203.0.113.10"


def test_demo_railway_mode_does_not_fall_back_to_untrusted_forwarded_for(monkeypatch):
    monkeypatch.setattr(demo_routes.settings, "trust_railway_x_real_ip", True)
    monkeypatch.setattr(demo_routes.settings, "trust_proxy_headers", True)
    request = _request_with_headers(
        {
            "x-forwarded-for": "198.51.100.22",
        }
    )

    assert demo_routes._client_ip(request) == "100.64.0.10"


def test_demo_railway_mode_rejects_invalid_real_ip(monkeypatch):
    monkeypatch.setattr(demo_routes.settings, "trust_railway_x_real_ip", True)
    request = _request_with_headers(
        {
            "x-real-ip": "not-an-ip",
            "x-forwarded-for": "198.51.100.22",
        }
    )

    assert demo_routes._client_ip(request) == "100.64.0.10"


def test_demo_bootstrap_is_disabled_when_the_feature_flag_is_off(monkeypatch):
    monkeypatch.setattr(demo_routes.settings, "demo_enabled", False)
    client = TestClient(app)

    response = client.post("/demo/session")

    assert response.status_code == 404
    assert response.json()["detail"] == "Demo mode is unavailable"


def test_resumable_chunk_rejects_a_size_that_does_not_match_metadata(monkeypatch, tmp_path):
    upload_id = uuid4()
    user_id = uuid4()

    async def fake_load_meta(requested_upload_id, user_id=None):
        assert requested_upload_id == upload_id
        assert user_id == user_id_arg
        return {
            "status": "in_progress",
            "total_size": "10",
            "chunk_size": "4",
            "uploaded_chunks": "",
            "user_id": str(user_id_arg),
        }

    user_id_arg = user_id
    monkeypatch.setattr(
        ResumableUploadService,
        "_load_meta",
        staticmethod(fake_load_meta),
    )

    import asyncio

    with pytest.raises(ValueError, match="exactly 4 bytes"):
        asyncio.run(
            ResumableUploadService.store_chunk(
                upload_id,
                index=0,
                data=b"bad",
                user_id=user_id,
            )
        )


def test_resumable_chunk_rejects_indexes_outside_declared_upload(monkeypatch):
    upload_id = uuid4()
    user_id = uuid4()

    async def fake_load_meta(requested_upload_id, user_id=None):
        return {
            "status": "in_progress",
            "total_size": "10",
            "chunk_size": "4",
            "uploaded_chunks": "",
            "user_id": str(user_id),
        }

    monkeypatch.setattr(
        ResumableUploadService,
        "_load_meta",
        staticmethod(fake_load_meta),
    )

    import asyncio

    with pytest.raises(ValueError, match="outside the declared upload size"):
        asyncio.run(
            ResumableUploadService.store_chunk(
                upload_id,
                index=3,
                data=b"x",
                user_id=user_id,
            )
        )
