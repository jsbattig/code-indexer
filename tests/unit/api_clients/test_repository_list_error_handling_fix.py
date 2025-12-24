"""Test verification that repository list error handling improvements resolve the "404 issue".

This test verifies that the improved error handling provides specific, actionable
error messages instead of generic ones that mask the real issues.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import Response

from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    ActivationError,
)
from src.code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
    APIClientError,
)
from src.code_indexer.api_clients.base_client import AuthenticationError


class TestRepositoryListErrorHandlingFix:
    """Test that error handling improvements resolve the "404 issue"."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test-server.example.com",
        }

    @pytest.fixture
    def repository_client(self, mock_credentials):
        """Create repository linking client for testing."""
        client = RepositoryLinkingClient(
            server_url="https://test-server.example.com", credentials=mock_credentials
        )
        return client

    @pytest.fixture
    def query_client(self, mock_credentials):
        """Create remote query client for testing."""
        client = RemoteQueryClient(
            server_url="https://test-server.example.com", credentials=mock_credentials
        )
        return client

    @pytest.mark.asyncio
    async def test_repository_client_authentication_error_specific_handling(
        self, repository_client
    ):
        """VERIFY FIX: 401 errors now raise AuthenticationError with specific message."""
        # Mock 401 authentication failure
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Could not validate credentials"}

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should now raise specific AuthenticationError, not generic ActivationError
        with pytest.raises(AuthenticationError) as exc_info:
            await repository_client.list_user_repositories()

        # Verify specific error message and type
        assert "Authentication failed:" in str(exc_info.value)
        assert "Could not validate credentials" in str(exc_info.value)

        # Verify it's NOT the old generic message
        assert "Failed to list repositories:" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_client_access_denied_specific_handling(
        self, repository_client
    ):
        """VERIFY FIX: 403 errors now provide specific access denied messages."""
        # Mock 403 access denied
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "detail": "Insufficient permissions for repository access"
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise ActivationError with specific access denied message
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.list_user_repositories()

        # Verify specific error message
        assert "Access denied:" in str(exc_info.value)
        assert "Insufficient permissions" in str(exc_info.value)

        # Verify it's NOT the old generic message
        assert "Failed to list repositories:" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_client_true_404_specific_handling(
        self, repository_client
    ):
        """VERIFY FIX: True 404 errors now provide endpoint-specific messages."""
        # Mock true 404 (endpoint not found)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise ActivationError with endpoint-specific message
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.list_user_repositories()

        # Verify specific error message for endpoint issues
        assert "Repository list endpoint not available:" in str(exc_info.value)
        assert "Not Found" in str(exc_info.value)

        # Verify it's NOT the old generic message
        assert "Failed to list repositories:" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_client_authentication_error_specific_handling(
        self, query_client
    ):
        """VERIFY FIX: Query client 401 errors now raise AuthenticationError."""
        # Mock 401 authentication failure
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Token has expired"}

        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should now raise specific AuthenticationError
        with pytest.raises(AuthenticationError) as exc_info:
            await query_client.list_repositories()

        # Verify specific error message and type
        assert "Authentication failed:" in str(exc_info.value)
        assert "Token has expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_client_true_404_specific_handling(self, query_client):
        """VERIFY FIX: Query client 404 errors provide endpoint-specific messages."""
        # Mock true 404 (endpoint not found)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should raise APIClientError with endpoint-specific message
        with pytest.raises(APIClientError) as exc_info:
            await query_client.list_repositories()

        # Verify specific error message for endpoint issues
        assert "Repository list endpoint not available:" in str(exc_info.value)
        assert "Not Found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_error_handling_improvement_comparison(self, repository_client):
        """DEMONSTRATE: How the fix resolves the "404 issue" confusion."""

        # Test scenarios that previously appeared as generic "404 errors"
        test_scenarios = [
            (401, "Invalid token", AuthenticationError, "Authentication failed:"),
            (403, "Access denied", ActivationError, "Access denied:"),
            (
                404,
                "Not Found",
                ActivationError,
                "Repository list endpoint not available:",
            ),
            (500, "Internal error", ActivationError, "Failed to list repositories:"),
        ]

        for (
            status_code,
            detail,
            expected_exception,
            expected_message_prefix,
        ) in test_scenarios:
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = status_code
            mock_response.json.return_value = {"detail": detail}

            repository_client._authenticated_request = AsyncMock(
                return_value=mock_response
            )

            # Each error type should raise specific exception with specific message
            with pytest.raises(expected_exception) as exc_info:
                await repository_client.list_user_repositories()

            error_message = str(exc_info.value)

            # Verify specific error handling
            assert expected_message_prefix in error_message
            assert detail in error_message

            # Document the improvement
            print(
                f"STATUS {status_code}: {expected_exception.__name__} - {error_message}"
            )

        # OLD BEHAVIOR (all would be): "Failed to list repositories: [detail]"
        # NEW BEHAVIOR (specific to error type):
        # 401: "Authentication failed: [detail]"
        # 403: "Access denied: [detail]"
        # 404: "Repository list endpoint not available: [detail]"
        # 500: "Failed to list repositories: [detail]" (only for server errors)

    @pytest.mark.asyncio
    async def test_successful_repository_list_unchanged(self, repository_client):
        """VERIFY: Successful responses continue to work correctly."""
        # Mock successful response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "repositories": [
                {
                    "activation_id": "test-id",
                    "golden_alias": "test-repo",
                    "user_alias": "test-user",
                    "branch": "main",
                    "status": "active",
                    "activated_at": "2024-01-01T00:00:00Z",
                    "access_permissions": ["read"],
                    "query_endpoint": "/api/query",
                    "expires_at": "2024-12-31T23:59:59Z",
                    "usage_limits": {},
                }
            ]
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should succeed without any errors
        result = await repository_client.list_user_repositories()

        # Verify successful operation
        assert len(result) == 1
        assert result[0].golden_alias == "test-repo"

    @pytest.mark.asyncio
    async def test_empty_repository_list_handling(self, repository_client):
        """VERIFY: Empty repository lists are handled correctly."""
        # Mock empty repository list (valid response)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"repositories": []}

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should succeed with empty list
        result = await repository_client.list_user_repositories()

        # Verify empty list handling
        assert result == []
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_malformed_repository_response_handling(self, repository_client):
        """VERIFY: Malformed responses are handled gracefully."""
        # Mock response missing "repositories" key
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [], "count": 0}  # Wrong key

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Should handle missing "repositories" key gracefully
        result = await repository_client.list_user_repositories()

        # Should default to empty list when key is missing
        assert result == []
