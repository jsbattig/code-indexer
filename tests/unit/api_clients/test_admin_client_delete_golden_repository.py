"""
Tests for AdminAPIClient.delete_golden_repository() method.

Tests integration with DELETE /api/admin/golden-repos/{alias} endpoint
following TDD methodology and MESSI Rule #1 (anti-mock).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.code_indexer.api_clients.admin_client import AdminAPIClient
from src.code_indexer.api_clients.base_client import (
    APIClientError,
    AuthenticationError,
    NetworkError,
)


class TestAdminAPIClientDeleteGoldenRepository:
    """Test suite for AdminAPIClient.delete_golden_repository() method."""

    @pytest.fixture
    def admin_client(self):
        """Create AdminAPIClient instance for testing."""
        credentials = {"encrypted_data": "test_data"}
        return AdminAPIClient(
            server_url="https://test-server.com",
            credentials=credentials,
            project_root=Path("/test"),
        )

    @pytest.mark.asyncio
    async def test_delete_golden_repository_method_exists(self, admin_client):
        """Test that delete_golden_repository method exists (will fail initially)."""
        # This test will fail until we implement the method
        assert hasattr(admin_client, "delete_golden_repository")
        assert callable(getattr(admin_client, "delete_golden_repository"))

    @pytest.mark.asyncio
    async def test_delete_golden_repository_success_returns_empty_dict(
        self, admin_client
    ):
        """Test successful deletion returns empty dict for 204 No Content."""
        # Mock successful DELETE request
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Test successful deletion
        result = await admin_client.delete_golden_repository("test-repo")

        # Should return empty dict for 204 No Content
        assert result == {}

        # Verify correct API call
        admin_client._authenticated_request.assert_called_once_with(
            "DELETE", "/api/admin/golden-repos/test-repo"
        )

    @pytest.mark.asyncio
    async def test_delete_golden_repository_with_force_flag(self, admin_client):
        """Test delete with force flag (parameter validation)."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_response.text = ""

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Test with force=True (should not affect API call)
        result = await admin_client.delete_golden_repository("test-repo", force=True)

        assert result == {}
        admin_client._authenticated_request.assert_called_once_with(
            "DELETE", "/api/admin/golden-repos/test-repo"
        )

    @pytest.mark.asyncio
    async def test_delete_golden_repository_not_found_raises_api_error(
        self, admin_client
    ):
        """Test repository not found raises APIClientError with 404."""
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Repository 'test-repo' not found"}

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with 404
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("nonexistent-repo")

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_forbidden_raises_auth_error(
        self, admin_client
    ):
        """Test insufficient privileges raises AuthenticationError."""
        # Mock 403 response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Insufficient privileges"}

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise AuthenticationError
        with pytest.raises(AuthenticationError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert "admin role required" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_conflict_raises_api_error(
        self, admin_client
    ):
        """Test repository conflict (active instances) raises APIClientError with 409."""
        # Mock 409 response
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "detail": "Cannot delete repository with active instances"
        }

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with 409
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert exc_info.value.status_code == 409
        assert "conflict" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_service_unavailable_raises_api_error(
        self, admin_client
    ):
        """Test service unavailable raises APIClientError with 503."""
        # Mock 503 response
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {
            "detail": "Repository deletion failed due to service unavailability"
        }

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with 503
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert exc_info.value.status_code == 503
        assert "service unavailable" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_internal_error_raises_api_error(
        self, admin_client
    ):
        """Test internal server error raises APIClientError with 500."""
        # Mock 500 response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with 500
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert exc_info.value.status_code == 500
        assert "failed to delete" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_handles_json_decode_error(
        self, admin_client
    ):
        """Test graceful handling of malformed JSON responses."""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.side_effect = ValueError("Invalid JSON")

        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should handle JSON decode error gracefully
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert exc_info.value.status_code == 404
        assert "repository not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_golden_repository_network_error_propagation(
        self, admin_client
    ):
        """Test network errors are properly propagated."""
        # Mock network error
        admin_client._authenticated_request = AsyncMock(
            side_effect=NetworkError("Connection failed")
        )

        # Should propagate NetworkError
        with pytest.raises(NetworkError):
            await admin_client.delete_golden_repository("test-repo")

    @pytest.mark.asyncio
    async def test_delete_golden_repository_unexpected_error_handling(
        self, admin_client
    ):
        """Test unexpected exceptions are wrapped in APIClientError."""
        # Mock unexpected exception
        admin_client._authenticated_request = AsyncMock(
            side_effect=ValueError("Unexpected error")
        )

        # Should wrap unexpected errors
        with pytest.raises(APIClientError) as exc_info:
            await admin_client.delete_golden_repository("test-repo")

        assert (
            "unexpected error deleting golden repository" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_delete_golden_repository_validates_alias_parameter(
        self, admin_client
    ):
        """Test that alias parameter is required and validated."""
        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 204
        admin_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Test with empty alias
        with pytest.raises((ValueError, TypeError)):
            await admin_client.delete_golden_repository("")

        # Test with None alias
        with pytest.raises((ValueError, TypeError)):
            await admin_client.delete_golden_repository(None)

    @pytest.mark.asyncio
    async def test_delete_golden_repository_signature_validation(self, admin_client):
        """Test method signature matches specification."""
        import inspect

        # Get method signature
        sig = inspect.signature(admin_client.delete_golden_repository)
        params = list(sig.parameters.keys())

        # Should have alias and force parameters
        assert "alias" in params
        assert "force" in params

        # Force should have default value False
        assert sig.parameters["force"].default is False

        # Return annotation should be Dict[str, Any]
        assert "Dict" in str(sig.return_annotation) or sig.return_annotation is dict
