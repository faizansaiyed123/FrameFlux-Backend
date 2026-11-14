from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.security import create_access_token, decode_access_token
from app.features.demo import routes as demo_routes
from app.features.demo.service import hash_client_ip
from app.main import app


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


def test_demo_bootstrap_is_disabled_when_the_feature_flag_is_off(monkeypatch):
    monkeypatch.setattr(demo_routes.settings, "demo_enabled", False)
    client = TestClient(app)

    response = client.post("/demo/session")

    assert response.status_code == 404
    assert response.json()["detail"] == "Demo mode is unavailable"
