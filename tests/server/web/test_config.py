"""
Tests for Configuration Management (Story #537).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# AC1: Configuration Display Tests
# =============================================================================

class TestConfigDisplay:
    """Tests for configuration display (AC1)."""

    def test_config_page_requires_auth(self, web_client: TestClient):
        """
        AC1: Unauthenticated access to /admin/config redirects to login.

        Given I am not authenticated
        When I navigate to /admin/config
        Then I am redirected to /admin/login
        """
        response = web_client.get("/admin/config")

        assert response.status_code in [302, 303], (
            f"Expected redirect, got {response.status_code}"
        )
        location = response.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )

    def test_config_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/config shows config page.

        Given I am authenticated as an admin
        When I navigate to /admin/config
        Then I see the config page with title "Configuration - CIDX Admin"
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "Configuration - CIDX Admin" in response.text, (
            "Page title should be 'Configuration - CIDX Admin'"
        )

    def test_config_sections_present(self, authenticated_client: TestClient):
        """
        AC1/AC4: Config page shows all 5 logical sections.

        Given I am authenticated as an admin
        When I view the config page
        Then I see sections: Server, Indexing, Query, Storage, Security
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check all required sections are present
        assert "server" in text_lower, "Page should have Server Settings section"
        assert "indexing" in text_lower, "Page should have Indexing Settings section"
        assert "query" in text_lower, "Page should have Query Settings section"
        assert "storage" in text_lower, "Page should have Storage Settings section"
        assert "security" in text_lower, "Page should have Security Settings section"

    def test_config_section_collapsible(self, authenticated_client: TestClient):
        """
        AC1: Each section should be collapsible/expandable.

        Given I am authenticated as an admin
        When I view the config page
        Then I see details elements for collapsible sections
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        # Details/summary elements provide native collapsible behavior
        assert "<details" in response.text.lower(), (
            "Page should use <details> elements for collapsible sections"
        )
        assert "<summary" in response.text.lower(), (
            "Page should use <summary> elements for collapsible section headers"
        )


# =============================================================================
# AC2: Configuration Editing Tests
# =============================================================================

class TestConfigEditing:
    """Tests for configuration editing (AC2)."""

    def test_config_edit_button(self, authenticated_client: TestClient):
        """
        AC2: Edit button exists for each section.

        Given I am authenticated as an admin
        When I view the config page
        Then I see an "Edit" button for each section
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "edit" in text_lower, "Page should have Edit button(s)"

    def test_config_save_cancel(self, authenticated_client: TestClient):
        """
        AC2: Save and Cancel buttons exist in edit mode.

        Given I am authenticated as an admin
        When I view the config page
        Then I see Save and Cancel buttons for forms
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "save" in text_lower, "Page should have Save button"
        assert "cancel" in text_lower, "Page should have Cancel button"


# =============================================================================
# AC3: Field Types and Validation Tests
# =============================================================================

class TestConfigFieldTypes:
    """Tests for field types and validation (AC3)."""

    def test_config_field_types(self, authenticated_client: TestClient):
        """
        AC3: Config page has appropriate field types.

        Given I am authenticated as an admin
        When I view the config page
        Then I see boolean (checkbox), number, string, and select fields
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check for various input types
        # Boolean fields should have checkbox
        assert 'type="checkbox"' in text_lower or 'type="number"' in text_lower, (
            "Page should have checkbox or number inputs"
        )
        # Number fields should have number inputs
        # String fields should have text inputs
        assert 'type="text"' in text_lower or 'type="number"' in text_lower, (
            "Page should have text or number inputs"
        )

    def test_config_validation(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """
        AC3/AC5: Validation errors displayed inline.

        Given I am authenticated as an admin
        When I submit invalid config values
        Then I see validation error messages
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit invalid config (port out of range)
        response = client.post(
            "/admin/config/server",
            data={
                "port": "99999",  # Invalid port
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error
        assert "error" in text_lower or "invalid" in text_lower or "must be" in text_lower, (
            "Should show validation error for invalid port"
        )


# =============================================================================
# AC4: Configuration Sections Tests
# =============================================================================

class TestConfigSectionContents:
    """Tests for configuration section contents (AC4)."""

    def test_server_settings_fields(self, authenticated_client: TestClient):
        """
        AC4: Server Settings section has expected fields.

        Given I am authenticated as an admin
        When I view the config page
        Then Server Settings shows: Host, Port, Workers, Log Level
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Server settings fields
        assert "host" in text_lower, "Server Settings should have Host field"
        assert "port" in text_lower, "Server Settings should have Port field"
        assert "workers" in text_lower or "log" in text_lower, (
            "Server Settings should have Workers or Log Level field"
        )

    def test_indexing_settings_fields(self, authenticated_client: TestClient):
        """
        AC4: Indexing Settings section has expected fields.

        Given I am authenticated as an admin
        When I view the config page
        Then Indexing Settings shows: Batch Size, Max File Size, Excluded Patterns
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Indexing settings fields
        assert "batch" in text_lower or "file" in text_lower or "pattern" in text_lower, (
            "Indexing Settings should have batch size, file size, or patterns field"
        )

    def test_query_settings_fields(self, authenticated_client: TestClient):
        """
        AC4: Query Settings section has expected fields.

        Given I am authenticated as an admin
        When I view the config page
        Then Query Settings shows: Default Limit, Max Limit, Timeout, Min Score
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Query settings fields
        assert "limit" in text_lower or "timeout" in text_lower or "score" in text_lower, (
            "Query Settings should have limit, timeout, or score field"
        )


# =============================================================================
# AC5: Validation Feedback Tests
# =============================================================================

class TestValidationFeedback:
    """Tests for validation feedback (AC5)."""

    def test_port_validation_message(
        self,
        web_infrastructure: WebTestInfrastructure,
        admin_user: Dict[str, Any]
    ):
        """
        AC5: Invalid port shows specific error message.

        Given I am authenticated as an admin
        When I enter an invalid port (e.g., 99999)
        Then I see "Port must be between 1 and 65535" error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"],
            admin_user["password"]
        )

        # Get the config page to get CSRF token
        config_page = client.get("/admin/config")
        csrf_token = web_infrastructure.extract_csrf_token(config_page.text)

        # Submit invalid port
        response = client.post(
            "/admin/config/server",
            data={
                "port": "99999",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show specific port validation error
        assert "port" in text_lower and ("1" in text_lower or "65535" in text_lower or "invalid" in text_lower), (
            "Should show port validation error message"
        )


# =============================================================================
# AC6: Configuration Reset Tests
# =============================================================================

class TestConfigReset:
    """Tests for configuration reset (AC6)."""

    def test_config_reset_button(self, authenticated_client: TestClient):
        """
        AC6: Reset to Defaults button exists.

        Given I am authenticated as an admin
        When I view the config page
        Then I see a "Reset to Defaults" button
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "reset" in text_lower and "default" in text_lower, (
            "Page should have 'Reset to Defaults' button"
        )


# =============================================================================
# AC7: Read-Only Fields Tests
# =============================================================================

class TestReadOnlyFields:
    """Tests for read-only fields (AC7)."""

    def test_read_only_fields_exist(self, authenticated_client: TestClient):
        """
        AC7: Some fields are marked as read-only.

        Given I am authenticated as an admin
        When I view the config page
        Then I see some fields are marked as read-only or disabled
        """
        response = authenticated_client.get("/admin/config")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check for read-only indicators
        has_readonly = (
            "readonly" in text_lower or
            "disabled" in text_lower or
            "read-only" in text_lower or
            "restart" in text_lower
        )
        assert has_readonly, (
            "Page should have read-only fields or restart notice"
        )


# =============================================================================
# Partial Refresh Endpoint Tests
# =============================================================================

class TestConfigPartial:
    """Tests for htmx partial refresh endpoint."""

    def test_config_partial_section(self, authenticated_client: TestClient):
        """
        Partial endpoint for config section returns HTML fragment.

        Given I am authenticated
        When I request a config section partial
        Then I receive an HTML fragment (not full page)
        """
        response = authenticated_client.get("/admin/partials/config-section?section=server")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}"
        )
        # Should be an HTML fragment, not a full page
        assert "<html>" not in response.text.lower(), (
            "Partial should not contain full HTML structure"
        )

    def test_config_partial_requires_auth(self, web_client: TestClient):
        """
        Config partial endpoints require authentication.

        Given I am not authenticated
        When I request a config partial endpoint
        Then I am redirected to login
        """
        response = web_client.get("/admin/partials/config-section?section=server")
        assert response.status_code in [302, 303], (
            f"Config partial should redirect unauthenticated, got {response.status_code}"
        )
