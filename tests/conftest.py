import pytest
from uuid import uuid4

from app.main import app
from app.features.auth.dependencies import get_current_active_user, get_current_user
from app.features.auth.models import User

TEST_MOCK_USER_ID = uuid4()
TEST_MOCK_USER = User(
    id=TEST_MOCK_USER_ID,
    email="test@frameflux.local",
    password_hash="mock_hash",
    full_name="Mock User",
    is_active=True,
)


@pytest.fixture(autouse=True)
def default_auth_for_legacy_tests(request):
    """
    Ensure existing tests in legacy test suites run with a default mock active user,
    while auth and authorization test suites test unauthenticated and multi-user behavior.
    """
    if request.module.__name__ in ("tests.test_auth", "tests.test_authorization"):
        yield
        return

    app.dependency_overrides[get_current_active_user] = lambda: TEST_MOCK_USER
    app.dependency_overrides[get_current_user] = lambda: TEST_MOCK_USER
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)
        app.dependency_overrides.pop(get_current_user, None)
