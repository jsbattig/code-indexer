"""TDD Failing Tests for Repository Linking Client Issues.

These tests reproduce the exact failures identified in the existing test suite
to ensure we fix the root causes with proper TDD methodology.
"""

import pytest

from code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryNotFoundError,
)
from code_indexer.api_clients.base_client import NetworkError


class TestRepositoryLinkingClientTDDFixes:
    """TDD tests to reproduce and fix specific issues."""

    @pytest.mark.asyncio
    async def test_authentication_error_when_server_unavailable_should_contain_auth_terms(
        self,
    ):
        """FAILING TEST: Connection errors should be properly classified for auth context.

        This test reproduces the issue where connection failures during authentication
        operations should be properly handled to indicate authentication-related problems
        rather than generic connection errors.
        """
        # Create client with test credentials pointing to unavailable server
        client = RepositoryLinkingClient(
            server_url="http://localhost:8001",
            credentials={"username": "test_user", "password": "test_password"},
        )

        try:
            # This will fail with connection error since no server is running
            await client.discover_repositories(
                "https://github.com/example/auth-test.git"
            )
            pytest.fail("Expected an error due to server unavailability")
        except Exception as e:
            error_str = str(e).lower()

            # This assertion will FAIL initially because connection errors
            # don't contain authentication-related terms
            assert any(
                term in error_str
                for term in [
                    "authentication",
                    "unauthorized",
                    "invalid",
                    "credentials",
                    "login",
                ]
            ), f"Error message should contain authentication-related terms, but got: {error_str}"
        finally:
            await client.close()

    def test_credentials_attribute_access_for_resource_isolation(self):
        """FAILING TEST: Client should expose credentials for resource isolation testing.

        This test reproduces the issue where tests need to access client credentials
        to verify resource isolation, but the attribute name doesn't match expectations.
        """
        # Create clients with same credentials
        test_credentials = {"username": "test_user", "password": "test_password"}

        client1 = RepositoryLinkingClient(
            server_url="http://localhost:8001", credentials=test_credentials
        )

        client2 = RepositoryLinkingClient(
            server_url="http://localhost:8001", credentials=test_credentials
        )

        try:
            # This assertion will FAIL initially because _credentials doesn't exist
            assert hasattr(
                client1, "_credentials"
            ), "Client should have _credentials attribute"
            assert hasattr(
                client2, "_credentials"
            ), "Client should have _credentials attribute"

            # This will also fail due to missing attribute
            assert (
                client1._credentials == client2._credentials
            ), "Both clients should have same credentials"

        except AttributeError as e:
            pytest.fail(f"Clients should have accessible credentials attribute: {e}")

    @pytest.mark.asyncio
    async def test_connection_error_during_auth_should_be_properly_classified(self):
        """FAILING TEST: Connection errors during authentication should be classified correctly.

        This reproduces the specific issue where NetworkError during authentication
        gets wrapped as RepositoryNotFoundError instead of maintaining authentication context.
        """
        client = RepositoryLinkingClient(
            server_url="http://localhost:8001",
            credentials={"username": "test_user", "password": "invalid_password"},
        )

        try:
            # This operation requires authentication, but server is unavailable
            await client.discover_repositories("https://github.com/example/test.git")
            pytest.fail("Expected network/authentication error")
        except RepositoryNotFoundError as e:
            # Current behavior: gets wrapped as RepositoryNotFoundError
            # Expected behavior: should maintain authentication context
            error_msg = str(e).lower()

            # This will FAIL - current implementation doesn't maintain auth context
            assert (
                "authentication" in error_msg or "connection" in error_msg
            ), f"Error should indicate authentication or connection issue, got: {error_msg}"
        except NetworkError:
            # This would be acceptable - network error is properly classified
            pass
        finally:
            await client.close()

    def test_multiple_clients_should_have_independent_but_accessible_credentials(self):
        """FAILING TEST: Multiple clients should have independently accessible credentials.

        This reproduces the issue where resource isolation tests need to verify
        that multiple clients have proper credential handling.
        """
        credentials1 = {"username": "user1", "password": "pass1"}
        credentials2 = {"username": "user2", "password": "pass2"}

        client1 = RepositoryLinkingClient(
            server_url="http://localhost:8001", credentials=credentials1
        )

        client2 = RepositoryLinkingClient(
            server_url="http://localhost:8001", credentials=credentials2
        )

        try:
            # These assertions will FAIL due to missing _credentials attribute
            assert hasattr(
                client1, "_credentials"
            ), "Client1 should have accessible credentials"
            assert hasattr(
                client2, "_credentials"
            ), "Client2 should have accessible credentials"

            # This should show they have different credentials
            assert (
                client1._credentials != client2._credentials
            ), "Clients should have different credentials"
            assert (
                client1._credentials == credentials1
            ), "Client1 should have its specific credentials"
            assert (
                client2._credentials == credentials2
            ), "Client2 should have its specific credentials"

        except AttributeError as e:
            pytest.fail(
                f"Clients should expose credentials for resource isolation testing: {e}"
            )
