"""
Tests for user self-service API keys page.

Verifies that non-admin users can manage their own API keys through /user/api-keys.

Note: The REST API endpoints (/api/keys) are tested in test_global_tools.py.
These tests focus on the web UI routes which use session authentication.
"""

from typing import Dict, Any

from fastapi.testclient import TestClient

from tests.server.web.conftest import WebTestInfrastructure


class TestUserLogin:
    """Test /user/login endpoint for non-admin users."""

    def test_user_login_page_renders(self, web_client: TestClient):
        """Test that /user/login page renders successfully."""
        response = web_client.get("/user/login")

        assert response.status_code == 200
        assert "Login" in response.text
        assert "csrf_token" in response.text

    def test_user_login_accepts_normal_user(
        self, web_infrastructure: WebTestInfrastructure, normal_user: Dict[str, Any]
    ):
        """Test that normal_user can login via /user/login."""
        client = web_infrastructure.client
        assert client is not None  # Guaranteed by web_infrastructure fixture

        # Get login page and extract CSRF token
        login_response = client.get("/user/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_response.text)
        assert csrf_token is not None

        # Submit login
        login_data = {
            "username": normal_user["username"],
            "password": normal_user["password"],
            "csrf_token": csrf_token,
        }
        response = client.post("/user/login", data=login_data, follow_redirects=False)

        # Should redirect to /user/api-keys
        assert response.status_code == 303
        assert response.headers["location"] == "/user/api-keys"

        # Should have session cookie
        assert "session" in client.cookies

    def test_user_login_accepts_power_user(
        self, web_infrastructure: WebTestInfrastructure, power_user: Dict[str, Any]
    ):
        """Test that power_user can login via /user/login."""
        client = web_infrastructure.client
        assert client is not None  # Guaranteed by web_infrastructure fixture

        # Get login page and extract CSRF token
        login_response = client.get("/user/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_response.text)
        assert csrf_token is not None

        # Submit login
        login_data = {
            "username": power_user["username"],
            "password": power_user["password"],
            "csrf_token": csrf_token,
        }
        response = client.post("/user/login", data=login_data, follow_redirects=False)

        # Should redirect to /user/api-keys
        assert response.status_code == 303
        assert response.headers["location"] == "/user/api-keys"

    def test_user_login_accepts_admin(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """Test that admin can also login via /user/login."""
        client = web_infrastructure.client
        assert client is not None  # Guaranteed by web_infrastructure fixture

        # Get login page and extract CSRF token
        login_response = client.get("/user/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_response.text)
        assert csrf_token is not None

        # Submit login
        login_data = {
            "username": admin_user["username"],
            "password": admin_user["password"],
            "csrf_token": csrf_token,
        }
        response = client.post("/user/login", data=login_data, follow_redirects=False)

        # Should redirect to /user/api-keys
        assert response.status_code == 303
        assert response.headers["location"] == "/user/api-keys"

    def test_user_login_rejects_invalid_credentials(
        self, web_infrastructure: WebTestInfrastructure, normal_user: Dict[str, Any]
    ):
        """Test that invalid credentials show error message."""
        client = web_infrastructure.client
        assert client is not None  # Guaranteed by web_infrastructure fixture

        # Get login page and extract CSRF token
        login_response = client.get("/user/login")
        csrf_token = web_infrastructure.extract_csrf_token(login_response.text)
        assert csrf_token is not None

        # Submit with wrong password
        login_data = {
            "username": normal_user["username"],
            "password": "WrongPassword123!",
            "csrf_token": csrf_token,
        }
        response = client.post("/user/login", data=login_data, follow_redirects=False)

        # Should show error on same page
        assert response.status_code == 200
        assert "Invalid username or password" in response.text

    def test_user_login_requires_csrf_token(
        self, web_infrastructure: WebTestInfrastructure, normal_user: Dict[str, Any]
    ):
        """Test that login requires valid CSRF token."""
        client = web_infrastructure.client
        assert client is not None  # Guaranteed by web_infrastructure fixture

        # Try to submit without CSRF token
        login_data = {
            "username": normal_user["username"],
            "password": normal_user["password"],
        }
        response = client.post("/user/login", data=login_data, follow_redirects=False)

        # Should be rejected with 403
        assert response.status_code == 403


class TestUserApiKeysAccess:
    """Test access control for /user/api-keys page."""

    def test_api_keys_page_requires_authentication(self, web_client: TestClient):
        """Test that /user/api-keys returns 303 redirect without authentication."""
        response = web_client.get("/user/api-keys", follow_redirects=False)

        # Should redirect to user login (not admin login)
        assert response.status_code == 303
        assert response.headers["location"] == "/user/login"

    def test_api_keys_page_accessible_to_admin(self, authenticated_client: TestClient):
        """Test that admin can access /user/api-keys page."""
        response = authenticated_client.get("/user/api-keys")

        assert response.status_code == 200
        assert "API Key Management" in response.text

    def test_api_keys_page_accessible_to_normal_user(
        self, web_infrastructure: WebTestInfrastructure, normal_user: Dict[str, Any]
    ):
        """Test that normal_user can access /user/api-keys page."""
        client = web_infrastructure.get_authenticated_client(
            normal_user["username"], normal_user["password"]
        )
        response = client.get("/user/api-keys")
        assert response.status_code == 200
        assert "API Key Management" in response.text

    def test_api_keys_page_accessible_to_power_user(
        self, web_infrastructure: WebTestInfrastructure, power_user: Dict[str, Any]
    ):
        """Test that power_user can access /user/api-keys page."""
        client = web_infrastructure.get_authenticated_client(
            power_user["username"], power_user["password"]
        )
        response = client.get("/user/api-keys")
        assert response.status_code == 200
        assert "API Key Management" in response.text


class TestUserApiKeysPartial:
    """Test HTMX partial endpoint for API keys list."""

    def test_partial_requires_authentication(self, web_client: TestClient):
        """Test that partial returns 401 without authentication."""
        response = web_client.get("/user/partials/api-keys-list")

        assert response.status_code == 401
        assert "Session expired" in response.text

    def test_partial_accessible_to_authenticated_user(
        self, authenticated_client: TestClient
    ):
        """Test that authenticated user can access partial."""
        response = authenticated_client.get("/user/partials/api-keys-list")

        assert response.status_code == 200


class TestUserLogout:
    """Test user logout endpoint."""

    def test_user_logout_clears_session(self, authenticated_client: TestClient):
        """Test that /user/logout clears session and redirects."""
        response = authenticated_client.get("/user/logout", follow_redirects=False)

        # Should redirect to login
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

        # Session cookie should be cleared
        set_cookie_header = response.headers.get("set-cookie", "")
        assert (
            "Max-Age=0" in set_cookie_header or "expires" in set_cookie_header.lower()
        )
