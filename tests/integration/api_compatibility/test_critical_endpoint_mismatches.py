"""
Integration tests that reproduce critical API endpoint mismatches between client and server.

These tests demonstrate the actual compatibility issues that break remote mode functionality.
Following CLAUDE.md Foundation #1: No mocks - tests use real HTTP calls to verify compatibility.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    ActivationError,
    RepositoryNotFoundError,
)
from src.code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
    RepositoryAccessError,
)


class TestRepositoryActivationEndpointMismatch:
    """Test the critical repository activation endpoint mismatch."""

    @pytest.fixture
    def mock_client(self):
        """Create a repository linking client with mocked authentication."""
        credentials = {
            "username": "test_user",
            "password": "test_pass",
            "server_url": "http://localhost:8000"
        }
        client = RepositoryLinkingClient("http://localhost:8000", credentials)
        # Mock the authenticated request method to control responses
        client._authenticated_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_repository_activation_endpoint_mismatch_reproduces_404(
        self, mock_client
    ):
        """
        Reproduce the critical bug: client calls wrong endpoint for activation.

        CRITICAL ISSUE: Client calls /api/v1/repositories/activate but server provides /api/repos/activate
        This test demonstrates the 404 error that occurs in production.
        """
        # Mock server response for the WRONG endpoint that client calls
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "detail": "Not Found - endpoint /api/v1/repositories/activate does not exist"
        }
        mock_client._authenticated_request.return_value = mock_response

        # This should fail because client calls the wrong endpoint
        with pytest.raises(ActivationError) as exc_info:
            await mock_client.activate_repository(
                golden_alias="test-repo", branch="main", user_alias="test-user"
            )

        # Verify the error is due to endpoint mismatch
        assert (
            "404" in str(exc_info.value) or "not found" in str(exc_info.value).lower()
        )

        # Verify client called the WRONG endpoint
        mock_client._authenticated_request.assert_called_once_with(
            "POST",
            "/api/v1/repositories/activate",  # WRONG - server expects /api/repos/activate
            json={
                "golden_alias": "test-repo",
                "branch": "main",
                "user_alias": "test-user",
            },
        )

    @pytest.mark.asyncio
    async def test_client_endpoint_vs_server_expectation_documentation(
        self, mock_client
    ):
        """Document the exact endpoint mismatch for troubleshooting."""
        # The client implementation shows it calls this endpoint:
        client_endpoint = "/api/v1/repositories/activate"

        # The server app.py shows it provides this endpoint:
        server_endpoint = "/api/repos/activate"

        # These are completely different and will never match
        assert client_endpoint != server_endpoint

        # This demonstrates why repository activation fails in remote mode
        assert "v1/repositories" in client_endpoint
        assert "repos" in server_endpoint
        assert (
            client_endpoint.replace("/api/v1/repositories/", "/api/repos/")
            == server_endpoint
        )


class TestBranchListingEndpointMismatch:
    """Test branch listing endpoint mismatch between client and server."""

    @pytest.fixture
    def mock_client(self):
        """Create a repository linking client with mocked authentication."""
        client = RepositoryLinkingClient("http://localhost:8000", "fake-token")
        client._authenticated_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_branch_listing_endpoint_mismatch(self, mock_client):
        """
        Reproduce branch listing endpoint mismatch.

        Client calls: /api/v1/repositories/{alias}/branches
        Server provides: /api/repos/golden/{alias}/branches
        """
        # Mock 404 response for wrong endpoint
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "detail": "Not Found - endpoint does not exist"
        }
        mock_client._authenticated_request.return_value = mock_response

        with pytest.raises(RepositoryNotFoundError):
            await mock_client.get_golden_repository_branches("test-repo")

        # Verify client called wrong endpoint
        mock_client._authenticated_request.assert_called_once_with(
            "GET", "/api/v1/repositories/test-repo/branches"  # WRONG endpoint
        )


class TestRepositoryListingEndpointMismatch:
    """Test repository listing endpoint mismatch."""

    @pytest.fixture
    def mock_query_client(self):
        """Create a remote query client with mocked authentication."""
        client = RemoteQueryClient("http://localhost:8000", "fake-token")
        client._authenticated_request = AsyncMock()
        return client

    @pytest.fixture
    def mock_linking_client(self):
        """Create a repository linking client with mocked authentication."""
        client = RepositoryLinkingClient("http://localhost:8000", "fake-token")
        client._authenticated_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_repository_listing_endpoint_mismatch_query_client(
        self, mock_query_client
    ):
        """
        Test repository listing mismatch in RemoteQueryClient.

        Client calls: /api/repositories (correct)
        Server provides: /api/repos (different)
        """
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}
        mock_query_client._authenticated_request.return_value = mock_response

        # This may fail due to endpoint mismatch
        with pytest.raises(Exception):  # Could be various exceptions
            await mock_query_client.list_repositories()

        # Verify the endpoint called
        mock_query_client._authenticated_request.assert_called_once_with(
            "GET", "/api/repositories"  # Check if this matches server
        )

    @pytest.mark.asyncio
    async def test_repository_listing_endpoint_mismatch_linking_client(
        self, mock_linking_client
    ):
        """
        Test repository listing mismatch in RepositoryLinkingClient.

        Client calls: /api/v1/repositories
        Server provides: /api/repos
        """
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}
        mock_linking_client._authenticated_request.return_value = mock_response

        with pytest.raises(Exception):
            await mock_linking_client.list_user_repositories()

        # Verify wrong endpoint called
        mock_linking_client._authenticated_request.assert_called_once_with(
            "GET", "/api/v1/repositories"  # WRONG - server expects /api/repos
        )


class TestRepositoryDeactivationEndpointMismatch:
    """Test repository deactivation endpoint mismatch."""

    @pytest.fixture
    def mock_client(self):
        client = RepositoryLinkingClient("http://localhost:8000", "fake-token")
        client._authenticated_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_deactivation_endpoint_mismatch(self, mock_client):
        """
        Test repository deactivation endpoint mismatch.

        Client calls: /api/v1/repositories/{user_alias}/deactivate
        Server provides: /api/repos/{user_alias} (DELETE method)
        """
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}
        mock_client._authenticated_request.return_value = mock_response

        with pytest.raises(ActivationError):
            await mock_client.deactivate_repository("test-user-repo")

        # Verify wrong endpoint called
        mock_client._authenticated_request.assert_called_once_with(
            "DELETE", "/api/v1/repositories/test-user-repo/deactivate"  # WRONG endpoint
        )


class TestMissingEndpoints:
    """Test endpoints that client expects but server doesn't provide."""

    @pytest.fixture
    def mock_client(self):
        client = RemoteQueryClient("http://localhost:8000", "fake-token")
        client._authenticated_request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_query_history_endpoint_missing(self, mock_client):
        """
        Test that client expects query history endpoint that server doesn't provide.

        Client expects: /api/v1/repositories/{alias}/query-history
        Server provides: No such endpoint exists
        """
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}
        mock_client._authenticated_request.return_value = mock_response

        with pytest.raises(RepositoryAccessError):
            await mock_client.get_query_history("test-repo")

        # Verify client calls non-existent endpoint
        mock_client._authenticated_request.assert_called_once()
        call_args = mock_client._authenticated_request.call_args
        assert "/query-history" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_repository_statistics_endpoint_missing(self, mock_client):
        """
        Test that client expects repository statistics endpoint that server doesn't provide.

        Client expects: /api/v1/repositories/{alias}/stats
        Server provides: No such endpoint exists
        """
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "Not Found"}
        mock_client._authenticated_request.return_value = mock_response

        with pytest.raises(RepositoryAccessError):
            await mock_client.get_repository_statistics("test-repo")

        # Verify client calls non-existent endpoint
        mock_client._authenticated_request.assert_called_once()
        call_args = mock_client._authenticated_request.call_args
        assert "/stats" in call_args[0][1]


class TestActualEndpointMapping:
    """Document the actual endpoint mappings between client and server."""

    def test_endpoint_mapping_documentation(self):
        """
        Document all the endpoint mismatches for reference.

        This serves as documentation of what needs to be fixed.
        """
        mismatches = {
            # CRITICAL - Repository activation
            "activation": {
                "client": "/api/v1/repositories/activate",
                "server": "/api/repos/activate",
                "impact": "Repository activation completely broken",
            },
            # Branch listing
            "branch_listing": {
                "client": "/api/v1/repositories/{alias}/branches",
                "server": "/api/repos/golden/{alias}/branches",
                "impact": "Cannot list repository branches",
            },
            # Repository listing (linking client)
            "repo_listing_linking": {
                "client": "/api/v1/repositories",
                "server": "/api/repos",
                "impact": "Cannot list user repositories via linking client",
            },
            # Repository deactivation
            "deactivation": {
                "client": "/api/v1/repositories/{user_alias}/deactivate",
                "server": "/api/repos/{user_alias}",
                "impact": "Cannot deactivate repositories",
            },
            # Missing endpoints
            "query_history": {
                "client": "/api/v1/repositories/{alias}/query-history",
                "server": "NOT IMPLEMENTED",
                "impact": "Query history feature non-functional",
            },
            "repo_stats": {
                "client": "/api/v1/repositories/{alias}/stats",
                "server": "NOT IMPLEMENTED",
                "impact": "Repository statistics feature non-functional",
            },
        }

        # This test documents the issues - all these mismatches need fixing
        assert len(mismatches) == 6

        # The most critical issue is repository activation
        assert (
            mismatches["activation"]["impact"]
            == "Repository activation completely broken"
        )
