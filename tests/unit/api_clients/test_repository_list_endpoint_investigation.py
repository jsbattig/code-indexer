"""Deep investigation of repository list endpoint 404 issues.

This test investigates the exact conditions under which the /api/repos endpoint
returns 404 vs proper responses.
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


class TestRepositoryListEndpointDeepInvestigation:
    """Deep investigation of /api/repos endpoint 404 issues."""

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
    async def test_repository_list_endpoint_empty_response_behavior(
        self, repository_client
    ):
        """Investigate endpoint behavior when user has no repositories."""
        # Mock empty repository list (valid response, not 404)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"repositories": []}  # Empty list is valid

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should succeed with empty list
        result = await repository_client.list_user_repositories()

        # Verify proper empty response handling
        assert result == []
        assert isinstance(result, list)

        # Verify correct endpoint call
        call_args = repository_client._authenticated_request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/api/repos"

    @pytest.mark.asyncio
    async def test_repository_list_endpoint_authentication_failure_as_404(
        self, repository_client
    ):
        """Investigate if authentication failures appear as 404."""
        # Mock authentication failure (could appear as 404 in some configs)
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Could not validate credentials"}

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should raise ActivationError for 401, not 404
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.list_user_repositories()

        # Verify it's not treated as 404
        assert "401" not in str(
            exc_info.value
        ) or "Failed to list repositories:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_list_endpoint_server_error_handling(
        self, repository_client
    ):
        """Investigate server-side error responses that might appear as 404."""
        # Mock server error scenarios
        error_scenarios = [
            (500, "Internal Server Error"),
            (503, "Service Unavailable"),
            (404, "Not Found"),  # Actual 404
        ]

        for status_code, detail in error_scenarios:
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = status_code
            mock_response.json.return_value = {"detail": detail}

            repository_client._authenticated_request = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(ActivationError) as exc_info:
                await repository_client.list_user_repositories()

            # All should be handled as ActivationError
            assert "Failed to list repositories:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_list_endpoint_malformed_response_handling(
        self, repository_client
    ):
        """Investigate handling of malformed JSON responses."""
        # Mock malformed response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            # Missing "repositories" key
            "data": [],
            "count": 0,
        }

        repository_client._authenticated_request = AsyncMock(return_value=mock_response)

        # This should handle missing "repositories" key gracefully
        result = await repository_client.list_user_repositories()

        # Should default to empty list if "repositories" key missing
        assert result == []

    @pytest.mark.asyncio
    async def test_repository_list_endpoint_network_error_manifestation(
        self, repository_client
    ):
        """Investigate if network errors appear as 404."""
        # Mock network connection error
        from src.code_indexer.api_clients.base_client import APIClientError

        async def mock_request_with_network_error(*args, **kwargs):
            raise APIClientError("Connection failed", status_code=None)

        repository_client._authenticated_request = AsyncMock(
            side_effect=mock_request_with_network_error
        )

        # Network errors should be wrapped appropriately
        with pytest.raises(ActivationError) as exc_info:
            await repository_client.list_user_repositories()

        # Should not appear as 404
        assert "Failed to list repositories:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_client_repository_list_404_specific_investigation(
        self, query_client
    ):
        """Investigate query client specific 404 behavior."""
        # Mock true 404 response
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}

        query_client._authenticated_request = AsyncMock(return_value=mock_response)

        # Query client should handle 404 gracefully
        with pytest.raises(APIClientError) as exc_info:
            await query_client.list_repositories()

        assert "Failed to list repositories:" in str(exc_info.value)

        # Verify correct endpoint usage
        call_args = query_client._authenticated_request.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "/api/repos"

    @pytest.mark.asyncio
    async def test_repository_endpoint_discovery_via_error_patterns(
        self, repository_client
    ):
        """Test to discover if endpoint URL issues cause 404s."""
        # Test various potential endpoint URL issues
        endpoint_variations = [
            "/api/repos",  # Correct
            "/api/repos/",  # With trailing slash
            "api/repos",  # Missing leading slash
            "/api/repositories",  # Alternative endpoint name
        ]

        for endpoint in endpoint_variations:
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = 404
            mock_response.json.return_value = {"detail": "Not Found"}

            # Mock to test different endpoints
            async def mock_with_endpoint(*args, **kwargs):
                # Verify which endpoint is being called
                called_endpoint = args[1]
                if called_endpoint == endpoint:
                    return mock_response
                else:
                    # Different endpoint, return success
                    success_response = MagicMock(spec=Response)
                    success_response.status_code = 200
                    success_response.json.return_value = {"repositories": []}
                    return success_response

            repository_client._authenticated_request = AsyncMock(
                side_effect=mock_with_endpoint
            )

            try:
                await repository_client.list_user_repositories()
                # If this succeeds, the endpoint works
                call_args = repository_client._authenticated_request.call_args
                actual_endpoint = call_args[0][1]
                print(f"SUCCESS: Endpoint {actual_endpoint} works")
            except ActivationError:
                # Expected for 404s
                call_args = repository_client._authenticated_request.call_args
                actual_endpoint = call_args[0][1]
                print(f"404: Endpoint {actual_endpoint} returns Not Found")

    @pytest.mark.asyncio
    async def test_server_route_registration_simulation(self, repository_client):
        """Simulate server route registration issues that could cause 404."""
        # This test simulates what happens if server routes aren't properly registered

        # Mock scenarios:
        # 1. Route exists and works
        # 2. Route missing (true 404)
        # 3. Route exists but dependencies fail

        scenarios = [
            ("route_exists", 200, {"repositories": []}),
            ("route_missing", 404, {"detail": "Not Found"}),
            ("dependency_fails", 422, {"detail": "Dependency injection failed"}),
            ("auth_required", 401, {"detail": "Authentication required"}),
        ]

        for scenario_name, status_code, response_data in scenarios:
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = status_code
            mock_response.json.return_value = response_data

            repository_client._authenticated_request = AsyncMock(
                return_value=mock_response
            )

            if status_code == 200:
                # Should succeed
                result = await repository_client.list_user_repositories()
                assert isinstance(result, list)
                print(f"SCENARIO {scenario_name}: SUCCESS")
            else:
                # Should fail with appropriate error
                with pytest.raises(ActivationError):
                    await repository_client.list_user_repositories()
                print(
                    f"SCENARIO {scenario_name}: FAILED as expected (status {status_code})"
                )

    @pytest.mark.asyncio
    async def test_real_vs_mocked_404_behavior_comparison(self, repository_client):
        """Compare real 404 vs potential false 404s from other issues."""

        # Test cases that could masquerade as 404:
        test_cases = [
            ("true_404", 404, "Endpoint not found"),
            ("auth_failure", 401, "Token invalid"),
            ("server_error", 500, "Internal error"),
            ("bad_request", 400, "Malformed request"),
            ("forbidden", 403, "Access denied"),
        ]

        for case_name, status_code, detail in test_cases:
            mock_response = MagicMock(spec=Response)
            mock_response.status_code = status_code
            mock_response.json.return_value = {"detail": detail}

            repository_client._authenticated_request = AsyncMock(
                return_value=mock_response
            )

            with pytest.raises(ActivationError) as exc_info:
                await repository_client.list_user_repositories()

            error_msg = str(exc_info.value)

            # Analyze error patterns
            if status_code == 404:
                assert "Failed to list repositories:" in error_msg
                print(f"TRUE 404: {error_msg}")
            else:
                assert "Failed to list repositories:" in error_msg
                print(f"MASQUERADING AS 404 (actually {status_code}): {error_msg}")

            # The key insight: all errors currently get wrapped as ActivationError
            # The actual status code information might be lost
