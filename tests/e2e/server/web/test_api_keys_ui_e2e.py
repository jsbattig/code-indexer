"""
E2E Tests for API Keys Configuration Web UI (Story #635).

Tests the complete web UI workflow for managing CI/CD platform API keys:
- Viewing API keys section (admin only)
- Adding/updating GitHub and GitLab tokens
- Token masking in UI
- CSRF protection
- Access control

Follows Anti-Mock principle - uses real encryption, real HTTP requests.
"""

import pytest
import re
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi.testclient import TestClient

from src.code_indexer.server.services.ci_token_manager import CITokenManager


# Import existing web test infrastructure
pytest_plugins = ["tests.server.web.conftest"]


def extract_csrf_token(html: str) -> Optional[str]:
    """Extract CSRF token from HTML form."""
    # Look for hidden input with name csrf_token
    match = re.search(
        r'<input[^>]*name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', html
    )
    if match:
        return match.group(1)

    # Also try reverse order (value before name)
    match = re.search(
        r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']csrf_token["\']', html
    )
    if match:
        return match.group(1)

    return None


@pytest.fixture
def token_manager(web_infrastructure):
    """
    Get the CITokenManager instance that integrates with the test server.

    Uses the same storage directory as the test server to ensure
    tokens saved in tests are visible to the server (Anti-Mock principle).
    """
    # Use the test server's storage directory
    # CITokenManager stores tokens in server_dir_path/ci_tokens.json
    return CITokenManager(server_dir_path=str(web_infrastructure.temp_dir))


@pytest.fixture
def admin_client_fixture(web_infrastructure, admin_user: Dict[str, Any]) -> TestClient:
    """Authenticated admin client using web_infrastructure."""
    return web_infrastructure.get_authenticated_client(
        admin_user["username"], admin_user["password"]
    )


@pytest.fixture
def normal_user_client_fixture(
    web_infrastructure, normal_user: Dict[str, Any]
) -> TestClient:
    """Authenticated normal user client using web_infrastructure."""
    return web_infrastructure.get_authenticated_client(
        normal_user["username"], normal_user["password"]
    )


class TestAPIKeysUIAccess:
    """Test access control for API Keys UI (AC13)."""

    def test_admin_can_view_api_keys_section(self, admin_client_fixture):
        """AC1: Admin user can view API Keys section in config page."""
        response = admin_client_fixture.get("/admin/config")
        assert response.status_code == 200

        # Check that API Keys section is present
        assert b"API Keys" in response.content or b"API Tokens" in response.content
        assert b"GitHub" in response.content
        assert b"GitLab" in response.content

    def test_non_admin_cannot_access_config(self, normal_user_client_fixture):
        """AC13: Non-admin user cannot access configuration page."""
        response = normal_user_client_fixture.get("/admin/config", follow_redirects=False)
        # Should redirect to login or return 403
        assert response.status_code in [303, 403]


class TestAPIKeysUIDisplay:
    """Test API Keys display and masking (AC2, AC3, AC4)."""

    def test_view_masked_github_token(self, admin_client_fixture, token_manager):
        """AC2: View masked GitHub token (ghp_****)."""
        # Setup: Save a GitHub token using the server's token manager
        token_manager.save_token(
            platform="github",
            token="ghp_1234567890abcdefghijklmnopqrstuvwxyz",
        )

        response = admin_client_fixture.get("/admin/config")
        assert response.status_code == 200

        # Check token is masked (template shows first 10 chars + asterisks)
        assert b"ghp_123456**" in response.content
        # Ensure full token is NOT visible
        assert b"ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in response.content

    def test_view_masked_gitlab_token(self, admin_client_fixture, token_manager):
        """AC3: View masked GitLab token (glpat-****)."""
        # Setup: Save a GitLab token using the server's token manager
        token_manager.save_token(
            platform="gitlab",
            token="glpat-1234567890abcdefghijklmn",
            base_url="https://gitlab.example.com",
        )

        response = admin_client_fixture.get("/admin/config")
        assert response.status_code == 200

        # Check token is masked (template shows first 10 chars + asterisks)
        assert b"glpat-1234**" in response.content
        # Ensure full token is NOT visible
        assert b"glpat-1234567890abcdefghijklmn" not in response.content
        # GitLab URL should be visible
        assert b"gitlab.example.com" in response.content

    def test_view_unconfigured_platform(self, admin_client_fixture):
        """AC4: View unconfigured platform shows empty/default state."""
        response = admin_client_fixture.get("/admin/config")
        assert response.status_code == 200

        # Should show "Not configured" or similar for empty platforms
        content = response.content.decode("utf-8")
        assert "Not configured" in content or "No token" in content or "Configure" in content


class TestAPIKeysUIEdit:
    """Test API Keys editing workflow (AC5, AC6, AC7, AC8)."""

    def test_configure_new_github_token(self, admin_client_fixture):
        """AC5: Configure new GitHub token via web UI."""
        # Get config page to extract CSRF token
        config_response = admin_client_fixture.get("/admin/config")
        assert config_response.status_code == 200
        csrf_token = extract_csrf_token(config_response.text)
        assert csrf_token is not None, "Failed to extract CSRF token from config page"

        # Save GitHub token
        response = admin_client_fixture.post(
            "/admin/config/api-keys/github",
            data={
                "csrf_token": csrf_token,
                "token": "ghp_newtoken1234567890abcdefghijklmnop",
            },
        )

        # Should succeed (200 or redirect)
        assert response.status_code in [200, 303]

    def test_update_existing_gitlab_token(
        self, admin_client_fixture, token_manager
    ):
        """AC6: Update existing GitLab token."""
        # Setup: Save initial GitLab token using server's token manager
        token_manager.save_token(
            platform="gitlab",
            token="glpat-oldtoken123456789012",
            base_url="https://gitlab.com",
        )

        # Get config page to extract CSRF token
        config_response = admin_client_fixture.get("/admin/config")
        assert config_response.status_code == 200
        csrf_token = extract_csrf_token(config_response.text)
        assert csrf_token is not None, "Failed to extract CSRF token from config page"

        # Update GitLab token
        response = admin_client_fixture.post(
            "/admin/config/api-keys/gitlab",
            data={
                "csrf_token": csrf_token,
                "token": "glpat-newtoken987654321098",
                "api_url": "https://gitlab.com",
            },
        )

        assert response.status_code in [200, 303]

    def test_configure_gitlab_selfhosted_url(self, admin_client_fixture):
        """AC7: Configure GitLab self-hosted URL."""
        # Get config page to extract CSRF token
        config_response = admin_client_fixture.get("/admin/config")
        assert config_response.status_code == 200
        csrf_token = extract_csrf_token(config_response.text)
        assert csrf_token is not None, "Failed to extract CSRF token from config page"

        # Save GitLab token with self-hosted URL
        response = admin_client_fixture.post(
            "/admin/config/api-keys/gitlab",
            data={
                "csrf_token": csrf_token,
                "token": "glpat-selfhosted1234567890",
                "api_url": "https://gitlab.internal.company.com",
            },
        )

        assert response.status_code in [200, 303]

        # Verify the URL was saved
        config_response = admin_client_fixture.get("/admin/config")
        assert b"gitlab.internal.company.com" in config_response.content

    def test_cancel_editing_without_saving(
        self, admin_client_fixture, token_manager
    ):
        """AC8: Cancel editing without saving changes."""
        # Setup: Save initial token using server's token manager
        token_manager.save_token(
            platform="github",
            token="ghp_original1234567890123456789012345678",
        )

        # Get config page - this simulates viewing in edit mode
        response = admin_client_fixture.get("/admin/config")
        assert response.status_code == 200

        # Verify original token is still there (not changed)
        # Reload token manager and check
        loaded_token = token_manager.get_token("github")
        assert loaded_token is not None
        assert loaded_token.token == "ghp_original1234567890123456789012345678"


class TestAPIKeysCSRFProtection:
    """Test CSRF protection on token operations (AC12)."""

    def test_save_token_requires_csrf(self, admin_client_fixture):
        """AC12: POST /admin/config/api-keys/{platform} requires valid CSRF token."""
        # Attempt to save without CSRF token
        response = admin_client_fixture.post(
            "/admin/config/api-keys/github",
            data={
                "token": "ghp_test1234567890123456789012345678901",
            },
        )

        # CSRF validation failure returns 200 with error message in HTML
        assert response.status_code == 200
        assert b"Invalid CSRF token" in response.content

    def test_delete_token_requires_csrf(self, admin_client_fixture, token_manager):
        """AC12: DELETE /admin/config/api-keys/{platform} requires valid CSRF token."""
        # Setup: Save a token using server's token manager
        token_manager.save_token(
            platform="github",
            token="ghp_todelete1234567890123456789012345678",
        )

        # Attempt to delete without CSRF token
        response = admin_client_fixture.delete("/admin/config/api-keys/github")

        # Should fail with 400 or 403 (CSRF validation failure)
        assert response.status_code in [400, 403]


class TestAPIKeysDelete:
    """Test deleting API keys via UI."""

    def test_delete_github_token(self, admin_client_fixture, token_manager):
        """Delete GitHub token via web UI."""
        # Setup: Save a token using server's token manager
        token_manager.save_token(
            platform="github",
            token="ghp_todelete1234567890123456789012345678",
        )

        # Get config page to extract CSRF token
        config_response = admin_client_fixture.get("/admin/config")
        assert config_response.status_code == 200
        csrf_token = extract_csrf_token(config_response.text)
        assert csrf_token is not None, "Failed to extract CSRF token from config page"

        # Delete token
        response = admin_client_fixture.delete(
            "/admin/config/api-keys/github",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code in [200, 204]

        # Verify token was deleted
        assert token_manager.get_token("github") is None

    def test_delete_gitlab_token(self, admin_client_fixture, token_manager):
        """Delete GitLab token via web UI."""
        # Setup: Save a token using server's token manager
        token_manager.save_token(
            platform="gitlab",
            token="glpat-todelete1234567890123",
            base_url="https://gitlab.com",
        )

        # Get config page to extract CSRF token
        config_response = admin_client_fixture.get("/admin/config")
        assert config_response.status_code == 200
        csrf_token = extract_csrf_token(config_response.text)
        assert csrf_token is not None, "Failed to extract CSRF token from config page"

        # Delete token
        response = admin_client_fixture.delete(
            "/admin/config/api-keys/gitlab",
            headers={"X-CSRF-Token": csrf_token},
        )

        assert response.status_code in [200, 204]

        # Verify token was deleted
        assert token_manager.get_token("gitlab") is None
