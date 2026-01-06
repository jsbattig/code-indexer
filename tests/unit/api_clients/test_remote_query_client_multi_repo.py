"""Real Test Suite for Remote Query Client Multi-Repository Search.

Foundation #1 Compliance: Zero mocks implementation using real infrastructure.
All operations use real HTTP servers, real query execution, and authentic responses.

Tests for Story #676: CLI Multi-Repository Query Support.
"""

import pytest
import pytest_asyncio

from code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
    QueryExecutionError,
)

# Import real infrastructure (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext

# Import test isolation utilities
from tests.unit.api_clients.test_isolation_utils import (
    MockIsolationManager,
    skip_if_no_server,
    with_rate_limit_protection,
    create_test_credentials,
)


class TestRemoteQueryClientMultiRepo:
    """Test multi-repository search with real server infrastructure."""

    @pytest_asyncio.fixture
    async def isolation_manager(self):
        """Test isolation manager for preventing rate limit contamination."""
        manager = MockIsolationManager()
        yield manager

    @pytest_asyncio.fixture
    async def real_server_with_multiple_repos(self, isolation_manager):
        """Real server with multiple test repositories."""
        await skip_if_no_server()

        async with CIDXServerTestContext() as server:
            # Reset rate limits before setting up server
            await isolation_manager.rate_limit_manager.reset_rate_limits()

            # Add multiple test repositories
            server.add_test_repository(
                repo_id="auth-repo",
                name="Authentication Service",
                path="/services/auth",
                branches=["main", "develop"],
                default_branch="main",
            )

            server.add_test_repository(
                repo_id="api-repo",
                name="API Gateway",
                path="/services/api",
                branches=["main", "staging"],
                default_branch="main",
            )

            server.add_test_repository(
                repo_id="frontend-repo",
                name="Frontend Application",
                path="/apps/frontend",
                branches=["main"],
                default_branch="main",
            )

            yield server

    @pytest.fixture
    def real_credentials(self):
        """Real credentials for server authentication."""
        return create_test_credentials("testuser")

    @pytest_asyncio.fixture
    async def real_query_client(
        self, real_server_with_multiple_repos, real_credentials, isolation_manager
    ):
        """Real query client with proper isolation and cleanup."""
        client = RemoteQueryClient(
            server_url=real_server_with_multiple_repos.base_url,
            credentials=real_credentials,
        )

        # Setup isolation for this client
        await isolation_manager.setup_isolated_test("multi_repo_query_client")

        yield client

        # Proper cleanup with isolation
        await client.close()
        await isolation_manager.teardown_isolated_test("multi_repo_query_client")

    @pytest.mark.asyncio
    async def test_execute_multi_repo_query_success(self, real_query_client):
        """Test successful multi-repository query with real server."""

        async def execute_query():
            return await real_query_client.execute_multi_repo_query(
                repositories=["auth-repo", "api-repo"],
                query="authentication",
                limit=5,
                search_type="semantic",
            )

        results = await with_rate_limit_protection(execute_query)

        # Verify response structure
        assert isinstance(results, dict)
        assert "results" in results
        assert "metadata" in results

        # Verify results contains repository mappings
        assert isinstance(results["results"], dict)

        # Verify metadata
        metadata = results["metadata"]
        assert "total_results" in metadata
        assert "total_repos_searched" in metadata
        assert "execution_time_ms" in metadata
        assert isinstance(metadata["total_results"], int)
        assert isinstance(metadata["total_repos_searched"], int)
        assert isinstance(metadata["execution_time_ms"], int)

    @pytest.mark.asyncio
    async def test_execute_multi_repo_query_empty_repos_list(self, real_query_client):
        """Test multi-repo query with empty repositories list raises ValueError."""

        with pytest.raises((ValueError, QueryExecutionError)):
            await real_query_client.execute_multi_repo_query(
                repositories=[],
                query="test query",
                limit=5,
                search_type="semantic",
            )

    @pytest.mark.asyncio
    async def test_execute_multi_repo_query_invalid_search_type(
        self, real_query_client
    ):
        """Test multi-repo query with invalid search type raises error."""

        async def execute_query():
            return await real_query_client.execute_multi_repo_query(
                repositories=["auth-repo"],
                query="test query",
                limit=5,
                search_type="invalid_type",
            )

        # Should raise error for invalid search type
        with pytest.raises((ValueError, QueryExecutionError)):
            await with_rate_limit_protection(execute_query)
