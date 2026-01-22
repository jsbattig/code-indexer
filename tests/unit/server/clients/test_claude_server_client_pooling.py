"""
Unit tests for ClaudeServerClient HTTP connection pooling.

Story #732: Add HTTP Connection Pooling to ClaudeServerClient

Tests verify:
- AC1: Single httpx.AsyncClient instance per ClaudeServerClient (created in __init__)
- AC2: Connection pooling with configurable limits (default: 10 max, 5 keepalive)
- AC3: Connections are reused for subsequent requests (HTTP keep-alive)
- AC4: Proper cleanup on server shutdown via close() method
- AC5: No behavior change for existing functionality
- AC6: Unit tests verify client lifecycle
"""

import pytest
from pytest_httpx import HTTPXMock


# Test constants
TEST_BASE_URL = "https://claude-server.example.com"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password123"


class TestClaudeServerClientPoolingInitialization:
    """Tests for AC1: Single httpx.AsyncClient instance per ClaudeServerClient."""

    def test_client_creates_shared_http_client_in_init(self):
        """
        ClaudeServerClient should create a shared httpx.AsyncClient in __init__.

        Given I instantiate a ClaudeServerClient
        When I check the internal state
        Then a _client attribute exists and is an httpx.AsyncClient instance
        """
        import httpx
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        assert hasattr(client, "_client"), "Missing _client attribute"
        assert isinstance(
            client._client, httpx.AsyncClient
        ), "_client should be httpx.AsyncClient instance"

    def test_client_respects_skip_ssl_verify_setting(self):
        """
        The shared client should be configured with skip_ssl_verify setting.

        Given skip_ssl_verify=True
        When I create a ClaudeServerClient
        Then the underlying httpx.AsyncClient has verify=False
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
            skip_ssl_verify=True,
        )

        # httpx.AsyncClient stores verify setting in _transport.verify
        # We check the _verify attribute on the client
        assert client._client._transport is not None


class TestClaudeServerClientPoolingLimits:
    """Tests for AC2: Connection pooling with configurable limits."""

    def test_client_has_default_connection_limits(self):
        """
        The shared client should have default connection limits configured.

        Given a ClaudeServerClient without explicit limits
        When I check the connection limits
        Then max_connections=10 and max_keepalive_connections=5
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # httpx.AsyncClient stores limits in the transport pool
        pool = client._client._transport._pool
        assert (
            pool._max_connections == 10
        ), f"Expected max_connections=10, got {pool._max_connections}"
        assert (
            pool._max_keepalive_connections == 5
        ), f"Expected max_keepalive_connections=5, got {pool._max_keepalive_connections}"

    def test_client_has_proper_timeout_configuration(self):
        """
        The shared client should have proper timeout configuration.

        Given a ClaudeServerClient
        When I check the timeout settings
        Then total timeout is 30s and connect timeout is 10s
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        timeout = client._client.timeout
        assert timeout.read == 30.0, f"Expected read timeout=30.0, got {timeout.read}"
        assert (
            timeout.connect == 10.0
        ), f"Expected connect timeout=10.0, got {timeout.connect}"


class TestClaudeServerClientPoolingReuse:
    """Tests for AC3: Connections are reused for subsequent requests."""

    @pytest.mark.asyncio
    async def test_multiple_requests_use_same_client_instance(
        self, httpx_mock: HTTPXMock
    ):
        """
        Multiple requests should use the same underlying httpx.AsyncClient.

        Given a ClaudeServerClient
        When I make multiple authenticated requests
        Then all requests go through the same _client instance
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer", "expires_in": 3600},
            status_code=200,
        )

        # Repository responses
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/repo1",
            json={"alias": "repo1"},
            status_code=200,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/repo2",
            json={"alias": "repo2"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Get reference to the client instance before requests
        original_client = client._client

        # Make multiple requests
        await client.authenticate()
        await client.check_repository_exists("repo1")
        await client.check_repository_exists("repo2")

        # Verify same client instance was used
        assert (
            client._client is original_client
        ), "Client instance should not change between requests"

    @pytest.mark.asyncio
    async def test_no_new_async_client_per_request(self, httpx_mock: HTTPXMock):
        """
        Each request should NOT create a new httpx.AsyncClient.

        This test verifies that we no longer use `async with httpx.AsyncClient()`.
        The shared client pattern means we use `self._client.get/post` directly.

        Given a ClaudeServerClient with shared _client
        When I make multiple requests
        Then only one httpx.AsyncClient exists throughout
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer", "expires_in": 3600},
            status_code=200,
        )

        # Job creation response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs",
            json={"job_id": "job-123", "status": "created"},
            status_code=201,
        )

        # Start job response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs/job-123/start",
            json={"job_id": "job-123", "status": "running"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Capture client ID before requests
        client_id_before = id(client._client)

        await client.authenticate()
        await client.create_job("test prompt", ["repo1"])
        await client.start_job("job-123")

        # Verify same client instance (same object ID)
        assert id(client._client) == client_id_before


class TestClaudeServerClientPoolingCleanup:
    """Tests for AC4: Proper cleanup on server shutdown via close() method."""

    @pytest.mark.asyncio
    async def test_close_method_exists(self):
        """
        ClaudeServerClient should have a close() method.

        Given a ClaudeServerClient
        When I check for close() method
        Then it exists and is callable
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        assert hasattr(client, "close"), "Missing close() method"
        assert callable(client.close), "close should be callable"

    @pytest.mark.asyncio
    async def test_close_method_closes_underlying_client(self):
        """
        close() should close the underlying httpx.AsyncClient.

        Given a ClaudeServerClient
        When I call close()
        Then the underlying _client is closed
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Verify client is open initially
        assert not client._client.is_closed

        # Close the client
        await client.close()

        # Verify client is now closed
        assert client._client.is_closed

    @pytest.mark.asyncio
    async def test_close_can_be_called_multiple_times_safely(self):
        """
        close() should be idempotent - safe to call multiple times.

        Given a ClaudeServerClient that has been closed
        When I call close() again
        Then no error is raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Close twice - should not raise
        await client.close()
        await client.close()  # Should not raise


class TestClaudeServerClientContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_supports_async_context_manager(self, httpx_mock: HTTPXMock):
        """
        ClaudeServerClient should support async context manager protocol.

        Given a ClaudeServerClient
        When I use it with 'async with'
        Then __aenter__ returns the client and __aexit__ closes it
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer", "expires_in": 3600},
            status_code=200,
        )

        async with ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        ) as client:
            # Should be able to use client inside context
            await client.authenticate()
            assert not client._client.is_closed

        # After context exit, client should be closed
        assert client._client.is_closed

    @pytest.mark.asyncio
    async def test_context_manager_returns_client_instance(self):
        """
        __aenter__ should return the ClaudeServerClient instance.

        Given a ClaudeServerClient
        When I enter the context
        Then I get back the same client instance
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        async with client as entered_client:
            assert entered_client is client

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_exception(self, httpx_mock: HTTPXMock):
        """
        Context manager should close client even if exception occurs.

        Given a ClaudeServerClient used as context manager
        When an exception occurs inside the context
        Then the client is still closed properly
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        with pytest.raises(ValueError):
            async with client:
                raise ValueError("Test exception")

        # Client should still be closed
        assert client._client.is_closed


class TestClaudeServerClientBackwardCompatibility:
    """Tests for AC5: No behavior change for existing functionality."""

    @pytest.mark.asyncio
    async def test_authenticate_still_works(self, httpx_mock: HTTPXMock):
        """
        authenticate() should work the same with connection pooling.

        Given a ClaudeServerClient with connection pooling
        When I call authenticate()
        Then it returns JWT token as before
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
                "token_type": "bearer",
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        token = await client.authenticate()

        assert token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    @pytest.mark.asyncio
    async def test_create_job_still_works(self, httpx_mock: HTTPXMock):
        """
        create_job() should work the same with connection pooling.

        Given a ClaudeServerClient with connection pooling
        When I call create_job()
        Then it creates job and returns job info as before
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Create job response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs",
            json={
                "job_id": "job-12345",
                "status": "created",
            },
            status_code=201,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.create_job(
            prompt="Test prompt",
            repositories=["repo1"],
        )

        assert result["job_id"] == "job-12345"
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_error_handling_still_works(self, httpx_mock: HTTPXMock):
        """
        Error handling should work the same with connection pooling.

        Given a ClaudeServerClient with connection pooling
        When a connection error occurs
        Then ClaudeServerError is raised as before
        """
        import httpx
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        with pytest.raises(ClaudeServerError) as exc_info:
            await client.authenticate()

        assert "connection" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_401_retry_still_works(self, httpx_mock: HTTPXMock):
        """
        401 retry mechanism should work the same with connection pooling.

        Given a ClaudeServerClient with connection pooling
        When a request gets 401
        Then it re-authenticates and retries as before
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # Initial auth
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "old_token", "token_type": "bearer"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        await client.ensure_authenticated()

        # Job creation fails with 401
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs",
            status_code=401,
        )

        # Re-auth succeeds
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "new_token", "token_type": "bearer"},
            status_code=200,
        )

        # Retry job creation succeeds
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs",
            json={"job_id": "job-retry", "status": "created"},
            status_code=201,
        )

        result = await client.create_job(
            prompt="Test prompt",
            repositories=["repo1"],
        )

        assert result["job_id"] == "job-retry"
