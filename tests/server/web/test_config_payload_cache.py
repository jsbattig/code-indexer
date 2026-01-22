"""
Tests for Payload Cache Configuration Web UI (Story #679).

Tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


class TestPayloadCacheConfigDisplay:
    """Tests for payload cache configuration display in web UI."""

    def test_payload_cache_fields_displayed(self, authenticated_client: TestClient):
        """
        Payload cache fields should be displayed in Cache Settings section.

        Given I am authenticated as an admin
        When I view the config page
        Then I see Payload Cache fields: Preview Size, Max Fetch Size, Cache TTL, Cleanup Interval
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check payload cache display labels
        assert (
            "payload preview size" in text_lower
        ), "Should show Payload Preview Size field"
        assert (
            "payload max fetch size" in text_lower
        ), "Should show Payload Max Fetch Size field"
        assert "payload cache ttl" in text_lower, "Should show Payload Cache TTL field"
        assert (
            "payload cleanup interval" in text_lower
        ), "Should show Payload Cleanup Interval field"

    def test_payload_cache_default_values_displayed(
        self, authenticated_client: TestClient
    ):
        """
        Payload cache fields should show default values.

        Given I am authenticated as an admin
        When I view the config page
        Then I see payload cache default values: 2000, 5000, 900, 60
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200

        # Check default values are present
        # Note: values might be different if config has been modified,
        # but we check for presence of numeric inputs
        assert "2000" in response.text, "Should show default preview size (2000)"
        assert "5000" in response.text, "Should show default max fetch size (5000)"
        assert "900" in response.text, "Should show default cache TTL (900)"
        assert "60" in response.text, "Should show default cleanup interval (60)"


class TestPayloadCacheConfigEditing:
    """Tests for payload cache configuration editing in web UI."""

    def test_payload_cache_form_fields_exist(self, authenticated_client: TestClient):
        """
        Payload cache edit form should have all required fields.

        Given I am authenticated as an admin
        When I view the config page
        Then I see form inputs for all payload cache settings
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check form field names exist
        assert (
            'name="payload_preview_size_chars"' in text_lower
        ), "Should have payload_preview_size_chars form field"
        assert (
            'name="payload_max_fetch_size_chars"' in text_lower
        ), "Should have payload_max_fetch_size_chars form field"
        assert (
            'name="payload_cache_ttl_seconds"' in text_lower
        ), "Should have payload_cache_ttl_seconds form field"
        assert (
            'name="payload_cleanup_interval_seconds"' in text_lower
        ), "Should have payload_cleanup_interval_seconds form field"


class TestPayloadCacheConfigValidation:
    """Tests for payload cache configuration validation."""

    def test_payload_preview_size_validation_invalid(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Invalid payload_preview_size_chars should show validation error.

        Given I am authenticated as an admin
        When I submit invalid payload_preview_size_chars (non-number)
        Then I see validation error message
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit invalid value
        response = client.post(
            "/admin/config/cache",
            data={
                "payload_preview_size_chars": "invalid",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error
        assert (
            "valid number" in text_lower or "must be" in text_lower
        ), "Should show validation error for invalid payload preview size"

    def test_payload_preview_size_validation_negative(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Negative payload_preview_size_chars should show validation error.

        Given I am authenticated as an admin
        When I submit negative payload_preview_size_chars
        Then I see validation error message about positive number
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit negative value
        response = client.post(
            "/admin/config/cache",
            data={
                "payload_preview_size_chars": "-100",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error about positive number
        assert (
            "positive" in text_lower or "must be" in text_lower
        ), "Should show validation error for negative payload preview size"


class TestPayloadCacheConfigSave:
    """Tests for payload cache configuration save functionality."""

    def test_payload_cache_save_success(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Valid payload cache configuration should save successfully.

        Given I am authenticated as an admin
        When I submit valid payload cache configuration
        Then I see success message and config is persisted
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit valid payload cache config
        response = client.post(
            "/admin/config/cache",
            data={
                "index_cache_ttl_minutes": "10",
                "index_cache_cleanup_interval": "60",
                "fts_cache_ttl_minutes": "10",
                "fts_cache_cleanup_interval": "60",
                "payload_preview_size_chars": "3000",
                "payload_max_fetch_size_chars": "8000",
                "payload_cache_ttl_seconds": "1200",
                "payload_cleanup_interval_seconds": "90",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert "success" in text_lower, "Should show success message after saving"

        # Verify values are shown on page
        assert "3000" in response.text, "Should show new preview size value"
        assert "8000" in response.text, "Should show new max fetch size value"
        assert "1200" in response.text, "Should show new cache TTL value"
        assert "90" in response.text, "Should show new cleanup interval value"

    def test_payload_cache_persists_after_page_reload(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Saved payload cache configuration should persist after page reload.

        Given I am authenticated as an admin
        And I have saved payload cache configuration
        When I reload the config page
        Then I see the saved values
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit payload cache config with distinctive values
        response = client.post(
            "/admin/config/cache",
            data={
                "index_cache_ttl_minutes": "10",
                "index_cache_cleanup_interval": "60",
                "fts_cache_ttl_minutes": "10",
                "fts_cache_cleanup_interval": "60",
                "payload_preview_size_chars": "4500",  # Distinctive value
                "payload_max_fetch_size_chars": "9500",  # Distinctive value
                "payload_cache_ttl_seconds": "1500",  # Distinctive value
                "payload_cleanup_interval_seconds": "75",  # Distinctive value
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200

        # Reload the config page
        reload_response = client.get("/admin/config")

        assert reload_response.status_code == 200

        # Verify saved values are still present
        assert "4500" in reload_response.text, "Preview size should persist"
        assert "9500" in reload_response.text, "Max fetch size should persist"
        assert "1500" in reload_response.text, "Cache TTL should persist"
        assert "75" in reload_response.text, "Cleanup interval should persist"
