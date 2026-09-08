from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.features.auth.models import User
from app.features.auth.schemas import UserResponse
from app.infrastructure.database import get_db
from app.infrastructure.redis import get_redis
from app.main import app

settings = get_settings()


class MockSession:
    """In-memory mock session supporting the queries used by auth service."""

    def __init__(self, initial_users: list[User] | None = None) -> None:
        self.users: dict[UUID, User] = {}
        if initial_users:
            for u in initial_users:
                self.users[u.id] = u

    async def execute(self, stmt):
        params = stmt.compile().params
        matched = None
        for v in params.values():
            if isinstance(v, str):
                v_lower = v.lower()
                for u in self.users.values():
                    if u.email.lower() == v_lower:
                        matched = u
                        break
            elif isinstance(v, UUID) and v in self.users:
                matched = self.users[v]
                break

        res = MagicMock()
        res.scalar_one_or_none.return_value = matched
        return res

    def add(self, user: User) -> None:
        if not getattr(user, "id", None):
            user.id = uuid4()
        if not getattr(user, "created_at", None):
            user.created_at = datetime.now(timezone.utc)
        if not getattr(user, "updated_at", None):
            user.updated_at = datetime.now(timezone.utc)
        self.users[user.id] = user

    async def commit(self) -> None:
        pass

    async def refresh(self, user: User) -> None:
        pass


class MockRedis:
    """In-memory mock redis client."""

    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.storage[key] = str(value)
        return True

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self.storage:
                del self.storage[k]
                count += 1
        return count

    async def aclose(self) -> None:
        pass


@pytest.fixture
def auth_env():
    """Sets up fresh in-memory database and redis mock for each test."""
    mock_db = MockSession()
    mock_redis = MockRedis()

    async def override_db():
        yield mock_db

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis

    client = TestClient(app)
    yield client, mock_db, mock_redis

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)


# --------------------------------------------------------------------------
# 1. SIGNUP TESTS
# --------------------------------------------------------------------------


def test_signup_success(auth_env) -> None:
    client, mock_db, _ = auth_env
    response = client.post(
        "/auth/signup",
        json={
            "email": "alice@example.com",
            "password": "SecurePassword123!",
            "full_name": "Alice Wonderland",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "alice@example.com"
    assert data["full_name"] == "Alice Wonderland"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "password_hash" not in data

    # Verify user exists in database with Argon2 hash
    user_id = UUID(data["id"])
    saved_user = mock_db.users[user_id]
    assert saved_user.email == "alice@example.com"
    assert saved_user.password_hash.startswith("$argon2id$")
    assert verify_password("SecurePassword123!", saved_user.password_hash)


def test_duplicate_signup(auth_env) -> None:
    client, _, _ = auth_env
    payload = {
        "email": "duplicate@example.com",
        "password": "Password12345",
        "full_name": "First User",
    }

    # Initial registration
    first_res = client.post("/auth/signup", json=payload)
    assert first_res.status_code == 201

    # Duplicate registration with same email
    dup_res = client.post("/auth/signup", json=payload)
    assert dup_res.status_code == 409
    assert "already registered" in dup_res.json()["detail"].lower()

    # Case-insensitive duplicate check
    case_dup_res = client.post(
        "/auth/signup",
        json={
            "email": "DUPLICATE@EXAMPLE.COM",
            "password": "DifferentPassword123",
            "full_name": "Case User",
        },
    )
    assert case_dup_res.status_code == 409
    assert "already registered" in case_dup_res.json()["detail"].lower()


# --------------------------------------------------------------------------
# 2. LOGIN TESTS
# --------------------------------------------------------------------------


def test_login_success(auth_env) -> None:
    client, _, _ = auth_env
    # First sign up
    client.post(
        "/auth/signup",
        json={"email": "loginuser@example.com", "password": "Password123!", "full_name": "Login User"},
    )

    # Login
    response = client.post(
        "/auth/login",
        json={"email": "loginuser@example.com", "password": "Password123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == settings.jwt_expire_minutes * 60

    # Verify token payload
    payload = decode_access_token(data["access_token"])
    assert payload["type"] == "access"
    assert "sub" in payload
    assert "exp" in payload
    assert "jti" in payload


def test_invalid_login(auth_env) -> None:
    client, mock_db, _ = auth_env
    # Sign up active user
    client.post(
        "/auth/signup",
        json={"email": "valid@example.com", "password": "CorrectPassword1", "full_name": "Valid"},
    )

    # 1. Wrong password
    res_wrong_pw = client.post(
        "/auth/login",
        json={"email": "valid@example.com", "password": "WrongPassword99"},
    )
    assert res_wrong_pw.status_code == 401
    assert "invalid email or password" in res_wrong_pw.json()["detail"].lower()

    # 2. Non-existent email
    res_no_user = client.post(
        "/auth/login",
        json={"email": "unknown@example.com", "password": "AnyPassword123"},
    )
    assert res_no_user.status_code == 401
    assert "invalid email or password" in res_no_user.json()["detail"].lower()

    # Error message must be identical so existence is not revealed
    assert res_wrong_pw.json()["detail"] == res_no_user.json()["detail"]

    # 3. Inactive user
    inactive_user = User(
        id=uuid4(),
        email="inactive@example.com",
        password_hash=hash_password("Password123"),
        full_name="Inactive User",
        is_active=False,
    )
    mock_db.add(inactive_user)

    res_inactive = client.post(
        "/auth/login",
        json={"email": "inactive@example.com", "password": "Password123"},
    )
    assert res_inactive.status_code == 401
    assert "invalid email or password" in res_inactive.json()["detail"].lower()


# --------------------------------------------------------------------------
# 3. GET /AUTH/ME TESTS
# --------------------------------------------------------------------------


def test_get_me_success(auth_env) -> None:
    client, _, _ = auth_env
    signup_res = client.post(
        "/auth/signup",
        json={"email": "me_user@example.com", "password": "Password123!", "full_name": "Me User"},
    )
    user_id = signup_res.json()["id"]

    login_res = client.post(
        "/auth/login",
        json={"email": "me_user@example.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id
    assert data["email"] == "me_user@example.com"
    assert data["full_name"] == "Me User"
    assert data["is_active"] is True
    assert "password_hash" not in data


def test_missing_invalid_expired_token(auth_env) -> None:
    client, mock_db, _ = auth_env
    # 1. Missing token
    res_missing = client.get("/auth/me")
    assert res_missing.status_code == 401

    # 2. Invalid/malformed token
    res_invalid = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )
    assert res_invalid.status_code == 401
    assert "invalid" in res_invalid.json()["detail"].lower()

    # 3. Expired token
    expired_user_id = uuid4()
    mock_db.add(
        User(
            id=expired_user_id,
            email="expired@example.com",
            password_hash=hash_password("Password123"),
            is_active=True,
        )
    )
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(expired_user_id),
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
        "jti": "expired_jti",
        "type": "access",
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    res_expired = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401
    assert "expired" in res_expired.json()["detail"].lower()


# --------------------------------------------------------------------------
# 4. LOGOUT TESTS
# --------------------------------------------------------------------------


def test_logout_and_revocation(auth_env) -> None:
    client, _, mock_redis = auth_env
    client.post(
        "/auth/signup",
        json={"email": "logout@example.com", "password": "Password123!", "full_name": "Logout User"},
    )
    login_res = client.post(
        "/auth/login",
        json={"email": "logout@example.com", "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    # Verify access before logout
    pre_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert pre_res.status_code == 200

    # Logout
    logout_res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_res.status_code == 200
    assert "logged out" in logout_res.json()["detail"].lower()

    # Verify token is stored in Redis blocklist
    payload = decode_access_token(token)
    jti = payload["jti"]
    assert f"token:blocklist:{jti}" in mock_redis.storage

    # Verify access is rejected after logout
    post_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert post_res.status_code == 401
    assert "revoked" in post_res.json()["detail"].lower()


# --------------------------------------------------------------------------
# 5. FORGOT & RESET PASSWORD TESTS
# --------------------------------------------------------------------------


def test_forgot_password_generic_response(auth_env) -> None:
    client, _, mock_redis = auth_env
    # Sign up existing user
    client.post(
        "/auth/signup",
        json={"email": "existing@example.com", "password": "Password123!", "full_name": "Existing"},
    )

    # 1. Existing user
    res_existing = client.post(
        "/auth/forgot-password",
        json={"email": "existing@example.com"},
    )
    assert res_existing.status_code == 200
    assert "if this email is registered" in res_existing.json()["detail"].lower()

    # Verify token stored in Redis
    reset_keys = [k for k in mock_redis.storage.keys() if k.startswith("pwd_reset:")]
    assert len(reset_keys) == 1

    # 2. Non-existent user
    mock_redis.storage.clear()
    res_unknown = client.post(
        "/auth/forgot-password",
        json={"email": "unknown@example.com"},
    )
    assert res_unknown.status_code == 200
    # Must not reveal whether email exists
    assert res_unknown.json()["detail"] == res_existing.json()["detail"]
    assert len(mock_redis.storage) == 0


def test_reset_password_success_and_reused_token(auth_env) -> None:
    client, mock_db, mock_redis = auth_env
    # Sign up user
    client.post(
        "/auth/signup",
        json={"email": "reset_me@example.com", "password": "OldPassword123!", "full_name": "Reset Me"},
    )

    # Request reset
    client.post("/auth/forgot-password", json={"email": "reset_me@example.com"})
    reset_key = [k for k in mock_redis.storage.keys() if k.startswith("pwd_reset:")][0]
    token = reset_key.replace("pwd_reset:", "")

    # Reset password with valid token
    res_reset = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "NewSecurePassword1!"},
    )
    assert res_reset.status_code == 200
    assert "reset successfully" in res_reset.json()["detail"].lower()

    # Verify old password no longer works for login
    old_login = client.post(
        "/auth/login",
        json={"email": "reset_me@example.com", "password": "OldPassword123!"},
    )
    assert old_login.status_code == 401

    # Verify new password works for login
    new_login = client.post(
        "/auth/login",
        json={"email": "reset_me@example.com", "password": "NewSecurePassword1!"},
    )
    assert new_login.status_code == 200

    # REUSED RESET TOKEN TEST:
    # Attempt to use the same token again
    reuse_res = client.post(
        "/auth/reset-password",
        json={"token": token, "new_password": "AnotherPassword99!"},
    )
    assert reuse_res.status_code == 400
    assert "invalid or expired" in reuse_res.json()["detail"].lower()


def test_expired_reset_token(auth_env) -> None:
    client, _, _ = auth_env
    response = client.post(
        "/auth/reset-password",
        json={"token": "non_existent_or_expired_token", "new_password": "NewPassword123!"},
    )
    assert response.status_code == 400
    assert "invalid or expired" in response.json()["detail"].lower()


# --------------------------------------------------------------------------
# 6. CHANGE PASSWORD TESTS
# --------------------------------------------------------------------------


def test_change_password_success(auth_env) -> None:
    client, _, _ = auth_env
    # Sign up and login
    client.post(
        "/auth/signup",
        json={"email": "changer@example.com", "password": "CurrentPassword1!", "full_name": "Changer"},
    )
    login_res = client.post(
        "/auth/login",
        json={"email": "changer@example.com", "password": "CurrentPassword1!"},
    )
    token = login_res.json()["access_token"]

    # Change password
    change_res = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "CurrentPassword1!",
            "new_password": "BrandNewPassword1!",
        },
    )
    assert change_res.status_code == 200
    assert "changed successfully" in change_res.json()["detail"].lower()

    # Old password fails
    fail_login = client.post(
        "/auth/login",
        json={"email": "changer@example.com", "password": "CurrentPassword1!"},
    )
    assert fail_login.status_code == 401

    # New password succeeds
    ok_login = client.post(
        "/auth/login",
        json={"email": "changer@example.com", "password": "BrandNewPassword1!"},
    )
    assert ok_login.status_code == 200


def test_change_password_incorrect_current(auth_env) -> None:
    client, _, _ = auth_env
    client.post(
        "/auth/signup",
        json={"email": "wrong_curr@example.com", "password": "RealPassword123!", "full_name": "Test"},
    )
    login_res = client.post(
        "/auth/login",
        json={"email": "wrong_curr@example.com", "password": "RealPassword123!"},
    )
    token = login_res.json()["access_token"]

    # Attempt change with wrong current password
    bad_change = client.post(
        "/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "current_password": "WrongCurrentPassword!",
            "new_password": "NewValidPassword123!",
        },
    )
    assert bad_change.status_code == 400
    assert "incorrect current password" in bad_change.json()["detail"].lower()

    # Verify original password still works
    login_check = client.post(
        "/auth/login",
        json={"email": "wrong_curr@example.com", "password": "RealPassword123!"},
    )
    assert login_check.status_code == 200


# --------------------------------------------------------------------------
# 7. SECURITY & PASSWORD HASH EXPOSURE TESTS
# --------------------------------------------------------------------------


def test_password_hash_not_exposed(auth_env) -> None:
    client, _, _ = auth_env
    # Schema check: UserResponse must never contain password_hash field
    assert "password_hash" not in UserResponse.model_fields

    # Response check on signup
    signup_res = client.post(
        "/auth/signup",
        json={"email": "privacy@example.com", "password": "Password123!", "full_name": "Privacy"},
    )
    assert signup_res.status_code == 201
    assert "password_hash" not in signup_res.json()
    assert "password" not in signup_res.json()

    # Response check on login
    login_res = client.post(
        "/auth/login",
        json={"email": "privacy@example.com", "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    assert "password_hash" not in login_res.json()

    # Response check on /auth/me
    me_res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    assert "password_hash" not in me_res.json()
    assert "password" not in me_res.json()

    # Message responses must not contain password hash
    logout_res = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert "password_hash" not in logout_res.json()
