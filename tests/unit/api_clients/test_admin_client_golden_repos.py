"""
Test AdminAPIClient golden repository management functionality.

Tests the admin client's ability to add golden repositories through
the server API with proper authentication, validation, and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

# removed unused imports: Dict, Any

from src.code_indexer.api_clients.admin_client import AdminAPIClient
from src.code_indexer.api_clients.base_client import (
    APIClientError,
    AuthenticationError,
    NetworkError,
)


class TestAdminAPIClientGoldenRepos:
    """Test golden repository management through AdminAPIClient."""

    @pytest.fixture
    def admin_client(self) -> AdminAPIClient:
        """Create AdminAPIClient for testing."""
        return AdminAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "admin", "password": "admin123"},
            project_root=Path("/tmp/test_project"),
        )

    @pytest.mark.asyncio
    async def test_add_golden_repository_success(self, admin_client: AdminAPIClient):
        """Test successful golden repository addition."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"
        description = "Example repository for testing"

        expected_response = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "submitted",
            "message": "Golden repository addition job submitted successfully",
        }

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = expected_response
        admin_client._authenticated_request.return_value = mock_response

        # Act
        result = await admin_client.add_golden_repository(
            git_url=git_url, alias=alias, description=description
        )

        # Assert
        assert result == expected_response
        admin_client._authenticated_request.assert_called_once_with(
            "POST",
            "/api/admin/golden-repos",
            json={
                "repo_url": git_url,
                "alias": alias,
                "default_branch": "main",
                "description": description,
            },
        )

    @pytest.mark.asyncio
    async def test_add_golden_repository_without_description(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition without description."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"

        expected_response = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "submitted",
            "message": "Golden repository addition job submitted successfully",
        }

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = expected_response
        admin_client._authenticated_request.return_value = mock_response

        # Act
        result = await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        # Assert
        assert result == expected_response
        admin_client._authenticated_request.assert_called_once_with(
            "POST",
            "/api/admin/golden-repos",
            json={"repo_url": git_url, "alias": alias, "default_branch": "main"},
        )

    @pytest.mark.asyncio
    async def test_add_golden_repository_with_custom_branch(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with custom default branch."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"
        default_branch = "develop"

        expected_response = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "submitted",
            "message": "Golden repository addition job submitted successfully",
        }

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = expected_response
        admin_client._authenticated_request.return_value = mock_response

        # Act
        result = await admin_client.add_golden_repository(
            git_url=git_url, alias=alias, default_branch=default_branch
        )

        # Assert
        assert result == expected_response
        admin_client._authenticated_request.assert_called_once_with(
            "POST",
            "/api/admin/golden-repos",
            json={
                "repo_url": git_url,
                "alias": alias,
                "default_branch": default_branch,
            },
        )

    @pytest.mark.asyncio
    async def test_add_golden_repository_invalid_url_validation_error(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with invalid Git URL returns validation error."""
        # Arrange
        git_url = "invalid-url"
        alias = "example-repo"

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid Git URL format"}
        admin_client._authenticated_request.return_value = mock_response

        # Act & Assert
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert "Invalid request data: Invalid Git URL format" in str(exc_info.value)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_add_golden_repository_alias_conflict_error(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with duplicate alias returns conflict error."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "existing-repo"

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "detail": "Golden repository with alias 'existing-repo' already exists"
        }
        admin_client._authenticated_request.return_value = mock_response

        # Act & Assert
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert (
            "Repository conflict: Golden repository with alias 'existing-repo' already exists"
            in str(exc_info.value)
        )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_add_golden_repository_insufficient_privileges(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with insufficient privileges."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Insufficient privileges"}
        admin_client._authenticated_request.return_value = mock_response

        # Act & Assert
        with pytest.raises(AuthenticationError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert (
            "Insufficient privileges for golden repository creation (admin role required)"
            in str(exc_info.value)
        )

    @pytest.mark.asyncio
    async def test_add_golden_repository_server_error(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with server error."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"

        # Mock the _authenticated_request method
        admin_client._authenticated_request = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}
        admin_client._authenticated_request.return_value = mock_response

        # Act & Assert
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert "Failed to add golden repository: Internal server error" in str(
            exc_info.value
        )
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_add_golden_repository_network_error(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with network error."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"

        # Mock the _authenticated_request method to raise NetworkError
        admin_client._authenticated_request = AsyncMock()
        admin_client._authenticated_request.side_effect = NetworkError(
            "Connection failed"
        )

        # Act & Assert
        with pytest.raises(NetworkError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert "Connection failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_golden_repository_unexpected_error(
        self, admin_client: AdminAPIClient
    ):
        """Test golden repository addition with unexpected error."""
        # Arrange
        git_url = "https://github.com/example/repo.git"
        alias = "example-repo"

        # Mock the _authenticated_request method to raise unexpected error
        admin_client._authenticated_request = AsyncMock()
        admin_client._authenticated_request.side_effect = Exception("Unexpected error")

        # Act & Assert
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.add_golden_repository(git_url=git_url, alias=alias)

        assert "Unexpected error adding golden repository: Unexpected error" in str(
            exc_info.value
        )

    def test_add_golden_repository_validates_git_url_format(
        self, admin_client: AdminAPIClient
    ):
        """Test that add_golden_repository validates Git URL format locally."""
        # This test will verify that we have local validation
        # Will be implemented with the actual method
        pass

    def test_add_golden_repository_validates_alias_format(
        self, admin_client: AdminAPIClient
    ):
        """Test that add_golden_repository validates alias format locally."""
        # This test will verify that we have local validation
        # Will be implemented with the actual method
        pass
