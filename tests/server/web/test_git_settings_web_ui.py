"""
Tests for Git Settings Web UI.

Tests the /admin/settings/git web page route and template.
"""

from fastapi import status
from fastapi.testclient import TestClient


def test_git_settings_page_requires_authentication(web_client: TestClient):
    """Test that /admin/settings/git requires authentication."""
    response = web_client.get("/admin/settings/git", follow_redirects=False)

    # Should redirect to login page
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert response.headers["location"] == "/user/login"


def test_git_settings_page_renders_template(authenticated_client: TestClient):
    """Test that /admin/settings/git renders the git_settings.html template."""
    response = authenticated_client.get("/admin/settings/git")

    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]

    # Check for expected template elements
    html = response.text
    assert "Git Settings" in html or "git settings" in html.lower()
    assert "default_committer_email" in html


def test_git_settings_page_displays_current_config(authenticated_client: TestClient):
    """Test that the page displays current git service configuration."""
    response = authenticated_client.get("/admin/settings/git")

    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Should display service committer info (read-only)
    assert "service_committer_name" in html or "Service Committer Name" in html
    assert "service_committer_email" in html or "Service Committer Email" in html

    # Should have input/form for default_committer_email
    assert "default_committer_email" in html
    assert '<form' in html or 'input' in html


def test_git_settings_page_includes_csrf_token(authenticated_client: TestClient):
    """Test that the page includes a CSRF token for form submission."""
    response = authenticated_client.get("/admin/settings/git")

    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Should include CSRF token (either in hidden input or for JS)
    assert "csrf_token" in html or "csrf-token" in html

    # Should set CSRF cookie
    csrf_cookie_found = any(
        cookie.name == "_csrf" for cookie in response.cookies.jar
    )
    assert csrf_cookie_found, "CSRF cookie not set in response"


def test_git_settings_page_uses_config_manager(authenticated_client: TestClient):
    """Test that the page fetches configuration from ConfigManager."""
    from code_indexer.config import ConfigManager

    # Get current config to verify the page displays it
    config_manager = ConfigManager()
    config = config_manager.load()
    git_config = config.git_service

    response = authenticated_client.get("/admin/settings/git")

    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Should display the actual configuration values
    assert git_config.service_committer_name in html
    assert git_config.service_committer_email in html

    # default_committer_email might be None, so check conditionally
    if git_config.default_committer_email:
        assert git_config.default_committer_email in html


def test_git_settings_page_shows_navigation(authenticated_client: TestClient):
    """Test that the page shows the admin navigation bar."""
    response = authenticated_client.get("/admin/settings/git")

    assert response.status_code == status.HTTP_200_OK
    html = response.text

    # Should extend base template with navigation
    # Check for common nav elements
    assert "Dashboard" in html or "dashboard" in html.lower()
