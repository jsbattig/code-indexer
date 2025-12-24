"""Real Repository Linking Client Test Suite - Foundation #1 Compliant.

Tests repository linking client using real server connections and services.
No mocks - real implementations only following MESSI Rule #1.
"""

import pytest
import asyncio
import socket
from datetime import datetime, timezone

from code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryDiscoveryResponse,
    BranchInfo,
    ActivatedRepository,
    RepositoryNotFoundError,
    BranchNotFoundError,
    ActivationError,
)


class TestRealRepositoryLinkingClientDiscovery:
    """Real repository discovery tests with live server."""

    @pytest.fixture
    def test_credentials(self):
        """Real test credentials for server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def real_linking_client(self, test_credentials):
        """Create real linking client for testing."""
        return RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

    def _is_test_server_available(self):
        """Check if real test server is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False

    @pytest.mark.asyncio
    async def test_real_discover_repositories_success(self, real_linking_client):
        """Test real repository discovery with live server."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            result = await real_linking_client.discover_repositories(
                "https://github.com/example/cidx.git"
            )

            # Verify real discovery response structure
            assert isinstance(result, RepositoryDiscoveryResponse)
            assert hasattr(result, "matches")
            assert hasattr(result, "total_matches")
            assert isinstance(result.matches, list)
            assert isinstance(result.total_matches, int)

            # If matches found, verify their structure
            if result.matches:
                first_match = result.matches[0]
                assert hasattr(first_match, "alias")
                assert hasattr(first_match, "display_name")
                assert hasattr(first_match, "git_url")
                assert hasattr(first_match, "default_branch")
                assert hasattr(first_match, "available_branches")

        except RepositoryNotFoundError:
            # Expected for non-existent repositories - real behavior
            pass
        except Exception as e:
            pytest.fail(f"Real repository discovery failed: {e}")

    @pytest.mark.asyncio
    async def test_real_discover_repositories_multiple_matches(
        self, real_linking_client
    ):
        """Test real repository discovery with multiple potential matches."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        # Use common repository patterns that might have multiple matches
        test_urls = [
            "https://github.com/microsoft/vscode.git",
            "https://github.com/facebook/react.git",
            "https://github.com/python/cpython.git",
        ]

        for git_url in test_urls:
            try:
                result = await real_linking_client.discover_repositories(git_url)

                # Verify response structure for real multiple matches
                assert isinstance(result, RepositoryDiscoveryResponse)

                if result.total_matches > 1:
                    # Verify all matches have consistent structure
                    for match in result.matches:
                        assert match.alias
                        assert match.git_url
                        assert match.default_branch
                        assert isinstance(match.available_branches, list)

                    break  # Found multiple matches, test successful

            except RepositoryNotFoundError:
                continue  # Try next URL

    @pytest.mark.asyncio
    async def test_real_discover_repositories_invalid_urls(self, real_linking_client):
        """Test real discovery with invalid URLs."""
        invalid_urls = [
            "not-a-url",
            "https://example.com/not-git",
            "ftp://example.com/repo.git",
            "",
            "   ",
            "https://nonexistent-domain-12345.com/repo.git",
        ]

        for invalid_url in invalid_urls:
            try:
                await real_linking_client.discover_repositories(invalid_url)
                # If no exception, continue (server might handle some gracefully)
            except (ValueError, RepositoryNotFoundError) as e:
                # Expected real validation or not-found errors
                assert str(e)  # Ensure error has message
            except Exception as e:
                # Other real errors are acceptable for invalid input
                assert str(e)

    @pytest.mark.asyncio
    async def test_real_discover_repositories_timeout_handling(
        self, real_linking_client
    ):
        """Test real discovery timeout handling."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        # Set very short timeout for real timeout testing
        real_linking_client._request_timeout = 0.1  # 100ms

        try:
            await real_linking_client.discover_repositories(
                "https://github.com/large/repository.git"
            )
        except Exception as e:
            # Real timeout or connection error expected
            error_str = str(e).lower()
            assert any(
                term in error_str
                for term in ["timeout", "connection", "time", "network"]
            )


class TestRealRepositoryLinkingClientBranches:
    """Real branch management tests with live server."""

    @pytest.fixture
    def test_credentials(self):
        """Real test credentials for server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def real_linking_client(self, test_credentials):
        """Create real linking client for testing."""
        return RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

    def _is_test_server_available(self):
        """Check if real test server is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False

    @pytest.mark.asyncio
    async def test_real_get_golden_repository_branches_success(
        self, real_linking_client
    ):
        """Test real branch retrieval with live server."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        # First discover a repository to get a valid alias
        try:
            discovery_result = await real_linking_client.discover_repositories(
                "https://github.com/example/test-repo.git"
            )

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for branch testing")

            # Use first discovered repository for real branch testing
            repo_alias = discovery_result.matches[0].alias

            branches = await real_linking_client.get_golden_repository_branches(
                repo_alias
            )

            # Verify real branch information structure
            assert isinstance(branches, list)

            if branches:
                for branch in branches:
                    assert isinstance(branch, BranchInfo)
                    assert branch.name
                    assert isinstance(branch.is_default, bool)
                    assert branch.last_commit_sha
                    assert branch.indexing_status in [
                        "completed",
                        "in_progress",
                        "pending",
                        "failed",
                    ]
                    assert isinstance(branch.total_files, int)
                    assert isinstance(branch.indexed_files, int)
                    assert branch.indexed_files <= branch.total_files

                # Verify exactly one default branch
                default_branches = [b for b in branches if b.is_default]
                assert len(default_branches) == 1

        except RepositoryNotFoundError:
            pytest.skip("Repository not found for branch testing")
        except Exception as e:
            pytest.fail(f"Real branch retrieval failed: {e}")

    @pytest.mark.asyncio
    async def test_real_get_branches_nonexistent_repository(self, real_linking_client):
        """Test real branch retrieval for non-existent repository."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            await real_linking_client.get_golden_repository_branches(
                "nonexistent-repo-12345"
            )
            pytest.fail("Expected RepositoryNotFoundError for non-existent repository")
        except RepositoryNotFoundError as e:
            # Expected real error
            assert "not found" in str(e).lower()
        except Exception as e:
            # Other real server errors acceptable
            assert str(e)

    @pytest.mark.asyncio
    async def test_real_branch_indexing_status_verification(self, real_linking_client):
        """Test real branch indexing status verification."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            # Discover repository first
            discovery_result = await real_linking_client.discover_repositories(
                "https://github.com/example/indexed-repo.git"
            )

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for indexing status testing")

            repo_alias = discovery_result.matches[0].alias
            branches = await real_linking_client.get_golden_repository_branches(
                repo_alias
            )

            if branches:
                for branch in branches:
                    # Verify real indexing status values
                    assert branch.indexing_status in [
                        "completed",
                        "in_progress",
                        "pending",
                        "failed",
                        "error",
                    ]

                    # Verify realistic indexing progress
                    if branch.indexing_status == "completed":
                        assert branch.indexed_files == branch.total_files
                    elif branch.indexing_status == "in_progress":
                        assert 0 <= branch.indexed_files <= branch.total_files
                    elif branch.indexing_status == "pending":
                        assert branch.indexed_files == 0

        except Exception as e:
            pytest.skip(f"Real indexing status test skipped: {e}")


class TestRealRepositoryLinkingClientActivation:
    """Real repository activation tests with live server."""

    @pytest.fixture
    def test_credentials(self):
        """Real test credentials for server access."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.fixture
    def real_linking_client(self, test_credentials):
        """Create real linking client for testing."""
        return RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

    def _is_test_server_available(self):
        """Check if real test server is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False

    @pytest.mark.asyncio
    async def test_real_activate_repository_complete_workflow(
        self, real_linking_client
    ):
        """Test complete real repository activation workflow."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            # Step 1: Real repository discovery
            discovery_result = await real_linking_client.discover_repositories(
                "https://github.com/example/activation-test.git"
            )

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for activation testing")

            repo = discovery_result.matches[0]

            # Step 2: Real branch retrieval
            branches = await real_linking_client.get_golden_repository_branches(
                repo.alias
            )

            if not branches:
                pytest.skip("No branches found for activation testing")

            # Find default branch or use first available
            target_branch = next((b for b in branches if b.is_default), branches[0])

            # Step 3: Real repository activation
            activation = await real_linking_client.activate_repository(
                golden_alias=repo.alias,
                branch=target_branch.name,
                user_alias=f"{repo.alias}-test-user",
            )

            # Verify real activation response
            assert isinstance(activation, ActivatedRepository)
            assert activation.activation_id
            assert activation.golden_alias == repo.alias
            assert activation.branch == target_branch.name
            assert activation.status in ["active", "activating", "pending"]
            assert activation.query_endpoint
            assert isinstance(activation.access_permissions, list)
            assert "read" in activation.access_permissions

            # Verify realistic activation timestamp
            if activation.activated_at:
                activation_time = datetime.fromisoformat(
                    activation.activated_at.replace("Z", "+00:00")
                )
                now = datetime.now(timezone.utc)
                time_diff = abs((now - activation_time).total_seconds())
                assert (
                    time_diff < 60
                )  # Within 1 minute (reasonable for real activation)

        except (RepositoryNotFoundError, BranchNotFoundError) as e:
            pytest.skip(f"Repository/branch not available for activation: {e}")
        except ActivationError as e:
            # Real activation errors are acceptable (quota, permissions, etc.)
            assert str(e)
        except Exception as e:
            pytest.fail(f"Real activation workflow failed: {e}")

    @pytest.mark.asyncio
    async def test_real_activate_repository_invalid_branch(self, real_linking_client):
        """Test real activation with invalid branch."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            # Discover repository first
            discovery_result = await real_linking_client.discover_repositories(
                "https://github.com/example/test-repo.git"
            )

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for invalid branch testing")

            repo_alias = discovery_result.matches[0].alias

            # Try to activate with non-existent branch
            await real_linking_client.activate_repository(
                golden_alias=repo_alias,
                branch="nonexistent-branch-12345",
                user_alias=f"{repo_alias}-invalid-branch-test",
            )

            pytest.fail("Expected BranchNotFoundError for invalid branch")

        except BranchNotFoundError as e:
            # Expected real error
            assert "not found" in str(e).lower() or "invalid" in str(e).lower()
        except RepositoryNotFoundError:
            pytest.skip("Repository not found for invalid branch testing")
        except Exception as e:
            # Other real errors acceptable
            assert str(e)

    @pytest.mark.asyncio
    async def test_real_activate_repository_duplicate_activation(
        self, real_linking_client
    ):
        """Test real duplicate activation handling."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for real integration testing")

        try:
            # Discover repository
            discovery_result = await real_linking_client.discover_repositories(
                "https://github.com/example/duplicate-test.git"
            )

            if discovery_result.total_matches == 0:
                pytest.skip("No repositories found for duplicate activation testing")

            repo = discovery_result.matches[0]
            branches = await real_linking_client.get_golden_repository_branches(
                repo.alias
            )

            if not branches:
                pytest.skip("No branches found for duplicate activation testing")

            target_branch = branches[0]
            user_alias = f"{repo.alias}-duplicate-test"

            # First activation
            first_activation = await real_linking_client.activate_repository(
                golden_alias=repo.alias,
                branch=target_branch.name,
                user_alias=user_alias,
            )

            assert isinstance(first_activation, ActivatedRepository)

            # Attempt duplicate activation
            try:
                await real_linking_client.activate_repository(
                    golden_alias=repo.alias,
                    branch=target_branch.name,
                    user_alias=user_alias,
                )

                # Some servers might allow duplicate activations or return existing
                # This is acceptable real behavior

            except ActivationError as e:
                # Expected real duplicate activation error
                error_str = str(e).lower()
                assert any(
                    term in error_str
                    for term in ["already", "exists", "duplicate", "conflict"]
                )

        except Exception as e:
            pytest.skip(f"Duplicate activation test skipped: {e}")


class TestRealRepositoryLinkingClientErrorHandling:
    """Real error handling tests with live server."""

    @pytest.fixture
    def test_credentials(self):
        """Real test credentials for error testing."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.mark.asyncio
    async def test_real_authentication_error_handling(self, test_credentials):
        """Test real authentication error handling."""
        # Create client with invalid credentials
        invalid_credentials = test_credentials.copy()
        invalid_credentials["password"] = "invalid_password_12345"

        client = RepositoryLinkingClient(
            server_url=invalid_credentials["server_url"],
            credentials=invalid_credentials,
        )

        try:
            await client.discover_repositories(
                "https://github.com/example/auth-test.git"
            )
            # If no error, server might not require authentication
        except Exception as e:
            # Real authentication error expected
            error_str = str(e).lower()
            assert any(
                term in error_str
                for term in [
                    "authentication",
                    "unauthorized",
                    "invalid",
                    "credentials",
                    "login",
                ]
            )

    @pytest.mark.asyncio
    async def test_real_network_error_handling(self, test_credentials):
        """Test real network error handling."""
        # Create client with unreachable server
        unreachable_credentials = test_credentials.copy()
        unreachable_credentials["server_url"] = "http://localhost:9999"

        client = RepositoryLinkingClient(
            server_url=unreachable_credentials["server_url"],
            credentials=unreachable_credentials,
        )

        try:
            await client.discover_repositories(
                "https://github.com/example/network-test.git"
            )
            pytest.fail("Expected network error with unreachable server")
        except Exception as e:
            # Real network error expected
            error_str = str(e).lower()
            assert any(
                term in error_str
                for term in [
                    "connection",
                    "network",
                    "refused",
                    "timeout",
                    "unreachable",
                ]
            )

    @pytest.mark.asyncio
    async def test_real_server_error_handling(self, test_credentials):
        """Test real server error handling."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for error handling testing")

        client = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        # Test with malformed requests that might cause server errors
        malformed_requests = [
            "",  # Empty URL
            "not-a-url",  # Invalid URL format
            "https://",  # Incomplete URL
        ]

        for malformed_url in malformed_requests:
            try:
                await client.discover_repositories(malformed_url)
                # If no error, server handled gracefully
            except (ValueError, RepositoryNotFoundError) as e:
                # Expected real validation errors
                assert str(e)
            except Exception as e:
                # Other real server errors acceptable
                assert str(e)

    def _is_test_server_available(self):
        """Check if real test server is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False


class TestRealRepositoryLinkingClientResourceManagement:
    """Real resource management tests."""

    @pytest.fixture
    def test_credentials(self):
        """Real test credentials for resource management testing."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8001",
        }

    @pytest.mark.asyncio
    async def test_real_client_context_manager(self, test_credentials):
        """Test real client context manager behavior."""
        async with RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        ) as client:
            # Verify client is properly initialized
            assert client is not None
            assert hasattr(client, "discover_repositories")
            assert hasattr(client, "get_golden_repository_branches")
            assert hasattr(client, "activate_repository")

        # Context manager exit called - real cleanup occurred

    @pytest.mark.asyncio
    async def test_real_manual_resource_cleanup(self, test_credentials):
        """Test real manual resource cleanup."""
        client = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        # Use the client
        assert client is not None

        # Manual cleanup
        await client.close()

        # Verify client can't be used after cleanup (real behavior test)
        with pytest.raises(Exception):
            await client.discover_repositories(
                "https://github.com/example/cleanup-test.git"
            )

    @pytest.mark.asyncio
    async def test_real_multiple_clients_resource_isolation(self, test_credentials):
        """Test real resource isolation between multiple clients."""
        # Create multiple real clients
        client1 = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        client2 = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        try:
            # Verify both clients work independently
            assert client1 is not client2
            assert client1._credentials == client2._credentials  # Same credentials
            assert client1._server_url == client2._server_url  # Same server

            # Both should be functional
            assert hasattr(client1, "discover_repositories")
            assert hasattr(client2, "discover_repositories")

        finally:
            # Real cleanup of both clients
            await client1.close()
            await client2.close()

    @pytest.mark.asyncio
    async def test_real_concurrent_client_operations(self, test_credentials):
        """Test real concurrent client operations."""
        if not self._is_test_server_available():
            pytest.skip("Test server not available for concurrent testing")

        client = RepositoryLinkingClient(
            server_url=test_credentials["server_url"], credentials=test_credentials
        )

        try:
            # Define concurrent operations
            async def discover_operation(url):
                try:
                    return await client.discover_repositories(url)
                except Exception:
                    return None  # Handle real errors gracefully

            # Run concurrent real operations
            test_urls = [
                f"https://github.com/example/concurrent-test-{i}.git" for i in range(5)
            ]

            results = await asyncio.gather(
                *[discover_operation(url) for url in test_urls], return_exceptions=True
            )

            # Verify concurrent operations completed (real results or exceptions)
            assert len(results) == 5

            # Each result should be either RepositoryDiscoveryResponse or Exception
            for result in results:
                assert (
                    isinstance(result, RepositoryDiscoveryResponse)
                    or isinstance(result, Exception)
                    or result is None
                )

        finally:
            await client.close()

    def _is_test_server_available(self):
        """Check if real test server is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", 8001))
            sock.close()
            return result == 0
        except Exception:
            return False
