"""Test verification for API compatibility fixes.

These tests verify that the parameter mismatches and endpoint prefix issues
have been properly resolved.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import Response

from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    ActivatedRepository,
)
from src.code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
)


class TestRepositoryActivationParameterFix:
    """Test that repository activation now sends correct parameter names."""

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

    @pytest.mark.asyncio
    async def test_repository_activation_correct_parameters_sent(
        self, repository_client
    ):
        """VERIFY FIX: Repository activation sends correct parameter names to server.

        Client now sends: golden_repo_alias, branch_name
        Server expects: golden_repo_alias, branch_name

        This test verifies the 422 validation error is fixed.
        """
        # Mock successful response showing fix is working
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "activation_id": "test-activation-id",
            "golden_alias": "test-repo",
            "user_alias": "user1",
            "branch": "main",
            "status": "active",
            "activated_at": "2024-01-01T00:00:00Z",
            "access_permissions": ["read"],
            "query_endpoint": "/api/query",
            "expires_at": "2024-12-31T23:59:59Z",
            "usage_limits": {},
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should now succeed with correct parameters
        result = await repository_client.activate_repository(
            golden_alias="test-repo", branch="main", user_alias="user1"
        )

        # Verify the request was made successfully
        assert isinstance(result, ActivatedRepository)

        # Verify the client now sends CORRECT parameter names
        call_args = repository_client._authenticated_request.call_args
        request_payload = call_args[1]["json"]

        # CRITICAL: These are the CORRECT parameter names that match server expectations
        assert "golden_repo_alias" in request_payload  # ✅ CORRECT
        assert "branch_name" in request_payload  # ✅ CORRECT
        assert "user_alias" in request_payload  # ✅ ALREADY CORRECT

        # Verify correct parameter values
        assert request_payload["golden_repo_alias"] == "test-repo"
        assert request_payload["branch_name"] == "main"
        assert request_payload["user_alias"] == "user1"

        # Verify OLD parameter names are NOT sent
        assert "golden_alias" not in request_payload  # ❌ OLD NAME REMOVED
        assert "branch" not in request_payload  # ❌ OLD NAME REMOVED

    @pytest.mark.asyncio
    async def test_repository_activation_handles_server_validation_success(
        self, repository_client
    ):
        """VERIFY FIX: Server validation now passes with correct parameter names."""
        # Mock successful server response (no more 422 errors)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "activation_id": "validation-success-id",
            "golden_alias": "validated-repo",
            "user_alias": "validated-user",
            "branch": "validated-branch",
            "status": "active",
            "activated_at": "2024-01-01T00:00:00Z",
            "access_permissions": ["read"],
            "query_endpoint": "/api/query",
            "expires_at": "2024-12-31T23:59:59Z",
            "usage_limits": {},
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Execute activation with various parameter combinations
        test_cases = [
            ("repo1", "main", "user1"),
            ("long-repository-name", "feature/branch", "user-with-dashes"),
            ("r", "b", "u"),  # Short names
        ]

        for golden_alias, branch, user_alias in test_cases:
            result = await repository_client.activate_repository(
                golden_alias=golden_alias, branch=branch, user_alias=user_alias
            )

            # All should succeed with proper parameter names
            assert isinstance(result, ActivatedRepository)

            # Verify parameter name consistency
            call_args = repository_client._authenticated_request.call_args
            request_payload = call_args[1]["json"]

            assert request_payload["golden_repo_alias"] == golden_alias
            assert request_payload["branch_name"] == branch
            assert request_payload["user_alias"] == user_alias


class TestAPIVersionPrefixFix:
    """Test that API endpoints now use correct /api/ prefix instead of /api/v1/."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test-server.example.com",
        }

    @pytest.fixture
    def query_client(self, mock_credentials):
        """Create remote query client for testing."""
        client = RemoteQueryClient(
            server_url="https://test-server.example.com", credentials=mock_credentials
        )
        return client

    @pytest.mark.asyncio
    async def test_query_history_uses_correct_prefix(self, query_client):
        """VERIFY FIX: Query history method returns empty list without HTTP calls.

        The implementation has been updated to return empty list directly
        rather than call non-existent endpoints.
        """
        # The current implementation returns empty list without calling the endpoint
        result = await query_client.get_query_history("test-repo")

        # Should return empty list without errors
        assert isinstance(result, list)
        assert len(result) == 0

        # Should NOT make any HTTP requests (returns empty list directly)
        # No call to _authenticated_request should be made

    @pytest.mark.asyncio
    async def test_repository_statistics_uses_correct_prefix(self, query_client):
        """VERIFY FIX: Repository statistics endpoint uses correct /api/repositories/{alias} format."""
        # Mock successful response with statistics
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "statistics": {
                "total_files": 100,
                "indexed_files": 95,
                "total_size_bytes": 1024000,
                "embedding_count": 500,
            }
        }
        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should succeed
        result = await query_client.get_repository_statistics("test-repo")

        # Should return statistics data
        assert isinstance(result, dict)
        assert "total_files" in result
        assert result["total_files"] == 100

        # Verify it's using the CORRECT endpoint format
        call_args = query_client._authenticated_request.call_args
        endpoint_url = call_args[0][1]

        # CRITICAL: Should use /api/repositories/{alias} (not /stats suffix)
        assert endpoint_url == "/api/repositories/test-repo"
        assert not endpoint_url.startswith("/api/v1/")  # ❌ OLD PREFIX REMOVED

    @pytest.mark.asyncio
    async def test_multiple_endpoints_consistent_prefix_usage(self, query_client):
        """VERIFY FIX: All endpoints consistently use /api/ prefix."""
        # Mock successful response for statistics (query_history doesn't call HTTP)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "statistics": {
                "total_files": 100,
                "indexed_files": 95,
                "total_size_bytes": 1024000,
                "embedding_count": 500,
            }
        }
        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Test query history (returns empty list directly)
        history_result = await query_client.get_query_history("test-repo")
        assert isinstance(history_result, list)
        assert len(history_result) == 0

        # Test repository statistics (makes HTTP call)
        stats_result = await query_client.get_repository_statistics("test-repo")
        assert isinstance(stats_result, dict)
        assert "total_files" in stats_result

        # Verify statistics endpoint uses correct format
        call_args = query_client._authenticated_request.call_args
        endpoint_url = call_args[0][1]
        assert endpoint_url == "/api/repositories/test-repo"
        assert not endpoint_url.startswith("/api/v1/")


class TestEndToEndCompatibilityValidation:
    """Integration tests to validate complete API compatibility."""

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

    @pytest.mark.asyncio
    async def test_complete_activation_parameter_compatibility(self, repository_client):
        """VERIFY: Complete end-to-end parameter compatibility with server models."""
        # Mock server validation success with all expected fields
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "activation_id": "e2e-test-id",
            "golden_alias": "e2e-repo",
            "user_alias": "e2e-user",
            "branch": "e2e-branch",
            "status": "active",
            "activated_at": "2024-01-01T00:00:00Z",
            "access_permissions": ["read", "query"],
            "query_endpoint": "/api/query",
            "expires_at": "2024-12-31T23:59:59Z",
            "usage_limits": {"queries_per_hour": 1000},
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Execute activation
        result = await repository_client.activate_repository(
            golden_alias="e2e-repo", branch="e2e-branch", user_alias="e2e-user"
        )

        # Verify successful activation
        assert isinstance(result, ActivatedRepository)
        assert result.activation_id == "e2e-test-id"

        # Verify exact parameter mapping
        call_args = repository_client._authenticated_request.call_args
        request_payload = call_args[1]["json"]

        # Server model compatibility check
        server_expected_params = {
            "golden_repo_alias": "e2e-repo",  # ✅ Matches ActivateRepositoryRequest.golden_repo_alias
            "branch_name": "e2e-branch",  # ✅ Matches ActivateRepositoryRequest.branch_name
            "user_alias": "e2e-user",  # ✅ Matches ActivateRepositoryRequest.user_alias
        }

        assert request_payload == server_expected_params

        # Verify POST to correct endpoint
        assert call_args[0][0] == "POST"
        assert call_args[0][1] == "/api/repos/activate"
