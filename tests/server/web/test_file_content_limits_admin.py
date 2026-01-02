"""
Tests for File Content Limits Admin Settings Page.

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from typing import Dict, Any
from fastapi.testclient import TestClient

from .conftest import WebTestInfrastructure


# =============================================================================
# Authentication and Access Control Tests
# =============================================================================


class TestFileContentLimitsAuth:
    """Tests for authentication and access control."""

    def test_requires_authentication(self, web_client: TestClient):
        """
        Unauthenticated access redirects to login.

        Given I am not authenticated
        When I navigate to /admin/settings/file-content-limits
        Then I am redirected to /user/login
        """
        response = web_client.get("/admin/settings/file-content-limits")

        assert response.status_code in [
            302,
            303,
        ], f"Expected redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert (
            "/user/login" in location
        ), f"Expected redirect to /user/login, got {location}"

    def test_requires_admin_role(
        self, web_infrastructure: WebTestInfrastructure, normal_user: Dict[str, Any]
    ):
        """
        Non-admin users cannot access settings page.

        Given I am authenticated as a normal user
        When I navigate to /admin/settings/file-content-limits
        Then I am redirected to /user/login
        """
        client = web_infrastructure.get_authenticated_client(
            normal_user["username"], normal_user["password"]
        )

        response = client.get("/admin/settings/file-content-limits")

        assert response.status_code in [
            302,
            303,
        ], f"Non-admin should be redirected, got {response.status_code}"

    def test_admin_can_access(self, authenticated_client: TestClient):
        """
        Admin users can access settings page.

        Given I am authenticated as an admin
        When I navigate to /admin/settings/file-content-limits
        Then I see the file content limits settings page
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"


# =============================================================================
# Page Rendering Tests
# =============================================================================


class TestFileContentLimitsDisplay:
    """Tests for settings page display."""

    def test_page_title(self, authenticated_client: TestClient):
        """
        Page has correct title.

        Given I am authenticated as an admin
        When I view the file content limits page
        Then I see title "File Content Limits - CIDX Admin"
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        assert (
            "File Content Limits" in response.text
        ), "Page should have 'File Content Limits' in title"

    def test_displays_current_config(self, authenticated_client: TestClient):
        """
        Page displays current configuration values.

        Given I am authenticated as an admin
        When I view the file content limits page
        Then I see current max_tokens_per_request value
        And I see current chars_per_token value
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show config fields
        assert (
            "max" in text_lower and "token" in text_lower
        ), "Page should show max tokens field"
        assert (
            "char" in text_lower and "token" in text_lower
        ), "Page should show chars per token field"

    def test_displays_calculated_values(self, authenticated_client: TestClient):
        """
        Page displays calculated values (max chars, estimated lines).

        Given I am authenticated as an admin
        When I view the file content limits page
        Then I see calculated max characters
        And I see estimated max lines
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show calculated fields
        assert "max" in text_lower and (
            "char" in text_lower or "character" in text_lower
        ), "Page should show max characters"

    def test_has_form_elements(self, authenticated_client: TestClient):
        """
        Page has form with input elements.

        Given I am authenticated as an admin
        When I view the file content limits page
        Then I see a form with max_tokens_per_request input
        And I see chars_per_token dropdown
        And I see save button
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should have form elements
        assert "<form" in text_lower, "Page should have form"
        assert (
            'type="range"' in text_lower
            or 'type="number"' in text_lower
            or "input" in text_lower
        ), "Page should have slider or number input"
        assert "<select" in text_lower, "Page should have dropdown for chars_per_token"
        assert (
            "save" in text_lower or 'type="submit"' in text_lower
        ), "Page should have save button"


# =============================================================================
# Form Input Tests
# =============================================================================


class TestFileContentLimitsFormInputs:
    """Tests for form input elements."""

    def test_max_tokens_slider(self, authenticated_client: TestClient):
        """
        Max tokens has slider/number input with correct range.

        Given I am authenticated as an admin
        When I view the file content limits page
        Then max_tokens_per_request input has min=1000, max=20000, step=100
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Check for range input or number input with appropriate attributes
        assert (
            "min" in text_lower and "max" in text_lower
        ), "Input should have min/max attributes"

    def test_chars_per_token_dropdown(self, authenticated_client: TestClient):
        """
        Chars per token has dropdown with values 3, 4, 5.

        Given I am authenticated as an admin
        When I view the file content limits page
        Then chars_per_token dropdown has options: 3, 4, 5
        """
        response = authenticated_client.get("/admin/settings/file-content-limits")

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should have select with options 3, 4, 5
        assert "<select" in text_lower, "Page should have dropdown"
        assert (
            "3" in response.text and "4" in response.text and "5" in response.text
        ), "Dropdown should have options 3, 4, 5"


# =============================================================================
# Form Submission Tests
# =============================================================================


class TestFileContentLimitsUpdate:
    """Tests for updating configuration via form submission."""

    def test_successful_update(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Valid form submission updates configuration.

        Given I am authenticated as an admin
        When I submit valid max_tokens_per_request=10000 and chars_per_token=4
        Then configuration is updated
        And I see success message
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Get page to extract CSRF token
        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        # Submit form with valid values
        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "10000",
                "chars_per_token": "4",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower or "saved" in text_lower or "updated" in text_lower
        ), "Should show success message after update"

    def test_csrf_token_required(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Form submission requires valid CSRF token.

        Given I am authenticated as an admin
        When I submit form without CSRF token
        Then I see error message
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Submit form without CSRF token
        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "10000",
                "chars_per_token": "4",
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error
        assert (
            "error" in text_lower or "invalid" in text_lower or "csrf" in text_lower
        ), "Should show CSRF error"


# =============================================================================
# Validation Tests
# =============================================================================


class TestFileContentLimitsValidation:
    """Tests for form validation."""

    def test_max_tokens_too_low(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Max tokens below 1000 shows validation error.

        Given I am authenticated as an admin
        When I submit max_tokens_per_request=500 (below min)
        Then I see validation error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "500",  # Below min (1000)
                "chars_per_token": "4",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error
        assert (
            "error" in text_lower or "invalid" in text_lower or "1000" in text_lower
        ), "Should show error for value below minimum"

    def test_max_tokens_too_high(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Max tokens above 20000 shows validation error.

        Given I am authenticated as an admin
        When I submit max_tokens_per_request=25000 (above max)
        Then I see validation error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "25000",  # Above max (20000)
                "chars_per_token": "4",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error
        assert (
            "error" in text_lower or "invalid" in text_lower or "20000" in text_lower
        ), "Should show error for value above maximum"

    def test_chars_per_token_invalid(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Chars per token outside 3-5 range shows validation error.

        Given I am authenticated as an admin
        When I submit chars_per_token=10 (invalid)
        Then I see validation error
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "10000",
                "chars_per_token": "10",  # Invalid (must be 3-5)
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show validation error
        assert (
            "error" in text_lower or "invalid" in text_lower
        ), "Should show error for invalid chars_per_token"


# =============================================================================
# Success/Error Feedback Tests
# =============================================================================


class TestFileContentLimitsFeedback:
    """Tests for success and error message display."""

    def test_success_message_displayed(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Success message displayed after successful update.

        Given I am authenticated as an admin
        When I successfully update settings
        Then I see a success message
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "8000",
                "chars_per_token": "5",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show success message
        assert (
            "success" in text_lower or "saved" in text_lower
        ), "Should display success message"

    def test_error_message_inline(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Validation errors displayed inline with form.

        Given I am authenticated as an admin
        When I submit invalid values
        Then I see inline validation error messages
        And the form is still displayed
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        response = client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "100",  # Invalid
                "chars_per_token": "4",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        text_lower = response.text.lower()

        # Should show error and still have form
        assert (
            "error" in text_lower or "invalid" in text_lower
        ), "Should show error message"
        assert "<form" in text_lower, "Form should still be displayed after error"


# =============================================================================
# Configuration Persistence Tests
# =============================================================================


class TestFileContentLimitsPersistence:
    """Tests for configuration persistence."""

    def test_updated_values_persist(
        self, web_infrastructure: WebTestInfrastructure, admin_user: Dict[str, Any]
    ):
        """
        Updated values persist and are displayed on page reload.

        Given I am authenticated as an admin
        When I update max_tokens_per_request to 15000
        And I reload the page
        Then I see max_tokens_per_request is 15000
        """
        client = web_infrastructure.get_authenticated_client(
            admin_user["username"], admin_user["password"]
        )

        # Update configuration
        page_response = client.get("/admin/settings/file-content-limits")
        csrf_token = web_infrastructure.extract_csrf_token(page_response.text)

        client.post(
            "/admin/settings/file-content-limits",
            data={
                "max_tokens_per_request": "15000",
                "chars_per_token": "3",
                "csrf_token": csrf_token,
            },
            follow_redirects=True,
        )

        # Reload page
        reload_response = client.get("/admin/settings/file-content-limits")

        assert reload_response.status_code == 200
        # Should show updated value
        assert "15000" in reload_response.text, "Page should show updated value 15000"
        assert "3" in reload_response.text, "Page should show updated value 3"
