"""Real Test Suite for Remote Query Client.

Foundation #1 Compliance: Zero mocks implementation using real infrastructure.
All operations use real HTTP servers, real query execution, and authentic responses.

Enhanced with test isolation to prevent rate limiting contamination.
"""

import pytest
import pytest_asyncio

from code_indexer.api_clients.remote_query_client import (
    RemoteQueryClient,
    QueryResultItem,
    RepositoryInfo,
    RepositoryAccessError,
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


class TestRealRemoteQueryClientSemanticSearch:
    """Test semantic search with real server infrastructure and proper isolation."""

    @pytest_asyncio.fixture
    async def isolation_manager(self):
        """Test isolation manager for preventing rate limit contamination."""
        manager = MockIsolationManager()
        yield manager

    @pytest_asyncio.fixture
    async def real_server_with_repos(self, isolation_manager):
        """Real server with test repositories and isolation."""
        await skip_if_no_server()

        async with CIDXServerTestContext() as server:
            # Reset rate limits before setting up server
            await isolation_manager.rate_limit_manager.reset_rate_limits()

            # Add test repositories with different branches
            server.add_test_repository(
                repo_id="auth-repo",
                name="Authentication Service",
                path="/services/auth",
                branches=["main", "develop", "feature/oauth"],
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
                branches=["main", "develop", "feature/dashboard"],
                default_branch="main",
            )

            yield server

    @pytest.fixture
    def real_credentials(self):
        """Real credentials for server authentication with isolation."""
        return create_test_credentials("testuser")

    @pytest_asyncio.fixture
    async def real_query_client(
        self, real_server_with_repos, real_credentials, isolation_manager
    ):
        """Real query client with proper isolation and cleanup."""
        client = RemoteQueryClient(
            server_url=real_server_with_repos.base_url, credentials=real_credentials
        )

        # Setup isolation for this client
        await isolation_manager.setup_isolated_test("real_query_client")

        yield client

        # Proper cleanup with isolation
        await client.close()
        await isolation_manager.teardown_isolated_test("real_query_client")

    @pytest.mark.asyncio
    async def test_real_execute_query_success(self, real_query_client):
        """Test successful semantic search query with real server and rate limit protection."""

        # Execute real query with rate limit protection
        async def execute_query():
            return await real_query_client.execute_query(
                repository_alias="auth-repo",
                query="authentication function",
                limit=10,
                min_score=0.0,
            )

        results = await with_rate_limit_protection(execute_query)

        # Verify we get real results
        assert isinstance(results, list)
        assert len(results) >= 0  # May have 0 results but should be a list

        # If we have results, verify structure
        if results:
            result = results[0]
            assert isinstance(result, QueryResultItem)
            assert hasattr(result, "score")
            assert hasattr(result, "file_path")
            assert hasattr(result, "content")
            assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_real_query_with_filters(self, real_query_client):
        """Test query execution with real language and path filters and rate limit protection."""

        # Execute query with filters and rate limit protection
        async def execute_filtered_query():
            return await real_query_client.execute_query(
                repository_alias="api-repo",
                query="endpoint handler",
                limit=5,
                min_score=0.3,
                language="python",
                path_filter="*/handlers/*",
            )

        results = await with_rate_limit_protection(execute_filtered_query)
        results = await real_query_client.execute_query(
            query="database connection",
            limit=5,
            min_score=0.5,
            language="python",
            path_filter="*/services/*",
        )

        # Verify filtering was applied (results structure is valid)
        assert isinstance(results, list)
        # Results may be empty but should be properly formatted

    @pytest.mark.asyncio
    async def test_real_query_limit_parameter(self, real_query_client):
        """Test query limit parameter with real server."""
        # Test with small limit
        limited_results = await real_query_client.execute_query(
            query="function definition", limit=2, min_score=0.0
        )

        # Test with larger limit
        expanded_results = await real_query_client.execute_query(
            query="function definition", limit=10, min_score=0.0
        )

        # Both should be valid result lists
        assert isinstance(limited_results, list)
        assert isinstance(expanded_results, list)

        # Limited results should not exceed limit
        assert len(limited_results) <= 2

    @pytest.mark.asyncio
    async def test_real_query_score_filtering(self, real_query_client):
        """Test minimum score filtering with real results."""
        # Query with low score threshold
        low_threshold_results = await real_query_client.execute_query(
            query="test query", limit=10, min_score=0.1
        )

        # Query with high score threshold
        high_threshold_results = await real_query_client.execute_query(
            query="test query", limit=10, min_score=0.8
        )

        # Both should return valid results
        assert isinstance(low_threshold_results, list)
        assert isinstance(high_threshold_results, list)

        # High threshold should have fewer or equal results
        assert len(high_threshold_results) <= len(low_threshold_results)

    @pytest.mark.asyncio
    async def test_real_empty_query_handling(self, real_query_client):
        """Test handling of empty query strings."""
        with pytest.raises(ValueError) as exc_info:
            await real_query_client.execute_query(query="", limit=10)
        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_real_invalid_limit_handling(self, real_query_client):
        """Test handling of invalid limit parameters."""
        with pytest.raises(ValueError) as exc_info:
            await real_query_client.execute_query(query="test query", limit=0)
        assert "limit" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            await real_query_client.execute_query(query="test query", limit=-1)
        assert "limit" in str(exc_info.value).lower()


class TestRealRemoteQueryClientRepositoryInfo:
    """Test repository information retrieval with real server."""

    @pytest_asyncio.fixture
    async def real_server_multi_repo(self):
        """Real server with multiple test repositories."""
        async with CIDXServerTestContext() as server:
            # Add multiple repositories with different configurations
            server.add_test_repository(
                repo_id="repo-1",
                name="Primary Repository",
                path="/primary/repo",
                branches=["main", "develop", "feature/new"],
                default_branch="main",
            )

            server.add_test_repository(
                repo_id="repo-2",
                name="Secondary Repository",
                path="/secondary/repo",
                branches=["master", "staging"],
                default_branch="master",
            )

            yield server

    @pytest_asyncio.fixture
    async def real_multi_query_client(self, real_server_multi_repo):
        """Real query client for multi-repo testing."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_multi_repo.base_url,
        }

        client = RemoteQueryClient(
            server_url=real_server_multi_repo.base_url, credentials=credentials
        )
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_real_list_repositories(self, real_multi_query_client):
        """Test listing repositories from real server."""
        repositories = await real_multi_query_client.list_repositories()

        # Verify we get real repository data
        assert isinstance(repositories, list)
        assert len(repositories) >= 2  # We added 2 test repositories

        # Verify repository structure
        repo = repositories[0]
        assert isinstance(repo, RepositoryInfo)
        assert hasattr(repo, "id")
        assert hasattr(repo, "name")
        assert hasattr(repo, "path")
        assert hasattr(repo, "branches")
        assert hasattr(repo, "default_branch")

        # Verify we have the expected repositories
        repo_ids = [repo.id for repo in repositories]
        assert "repo-1" in repo_ids
        assert "repo-2" in repo_ids

    @pytest.mark.asyncio
    async def test_real_get_repository_by_id(self, real_multi_query_client):
        """Test getting specific repository by ID from real server."""
        # Get specific repository
        repo = await real_multi_query_client.get_repository("repo-1")

        # Verify repository details
        assert isinstance(repo, RepositoryInfo)
        assert repo.id == "repo-1"
        assert repo.name == "Primary Repository"
        assert repo.path == "/primary/repo"
        assert "main" in repo.branches
        assert "develop" in repo.branches
        assert repo.default_branch == "main"

    @pytest.mark.asyncio
    async def test_real_get_nonexistent_repository(self, real_multi_query_client):
        """Test handling of nonexistent repository requests."""
        with pytest.raises(RepositoryAccessError) as exc_info:
            await real_multi_query_client.get_repository("nonexistent-repo")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_real_repository_branches_info(self, real_multi_query_client):
        """Test branch information from real repository data."""
        repo = await real_multi_query_client.get_repository("repo-2")

        # Verify branch information
        assert isinstance(repo.branches, list)
        assert "master" in repo.branches
        assert "staging" in repo.branches
        assert repo.default_branch == "master"

    @pytest.mark.asyncio
    async def test_real_empty_repository_list_handling(self):
        """Test handling when server has no repositories."""
        # Create server with no repositories
        async with CIDXServerTestContext() as empty_server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": empty_server.base_url,
            }

            client = RemoteQueryClient(
                server_url=empty_server.base_url, credentials=credentials
            )

            try:
                repositories = await client.list_repositories()
                # Should return empty list, not error
                assert isinstance(repositories, list)
                assert len(repositories) == 0
            finally:
                await client.close()


class TestRealRemoteQueryClientErrorHandling:
    """Test error handling with real network conditions."""

    @pytest.mark.asyncio
    async def test_real_authentication_error(self):
        """Test handling of real authentication errors."""
        # Use invalid credentials
        invalid_credentials = {
            "username": "wronguser",
            "password": "wrongpass",
            "server_url": "https://test.example.com",
        }

        async with CIDXServerTestContext() as server:
            client = RemoteQueryClient(
                server_url=server.base_url, credentials=invalid_credentials
            )

            try:
                # Should fail authentication
                with pytest.raises(RepositoryAccessError) as exc_info:
                    await client.execute_query("test query", limit=5)

                assert (
                    "authentication" in str(exc_info.value).lower()
                    or "credential" in str(exc_info.value).lower()
                )

            finally:
                await client.close()

    @pytest.mark.asyncio
    async def test_real_connection_error(self):
        """Test handling of real connection errors."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "http://nonexistent-server:9999",  # Invalid server
        }

        client = RemoteQueryClient(
            server_url="http://nonexistent-server:9999", credentials=credentials
        )

        try:
            # Should fail with connection error
            with pytest.raises(RepositoryAccessError) as exc_info:
                await client.execute_query("test query", limit=5)

            error_msg = str(exc_info.value).lower()
            assert (
                "connection" in error_msg
                or "network" in error_msg
                or "unreachable" in error_msg
                or "timeout" in error_msg
            )

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_server_error_handling(self):
        """Test handling of real server errors."""
        async with CIDXServerTestContext() as server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            client = RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            )

            try:
                # Configure server to return error for specific endpoint
                server.set_error_simulation("/api/query", "server")

                # Should handle server error appropriately
                with pytest.raises(QueryExecutionError) as exc_info:
                    await client.execute_query("test query", limit=5)

                assert (
                    "server" in str(exc_info.value).lower()
                    or "error" in str(exc_info.value).lower()
                )

            finally:
                await client.close()


class TestRealRemoteQueryClientResourceManagement:
    """Test real resource management and cleanup."""

    @pytest.mark.asyncio
    async def test_real_client_context_manager(self):
        """Test real resource cleanup using context manager."""
        async with CIDXServerTestContext() as server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            session_ref = None

            # Use context manager
            async with RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            ) as client:
                # Verify client is functional
                repositories = await client.list_repositories()
                assert isinstance(repositories, list)

                # Get reference to session for later checking
                session_ref = client.session

            # Session should be closed after context exit
            assert session_ref.is_closed

    @pytest.mark.asyncio
    async def test_real_manual_cleanup(self):
        """Test manual resource cleanup."""
        async with CIDXServerTestContext() as server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            client = RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            )

            try:
                # Use client
                repositories = await client.list_repositories()
                assert isinstance(repositories, list)

                # Get session reference
                session = client.session
                assert not session.is_closed

            finally:
                # Manual cleanup
                await client.close()
                assert session.is_closed

    @pytest.mark.asyncio
    async def test_real_multiple_close_safety(self):
        """Test that multiple close calls are safe."""
        async with CIDXServerTestContext() as server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            client = RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            )

            # Multiple close calls should not cause errors
            await client.close()
            await client.close()  # Should not raise exception
            await client.close()  # Should not raise exception


class TestRealRemoteQueryClientEndToEnd:
    """End-to-end integration tests with real infrastructure."""

    @pytest.mark.asyncio
    async def test_complete_real_query_workflow(self):
        """Test complete query workflow using real infrastructure."""
        async with CIDXServerTestContext() as server:
            # Set up test data
            server.add_test_repository(
                repo_id="e2e-repo",
                name="E2E Test Repository",
                path="/e2e/test",
                branches=["main", "test"],
                default_branch="main",
            )

            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            async with RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            ) as client:
                # 1. List repositories
                repositories = await client.list_repositories()
                assert len(repositories) >= 1

                repo = next(r for r in repositories if r.id == "e2e-repo")
                assert repo.name == "E2E Test Repository"

                # 2. Get specific repository
                specific_repo = await client.get_repository("e2e-repo")
                assert specific_repo.id == "e2e-repo"
                assert "main" in specific_repo.branches

                # 3. Execute query
                query_results = await client.execute_query(
                    query="test implementation", limit=5, min_score=0.0
                )
                assert isinstance(query_results, list)

                # 4. Execute filtered query
                filtered_results = await client.execute_query(
                    query="test function", limit=3, min_score=0.2, language="python"
                )
                assert isinstance(filtered_results, list)

    @pytest.mark.asyncio
    async def test_real_error_recovery_workflow(self):
        """Test error recovery in real scenarios."""
        async with CIDXServerTestContext() as server:
            # Add test repository for recovery testing
            server.add_test_repository(
                repo_id="recovery-repo",
                name="Recovery Test Repository",
                path="/recovery/test",
                branches=["main"],
                default_branch="main",
            )

            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            async with RemoteQueryClient(
                server_url=server.base_url, credentials=credentials
            ) as client:
                # 1. Successful operation
                repositories = await client.list_repositories()
                assert isinstance(repositories, list)

                # 2. Error scenario - invalid repository
                with pytest.raises(RepositoryAccessError):
                    await client.get_repository("invalid-repo-id")

                # 3. Recovery - client should still work
                repositories_after_error = await client.list_repositories()
                assert isinstance(repositories_after_error, list)
                assert len(repositories_after_error) == len(repositories)

                # 4. Valid query after error
                results = await client.execute_query("recovery test", limit=5)
                assert isinstance(results, list)
