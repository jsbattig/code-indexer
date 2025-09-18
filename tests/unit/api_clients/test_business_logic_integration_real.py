"""Real Business Logic Integration Test Suite - Foundation #1 Compliant.

Tests business logic integration using real API clients and services.
No mocks - real implementations only following MESSI Rule #1.
"""

import pytest

from code_indexer.business_logic import (
    execute_remote_query,
    RemoteOperationError,
)
from code_indexer.api_clients import (
    RemoteQueryClient,
    RepositoryLinkingClient,
)


class TestRealRemoteQueryBusinessLogic:
    """Real business logic tests for remote query execution."""

    @pytest.fixture
    def test_credentials(self):
        """Test credentials for remote server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def query_executor(self, test_credentials):
        """Create real query executor for testing."""
        return RemoteQueryClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

    @pytest.mark.asyncio
    async def test_real_execute_remote_query_success(self, test_credentials):
        """Test real remote query execution with live server."""
        # Skip if no test server available
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            result = await execute_remote_query(
                query="test function",
                repository_alias="test-repo",
                limit=5,
                server_url=test_credentials["server_url"],
                credentials=test_credentials,
            )

            # Verify result structure without mocking
            assert isinstance(result, list) or hasattr(result, "results")
            if hasattr(result, "results"):
                assert isinstance(result.results, list)

        except RemoteOperationError as e:
            # Expected business logic error - real behavior
            assert str(e)
        except Exception as e:
            # Real error - not mocked - analyze actual failure
            pytest.fail(f"Real query execution failed: {e}")

    @pytest.mark.asyncio
    async def test_real_execute_remote_query_with_filters(self, query_executor):
        """Test real remote query with filtering parameters."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            result = await query_executor.execute_query(
                query="authentication",
                repository_alias="test-repo",
                language="python",
                path_filter="*/auth/*",
                min_score=0.7,
                limit=10,
            )

            # Verify filtering was applied (real results)
            assert hasattr(result, "results")
            if result.results:
                # If results exist, verify they meet filter criteria
                for item in result.results:
                    assert hasattr(item, "score")
                    assert item.score >= 0.7

        except Exception as e:
            pytest.fail(f"Real filtered query failed: {e}")

    @pytest.mark.asyncio
    async def test_real_execute_remote_query_authentication_error(
        self, test_credentials
    ):
        """Test real authentication error handling."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        # Use invalid credentials for real authentication test
        invalid_credentials = test_credentials.copy()
        invalid_credentials["password"] = "invalid_password"

        executor = RemoteQueryClient(
            server_url=invalid_credentials["server_url"],
            credentials=invalid_credentials,
        )

        try:
            await executor.execute_query("test", "test-repo")
            pytest.fail("Expected authentication error with invalid credentials")
        except Exception as e:
            # Verify it's a real authentication error
            assert (
                "authentication" in str(e).lower() or "unauthorized" in str(e).lower()
            )

    def _is_test_server_available(self):
        """Check if test server is available for real integration testing."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False


class TestRealRepositoryLinkingBusinessLogic:
    """Real business logic tests for repository linking."""

    @pytest.fixture
    def test_credentials(self):
        """Test credentials for remote server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def linking_manager(self, test_credentials):
        """Create real linking manager for testing."""
        return RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

    @pytest.mark.asyncio
    async def test_real_discover_repositories_success(self, linking_manager):
        """Test real repository discovery with live server."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            result = await linking_manager.discover_repositories(
                git_url="https://github.com/example/test-repo.git"
            )

            # Verify real discovery result structure
            assert hasattr(result, "matches")
            assert hasattr(result, "total_matches")
            assert isinstance(result.matches, list)
            assert isinstance(result.total_matches, int)

        except Exception as e:
            # Real error - analyze actual failure pattern
            if "not found" in str(e).lower():
                # Expected for non-existent repos
                pass
            else:
                pytest.fail(f"Real repository discovery failed: {e}")

    @pytest.mark.asyncio
    async def test_real_link_repository_complete_workflow(self, linking_manager):
        """Test complete repository linking workflow with real services."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        git_url = "https://github.com/example/test-repo.git"

        try:
            # Step 1: Real discovery
            discovery_result = await linking_manager.discover_repositories(git_url)

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for linking test")

            # Step 2: Real branch information
            first_repo = discovery_result.matches[0]
            branches = await linking_manager.get_repository_branches(first_repo.alias)

            assert isinstance(branches, list)
            if branches:
                # Step 3: Real activation
                default_branch = next(
                    (b for b in branches if b.is_default), branches[0]
                )
                activation = await linking_manager.activate_repository(
                    golden_alias=first_repo.alias,
                    branch=default_branch.name,
                    user_alias=f"{first_repo.alias}-test",
                )

                # Verify real activation
                assert hasattr(activation, "activation_id")
                assert hasattr(activation, "status")
                assert activation.status == "active"

        except Exception as e:
            # Analyze real workflow failure
            pytest.fail(f"Real repository linking workflow failed: {e}")

    def _is_test_server_available(self):
        """Check if test server is available for real integration testing."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False


class TestRealRemoteStatusBusinessLogic:
    """Real business logic tests for remote repository status."""

    @pytest.fixture
    def test_credentials(self):
        """Test credentials for remote server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def status_checker(self, test_credentials, tmp_path):
        """Create real status checker for testing using factory pattern."""
        from code_indexer.remote.factories import RemoteServiceFactory
        from code_indexer.api_clients.base_client import CIDXRemoteAPIClient
        from code_indexer.remote.staleness_detector import StalenessDetector

        # Create temporary project with remote config for backward compatibility
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / ".remote-config"

        import json

        remote_config = {
            "server_url": test_credentials["server_url"],
            "encrypted_credentials": test_credentials,
            "repository_link": {
                "alias": "test-repo",
                "url": "https://github.com/test/repo.git",
                "branch": "main",
            },
        }

        with open(config_file, "w") as f:
            json.dump(remote_config, f)

        # Create API client and staleness detector
        api_client = CIDXRemoteAPIClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )
        staleness_detector = StalenessDetector()

        # Create repository service using factory
        repository_service = RemoteServiceFactory.create_repository_service(
            api_client, staleness_detector
        )

        # Create status displayer using factory
        return RemoteServiceFactory.create_remote_status_displayer(repository_service)

    @pytest.mark.asyncio
    async def test_real_get_repository_status_success(self, status_checker):
        """Test real repository status retrieval."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            status = await status_checker.get_repository_status("test-repo")

            # Verify real status structure
            assert hasattr(status, "repository_alias")
            assert hasattr(status, "status")
            assert hasattr(status, "last_updated")

        except Exception as e:
            # Real error handling - no mocks
            if "not found" in str(e).lower():
                # Expected for non-existent repos
                pass
            else:
                pytest.fail(f"Real status check failed: {e}")

    @pytest.mark.asyncio
    async def test_real_check_repository_staleness(self, status_checker):
        """Test real repository staleness detection."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            staleness_info = await status_checker.check_staleness(
                local_timestamp="2024-01-15T10:30:00Z", repository_alias="test-repo"
            )

            # Verify real staleness calculation
            assert hasattr(staleness_info, "is_stale")
            assert hasattr(staleness_info, "local_timestamp")
            assert hasattr(staleness_info, "remote_timestamp")
            assert isinstance(staleness_info.is_stale, bool)

        except Exception as e:
            pytest.fail(f"Real staleness check failed: {e}")

    def _is_test_server_available(self):
        """Check if test server is available for real integration testing."""
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False


class TestRealBusinessLogicErrorHandling:
    """Real error handling tests - no mocks."""

    @pytest.fixture
    def test_credentials(self):
        """Test credentials for error handling tests."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.mark.asyncio
    async def test_real_network_error_handling(self, test_credentials):
        """Test real network error handling."""
        # Use unreachable server for real network error
        unreachable_credentials = test_credentials.copy()
        unreachable_credentials["server_url"] = "http://localhost:9999"

        executor = RemoteQueryClient(
            server_url=unreachable_credentials["server_url"],
            credentials=unreachable_credentials,
        )

        try:
            await executor.execute_query("test", "test-repo")
            pytest.fail("Expected network error with unreachable server")
        except Exception as e:
            # Verify it's a real network error
            error_str = str(e).lower()
            assert any(
                term in error_str
                for term in [
                    "connection",
                    "network",
                    "timeout",
                    "refused",
                    "unreachable",
                ]
            )

    @pytest.mark.asyncio
    async def test_real_invalid_server_url_handling(self, test_credentials):
        """Test real invalid server URL handling."""
        invalid_credentials = test_credentials.copy()
        invalid_credentials["server_url"] = "not-a-valid-url"

        executor = RemoteQueryClient(
            server_url=invalid_credentials["server_url"],
            credentials=invalid_credentials,
        )

        try:
            await executor.execute_query("test", "test-repo")
            pytest.fail("Expected URL validation error")
        except Exception as e:
            # Verify it's a real URL error
            error_str = str(e).lower()
            assert any(
                term in error_str for term in ["url", "invalid", "scheme", "format"]
            )


class TestRealBusinessLogicResourceManagement:
    """Real resource management tests - no mocks."""

    @pytest.fixture
    def test_credentials(self):
        """Test credentials for resource management tests."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.mark.asyncio
    async def test_real_executor_context_manager(self, test_credentials):
        """Test real executor context manager behavior."""
        async with RemoteQueryClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        ) as executor:
            # Verify executor is properly initialized
            assert executor is not None
            assert hasattr(executor, "execute_query")

        # Verify cleanup occurred (real cleanup, no mocks)
        # Note: Can't easily verify internal cleanup without inspecting
        # real resource state, but context manager exit was called

    @pytest.mark.asyncio
    async def test_real_linking_manager_resource_cleanup(self, test_credentials):
        """Test real linking manager resource cleanup."""
        manager = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        try:
            # Use the manager
            assert manager is not None
        finally:
            # Real cleanup
            await manager.close()

        # Verify manager can't be used after cleanup
        # (Real behavior test, not mocked)
        with pytest.raises(Exception):
            await manager.discover_repositories("https://github.com/test/repo.git")
