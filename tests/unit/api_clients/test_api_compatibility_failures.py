"""Test cases to reproduce critical API compatibility failures identified by code-reviewer.

These tests reproduce the exact parameter mismatches and endpoint errors found
in production to ensure they are properly fixed.
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
    RepositoryAccessError,
)
from src.code_indexer.api_clients.base_client import APIClientError


class TestRepositoryActivationParameterMismatch:
    """Test cases reproducing repository activation parameter validation errors."""

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
    async def test_repository_activation_parameter_mismatch_reproduction(
        self, repository_client
    ):
        """REPRODUCE: Repository activation fails with 422 validation error due to parameter mismatch.

        Client sends: golden_alias, branch
        Server expects: golden_repo_alias, branch_name

        This test verifies the exact 422 error response that occurs in production.
        """
        # Mock the HTTP response that would come from server with parameter mismatch
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "detail": [
                {
                    "type": "missing",
                    "loc": ["body", "golden_repo_alias"],
                    "msg": "Field required",
                    "input": {
                        "golden_alias": "test-repo",
                        "branch": "main",
                        "user_alias": "user1",
                    },
                },
                {
                    "type": "missing",
                    "loc": ["body", "branch_name"],
                    "msg": "Field required",
                    "input": {
                        "golden_alias": "test-repo",
                        "branch": "main",
                        "user_alias": "user1",
                    },
                },
            ]
        }

        # Mock the request method to return the 422 response
        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should fail with ActivationError due to parameter mismatch
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.activate_repository(
                golden_alias="test-repo", branch="main", user_alias="user1"
            )

        # Verify the exact error message pattern that would occur
        assert "Activation error:" in str(exc_info.value)

        # Verify the client sent wrong parameter names (current broken behavior)
        call_args = repository_client._authenticated_request.call_args
        request_payload = call_args[1]["json"]

        # CRITICAL: These are the WRONG parameter names that cause 422 errors
        assert "golden_alias" in request_payload  # Should be "golden_repo_alias"
        assert "branch" in request_payload  # Should be "branch_name"
        assert "user_alias" in request_payload  # This one is correct

        # Verify wrong parameters values
        assert request_payload["golden_alias"] == "test-repo"
        assert request_payload["branch"] == "main"
        assert request_payload["user_alias"] == "user1"


class TestRepositoryListEndpoint404:
    """Test cases reproducing repository list endpoint 404 errors."""

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
    async def test_repository_list_endpoint_404_reproduction(self, repository_client):
        """REPRODUCE: Repository list endpoint returns 404 instead of repository list.

        Tests the /api/repos endpoint that should return list of activated repositories
        but is returning 404 in production.
        """
        # Mock 404 response that would indicate endpoint not found or not properly registered
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        # Mock the request method to simulate endpoint not found
        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should fail if endpoint is not properly registered
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.list_user_repositories()

        # Verify it's calling the correct endpoint
        call_args = repository_client._authenticated_request.call_args
        assert call_args[0][0] == "GET"  # HTTP method
        assert call_args[0][1] == "/api/repos"  # Endpoint URL

        # Verify error handling for 404
        assert "Failed to list repositories:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_client_repository_list_404_reproduction(self, query_client):
        """REPRODUCE: Query client repository list also experiences 404 errors.

        The RemoteQueryClient also calls /api/repos and may experience the same issue.
        """
        # Mock 404 response for repository listing via query client
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        # Mock the request method
        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should fail with APIClientError for 404
        with pytest.raises(APIClientError) as exc_info:
            await query_client.list_repositories()

        # Verify it's calling the correct endpoint
        call_args = query_client._authenticated_request.call_args
        assert call_args[0][0] == "GET"  # HTTP method
        assert call_args[0][1] == "/api/repos"  # Endpoint URL

        # Verify error message
        assert "Failed to list repositories:" in str(exc_info.value)


class TestAPIVersionPrefixMismatch:
    """Test cases reproducing incorrect /api/v1/ prefix usage."""

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
    async def test_query_history_wrong_prefix_reproduction(self, query_client):
        """REPRODUCE: Query history endpoint uses /api/v1/ prefix when server uses /api/.

        This test verifies that get_query_history still uses the wrong API prefix.
        """
        # Mock 404 response that would occur if wrong prefix is used
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should fail due to wrong prefix
        with pytest.raises(RepositoryAccessError):
            await query_client.get_query_history("test-repo")

        # Verify it's using the WRONG prefix (/api/v1/ instead of /api/)
        call_args = query_client._authenticated_request.call_args
        endpoint_url = call_args[0][1]

        # CRITICAL: This shows the bug - should be /api/ not /api/v1/
        assert endpoint_url.startswith("/api/v1/repositories/")
        assert "query-history" in endpoint_url

    @pytest.mark.asyncio
    async def test_repository_statistics_wrong_prefix_reproduction(self, query_client):
        """REPRODUCE: Repository statistics endpoint uses /api/v1/ prefix when server uses /api/.

        This test verifies that get_repository_statistics still uses the wrong API prefix.
        """
        # Mock 404 response that would occur if wrong prefix is used
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should fail due to wrong prefix
        with pytest.raises(RepositoryAccessError):
            await query_client.get_repository_statistics("test-repo")

        # Verify it's using the WRONG prefix (/api/v1/ instead of /api/)
        call_args = query_client._authenticated_request.call_args
        endpoint_url = call_args[0][1]

        # CRITICAL: This shows the bug - should be /api/ not /api/v1/
        assert endpoint_url.startswith("/api/v1/repositories/")
        assert "stats" in endpoint_url


class TestEndToEndParameterValidation:
    """Integration tests to validate parameter compatibility end-to-end."""

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
    async def test_parameter_names_sent_by_client(self, repository_client):
        """Verify exact parameter names sent by client for repository activation.

        This test captures the current broken behavior to ensure fix addresses exact issue.
        """
        # Mock successful response to focus on parameter validation
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "activation_id": "test-id",
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

        # Execute the activation
        await repository_client.activate_repository(
            golden_alias="test-repo", branch="main", user_alias="user1"
        )

        # Capture the exact parameters sent
        call_args = repository_client._authenticated_request.call_args
        request_payload = call_args[1]["json"]

        # Document the current WRONG parameter names for fixing
        expected_wrong_params = {
            "golden_alias": "test-repo",  # Should be "golden_repo_alias"
            "branch": "main",  # Should be "branch_name"
            "user_alias": "user1",  # This one is correct
        }

        assert request_payload == expected_wrong_params

        # This test will PASS with current broken implementation
        # After fix, we'll update this test to verify correct parameter names
