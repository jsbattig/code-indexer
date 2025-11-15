"""Unit tests for AdminAPIClient.get_golden_repository_branches() error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.code_indexer.api_clients.admin_client import AdminAPIClient
from src.code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestGetGoldenRepositoryBranchesErrorHandling:
    """Tests for get_golden_repository_branches() error handling."""

    @pytest.fixture
    def admin_client(self):
        """Create AdminAPIClient instance for testing."""
        return AdminAPIClient(
            server_url="http://test-server",
            credentials={"username": "admin", "password": "pass"},
            project_root="/test",
        )

    @pytest.mark.asyncio
    async def test_get_branches_handles_404(self, admin_client):
        """Test get_golden_repository_branches handles 404 repository not found."""
        # Mock response for 404
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Repository not found"}

        # Mock _authenticated_request to return 404
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with 404 status
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.get_golden_repository_branches("nonexistent-repo")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value).lower()
        assert "nonexistent-repo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_branches_handles_403(self, admin_client):
        """Test get_golden_repository_branches handles 403 insufficient privileges."""
        # Mock response for 403
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Insufficient privileges"}

        # Mock _authenticated_request to return 403
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise AuthenticationError
        with pytest.raises(AuthenticationError) as exc_info:
            await admin_client.get_golden_repository_branches("some-repo")

        assert "insufficient privileges" in str(exc_info.value).lower()
        assert "admin role required" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_branches_handles_500(self, admin_client):
        """Test get_golden_repository_branches handles 500 server error."""
        # Mock response for 500
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        # Mock _authenticated_request to return 500
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with proper error message
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.get_golden_repository_branches("some-repo")

        assert exc_info.value.status_code == 500
        assert "failed to get repository branches" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_branches_handles_malformed_json_response(self, admin_client):
        """Test get_golden_repository_branches handles malformed JSON in error response."""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("Invalid JSON")

        # Mock _authenticated_request to return malformed response
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with HTTP status code fallback
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.get_golden_repository_branches("some-repo")

        assert exc_info.value.status_code == 500
        assert "http 500" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_branches_handles_unexpected_exception(self, admin_client):
        """Test get_golden_repository_branches handles unexpected exceptions."""
        # Mock _authenticated_request to raise unexpected exception
        admin_client._authenticated_request = AsyncMock(
            side_effect=RuntimeError("Network timeout")
        )

        # Should wrap unexpected exceptions in APIClientError
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.get_golden_repository_branches("some-repo")

        assert (
            "unexpected error getting repository branches"
            in str(exc_info.value).lower()
        )
        assert "network timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_get_branches_success_case(self, admin_client):
        """Test get_golden_repository_branches returns data on success."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "branches": ["main", "develop", "feature-x"],
            "default_branch": "main",
        }

        # Mock _authenticated_request to return success
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should return the response data
        result = await admin_client.get_golden_repository_branches("test-repo")

        assert isinstance(result, dict)
        assert "branches" in result
        assert result["branches"] == ["main", "develop", "feature-x"]
        assert result["default_branch"] == "main"
