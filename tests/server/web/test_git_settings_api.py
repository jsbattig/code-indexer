"""
Tests for Git Settings API (Story #641 AC #6).

These tests follow TDD methodology - tests are written FIRST before implementation.
Tests verify REST API endpoints for managing default_committer_email configuration.

Tests verify the API interface contract, not implementation details.
Persistence is verified through the API (GET after PUT) rather than direct ConfigManager access.
"""

from fastapi.testclient import TestClient


# =============================================================================
# AC6.1: GET /api/settings/git - Retrieve Current Configuration
# =============================================================================


class TestGitSettingsAPI:
    """Tests for Git Settings REST API (AC #6)."""

    def test_get_git_settings_requires_auth(self, web_client: TestClient):
        """
        AC6.1: Unauthenticated access to GET /api/settings/git returns 401.

        Given I am not authenticated
        When I send GET /api/settings/git
        Then I receive 401 Unauthorized
        """
        response = web_client.get("/api/settings/git")

        assert (
            response.status_code == 401
        ), f"Expected 401 Unauthorized, got {response.status_code}"

    def test_get_git_settings_returns_current_config(
        self, authenticated_client: TestClient
    ):
        """
        AC6.1: GET /api/settings/git returns current git service configuration.

        Given I am authenticated as an admin
        When I send GET /api/settings/git
        Then I receive 200 OK with git service configuration
        """
        response = authenticated_client.get("/api/settings/git")

        # Verify response
        assert (
            response.status_code == 200
        ), f"Expected 200 OK, got {response.status_code}"
        data = response.json()

        assert "service_committer_name" in data
        assert "service_committer_email" in data
        assert "default_committer_email" in data

    def test_get_git_settings_returns_valid_response(
        self, authenticated_client: TestClient
    ):
        """
        AC6.1: GET /api/settings/git returns valid configuration structure.

        Given I am authenticated as an admin
        When I send GET /api/settings/git
        Then I receive 200 OK with git service configuration structure
        """
        response = authenticated_client.get("/api/settings/git")

        assert (
            response.status_code == 200
        ), f"Expected 200 OK, got {response.status_code}"
        data = response.json()

        # Verify response structure with expected field types
        assert "service_committer_name" in data
        assert isinstance(data["service_committer_name"], str)
        assert "service_committer_email" in data
        assert isinstance(data["service_committer_email"], str)
        assert "default_committer_email" in data
        # default_committer_email can be string or None
        assert data["default_committer_email"] is None or isinstance(
            data["default_committer_email"], str
        )


# =============================================================================
# AC6.2: PUT /api/settings/git - Update Configuration
# =============================================================================


class TestUpdateGitSettings:
    """Tests for updating git settings via API."""

    def test_put_git_settings_requires_auth(self, web_client: TestClient):
        """
        AC6.2: Unauthenticated access to PUT /api/settings/git returns 401.

        Given I am not authenticated
        When I send PUT /api/settings/git
        Then I receive 401 Unauthorized
        """
        payload = {"default_committer_email": "new@example.com"}
        response = web_client.put("/api/settings/git", json=payload)

        assert (
            response.status_code == 401
        ), f"Expected 401 Unauthorized, got {response.status_code}"

    def test_put_git_settings_updates_config(self, authenticated_client: TestClient):
        """
        AC6.2: PUT /api/settings/git updates default_committer_email.

        Given I am authenticated as an admin
        When I send PUT /api/settings/git with new default_committer_email
        Then the configuration is updated
        And I receive 200 OK with updated config
        """
        # Update via API
        new_email = "new-committer@example.com"
        payload = {"default_committer_email": new_email}
        response = authenticated_client.put("/api/settings/git", json=payload)

        # Verify response
        assert (
            response.status_code == 200
        ), f"Expected 200 OK, got {response.status_code}"
        data = response.json()
        assert data["default_committer_email"] == new_email

        # Verify persistence by reading back via GET
        get_response = authenticated_client.get("/api/settings/git")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["default_committer_email"] == new_email

    def test_put_git_settings_validates_email_format(
        self, authenticated_client: TestClient
    ):
        """
        AC6.2: PUT /api/settings/git validates email format.

        Given I am authenticated as an admin
        When I send PUT /api/settings/git with invalid email
        Then I receive 422 Unprocessable Entity with validation error
        """
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "missing-at.com",
            "double@@example.com",
            "",
            "   ",
        ]

        for invalid_email in invalid_emails:
            payload = {"default_committer_email": invalid_email}
            response = authenticated_client.put("/api/settings/git", json=payload)

            assert response.status_code == 422, (
                f"Expected 422 for invalid email '{invalid_email}', "
                f"got {response.status_code}"
            )

    def test_put_git_settings_accepts_valid_emails(
        self, authenticated_client: TestClient
    ):
        """
        AC6.2: PUT /api/settings/git accepts valid email formats.

        Given I am authenticated as an admin
        When I send PUT /api/settings/git with valid emails
        Then each update succeeds
        """
        valid_emails = [
            "user@example.com",
            "first.last@company.org",
            "test+tag@domain.co.uk",
            "admin-bot@ci-cd.internal",
        ]

        for valid_email in valid_emails:
            payload = {"default_committer_email": valid_email}
            response = authenticated_client.put("/api/settings/git", json=payload)

            assert response.status_code == 200, (
                f"Expected 200 for valid email '{valid_email}', "
                f"got {response.status_code}: {response.text}"
            )
            data = response.json()
            assert data["default_committer_email"] == valid_email

    def test_put_git_settings_updates_only_specified_fields(
        self, authenticated_client: TestClient
    ):
        """
        AC6.2: PUT /api/settings/git only updates specified fields.

        Given I am authenticated as an admin
        And I have existing git service configuration
        When I send PUT /api/settings/git updating only default_committer_email
        Then only default_committer_email is updated
        And other fields remain unchanged
        """
        # Get current values
        get_response = authenticated_client.get("/api/settings/git")
        assert get_response.status_code == 200
        original_data = get_response.json()
        original_name = original_data["service_committer_name"]
        original_service_email = original_data["service_committer_email"]

        # Update only default_committer_email
        new_default = "new-default@example.com"
        payload = {"default_committer_email": new_default}
        response = authenticated_client.put("/api/settings/git", json=payload)

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["default_committer_email"] == new_default
        assert data["service_committer_name"] == original_name
        assert data["service_committer_email"] == original_service_email

    def test_put_git_settings_handles_none_value(
        self, authenticated_client: TestClient
    ):
        """
        AC6.2: PUT /api/settings/git allows setting default_committer_email to None.

        Given I am authenticated as an admin
        When I send PUT /api/settings/git with default_committer_email: null
        Then the field is set to None
        And I receive 200 OK
        """
        # Update to None
        payload = {"default_committer_email": None}
        response = authenticated_client.put("/api/settings/git", json=payload)

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["default_committer_email"] is None

        # Verify persistence via GET
        get_response = authenticated_client.get("/api/settings/git")
        assert get_response.status_code == 200
        get_data = get_response.json()
        assert get_data["default_committer_email"] is None
