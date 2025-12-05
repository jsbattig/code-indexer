"""Integration tests for API Keys web UI page."""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


class TestApiKeysPage:
    """Tests for the API Keys web page."""

    def test_api_keys_page_requires_auth(
        self,
        web_infrastructure: WebTestInfrastructure
    ):
        """Test that unauthenticated users are redirected to login."""
        client = web_infrastructure.client
        response = client.get("/admin/api-keys", follow_redirects=False)
        assert response.status_code in [302, 303]
        assert "/admin/login" in response.headers.get("location", "")

    def test_api_keys_page_renders_for_authenticated_user(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """Test that authenticated users can access the page."""
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )
        response = client.get("/admin/api-keys")
        assert response.status_code == 200
        assert "API Key Management" in response.text
        assert "Generate New Key" in response.text

    def test_api_keys_page_shows_empty_state(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """Test that page shows message when no keys exist."""
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )
        response = client.get("/admin/api-keys")
        assert response.status_code == 200
        assert "No API keys found" in response.text

    def test_api_keys_partial_requires_auth(
        self,
        web_infrastructure: WebTestInfrastructure
    ):
        """Test that partial endpoint requires authentication."""
        client = web_infrastructure.client
        response = client.get("/admin/partials/api-keys-list")
        assert response.status_code == 401

    def test_api_keys_partial_works_authenticated(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """Test that partial endpoint works when authenticated."""
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )
        response = client.get("/admin/partials/api-keys-list")
        assert response.status_code == 200


class TestApiKeysNavigation:
    """Tests for API Keys navigation link."""

    def test_api_keys_link_in_navigation(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """Test that API Keys link appears in navigation."""
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )
        response = client.get("/admin/")
        assert response.status_code == 200
        assert 'href="/admin/api-keys"' in response.text
        assert "API Keys" in response.text
