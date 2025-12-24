"""
Real integration tests for password change security - NO MOCKS.

Following MESSI Rule #1: Zero mocks, real components only.
"""

import pytest
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import UserRole
from code_indexer.server.auth.rate_limiter import password_change_rate_limiter


@pytest.mark.e2e
class TestPasswordChangeSecurityReal:
    """Real integration tests with actual components."""

    @pytest.fixture(autouse=True)
    def reset_rate_limiter(self):
        """Reset rate limiter state between tests."""
        password_change_rate_limiter._attempts.clear()
        yield
        password_change_rate_limiter._attempts.clear()

    @pytest.fixture
    def test_db_path(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            db_path = tmp.name
            # Initialize with empty JSON object
            tmp.write(b"{}")
            tmp.flush()
        yield db_path
        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def real_app(self, test_db_path):
        """Create real FastAPI app with test database."""
        # Create temporary server data directory containing our test users file
        import tempfile

        temp_dir = tempfile.mkdtemp()
        users_file = Path(temp_dir) / "users.json"
        # Copy our test DB to the expected location
        import shutil

        shutil.copy2(test_db_path, users_file)

        # Set environment to use our temporary directory
        old_env = os.environ.get("CIDX_SERVER_DATA_DIR")
        os.environ["CIDX_SERVER_DATA_DIR"] = temp_dir

        try:
            app = create_app()
            yield app
        finally:
            # Restore environment
            if old_env is not None:
                os.environ["CIDX_SERVER_DATA_DIR"] = old_env
            else:
                os.environ.pop("CIDX_SERVER_DATA_DIR", None)
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def client(self, real_app):
        """Create test client with real app."""
        return TestClient(real_app)

    @pytest.fixture
    def test_user(self, real_app):
        """Create real test user in database."""
        from code_indexer.server.auth import dependencies

        user_manager = dependencies.user_manager
        user_manager.create_user(
            username="testuser", password="TestPassword123!", role=UserRole.NORMAL_USER
        )
        return user_manager.get_user("testuser")

    @pytest.fixture
    def auth_headers(self, client, test_user):
        """Get real authentication headers."""
        # Real login to get real JWT
        response = client.post(
            "/auth/login", json={"username": "testuser", "password": "TestPassword123!"}
        )
        if response.status_code != 200:
            print(f"Login failed: {response.status_code}, {response.text}")
        assert response.status_code == 200
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_password_change_with_correct_old_password(self, client, auth_headers):
        """Test successful password change with correct old password."""
        response = client.put(
            "/api/users/change-password",
            headers=auth_headers,
            json={
                "old_password": "TestPassword123!",
                "new_password": "NewPassword456!",
            },
        )
        assert response.status_code == 200
        assert "successfully" in response.json()["message"]

    def test_password_change_with_wrong_old_password(self, client, auth_headers):
        """Test password change fails with wrong old password."""
        response = client.put(
            "/api/users/change-password",
            headers=auth_headers,
            json={"old_password": "WrongPassword", "new_password": "NewPassword456!"},
        )
        assert response.status_code == 401
        assert "Invalid old password" in response.json()["detail"]

    def test_rate_limiting_after_multiple_failures(self, client, auth_headers):
        """Test rate limiting triggers after 5 failed attempts."""
        # First 4 attempts should return 401
        for i in range(4):
            response = client.put(
                "/api/users/change-password",
                headers=auth_headers,
                json={
                    "old_password": f"WrongPassword{i}",
                    "new_password": "NewPassword456!",
                },
            )
            assert response.status_code == 401, f"Attempt {i+1} should return 401"

        # 5th attempt should trigger rate limiting
        response = client.put(
            "/api/users/change-password",
            headers=auth_headers,
            json={"old_password": "WrongPassword5", "new_password": "NewPassword456!"},
        )
        assert response.status_code == 429, "5th attempt should trigger rate limiting"
        assert "Too many failed attempts" in response.json()["detail"]

        # Subsequent attempts should also be rate limited
        response = client.put(
            "/api/users/change-password",
            headers=auth_headers,
            json={"old_password": "WrongPassword6", "new_password": "NewPassword456!"},
        )
        assert response.status_code == 429, "6th attempt should still be rate limited"
