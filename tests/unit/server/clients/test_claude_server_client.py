"""
Unit tests for ClaudeServerClient.

Story #719: Execute Delegation Function with Async Job

Tests follow TDD methodology - tests written FIRST before implementation.
Uses httpx_mock for HTTP mocking per project conventions (not mocks of objects).
"""

from datetime import datetime, timezone, timedelta

import pytest
from pytest_httpx import HTTPXMock

# Test constants
TEST_BASE_URL = "https://claude-server.example.com"
TEST_USERNAME = "test_user"
TEST_PASSWORD = "test_password123"


class TestClaudeServerClientAuthentication:
    """Tests for authentication methods."""

    @pytest.mark.asyncio
    async def test_authenticate_returns_jwt_token(self, httpx_mock: HTTPXMock):
        """
        authenticate() should return JWT token on successful auth.

        Given valid credentials
        When I call authenticate()
        Then I receive a JWT access token
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
    async def test_authenticate_raises_on_invalid_credentials(
        self, httpx_mock: HTTPXMock
    ):
        """
        authenticate() should raise on authentication failure.

        Given invalid credentials
        When I call authenticate()
        Then ClaudeServerAuthError is raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerAuthError,
        )

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"detail": "Invalid credentials"},
            status_code=401,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password="wrong_password",
        )

        with pytest.raises(ClaudeServerAuthError):
            await client.authenticate()

    @pytest.mark.asyncio
    async def test_ensure_authenticated_returns_cached_token(
        self, httpx_mock: HTTPXMock
    ):
        """
        ensure_authenticated() should return cached token if not expired.

        Given a previously authenticated session with valid token
        When I call ensure_authenticated()
        Then the cached token is returned (no new HTTP request)
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={
                "access_token": "cached_token_123",
                "token_type": "bearer",
                "expires_in": 3600,
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # First call should authenticate
        token1 = await client.ensure_authenticated()
        # Second call should return cached token
        token2 = await client.ensure_authenticated()

        assert token1 == token2 == "cached_token_123"
        # Should only have made one request
        assert len(httpx_mock.get_requests()) == 1

    @pytest.mark.asyncio
    async def test_ensure_authenticated_refreshes_expired_token(
        self, httpx_mock: HTTPXMock
    ):
        """
        ensure_authenticated() should refresh token when expired.

        Given an expired cached token
        When I call ensure_authenticated()
        Then a new authentication request is made
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        # First auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={
                "access_token": "first_token",
                "token_type": "bearer",
                "expires_in": 0,  # Immediately expired
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # First call
        await client.ensure_authenticated()

        # Add second auth response for refresh
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={
                "access_token": "refreshed_token",
                "token_type": "bearer",
                "expires_in": 3600,
            },
            status_code=200,
        )

        # Force token expiration
        client._jwt_expires = datetime.now(timezone.utc) - timedelta(minutes=1)

        # Second call should re-authenticate
        token = await client.ensure_authenticated()

        assert token == "refreshed_token"
        assert len(httpx_mock.get_requests()) == 2


class TestClaudeServerClientRepositoryOperations:
    """Tests for repository-related operations."""

    @pytest.mark.asyncio
    async def test_check_repository_exists_returns_true(self, httpx_mock: HTTPXMock):
        """
        check_repository_exists() should return True for existing repo.

        Given a registered repository alias
        When I call check_repository_exists(alias)
        Then True is returned
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

        # Repository check response
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/main-app",
            json={"alias": "main-app", "remote": "https://github.com/org/main-app"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        exists = await client.check_repository_exists("main-app")

        assert exists is True

    @pytest.mark.asyncio
    async def test_check_repository_exists_returns_false(self, httpx_mock: HTTPXMock):
        """
        check_repository_exists() should return False for non-existent repo.

        Given a non-existent repository alias
        When I call check_repository_exists(alias)
        Then False is returned
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

        # Repository not found
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/unknown-repo",
            json={"detail": "Repository not found"},
            status_code=404,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        exists = await client.check_repository_exists("unknown-repo")

        assert exists is False

    @pytest.mark.asyncio
    async def test_register_repository_success(self, httpx_mock: HTTPXMock):
        """
        register_repository() should register and return repository info.

        Given valid repository details
        When I call register_repository(alias, remote, branch)
        Then repository is registered and details returned
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

        # Register repository response (Claude Server uses name/gitUrl fields)
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/repositories/register",
            json={
                "name": "new-repo",
                "gitUrl": "https://github.com/org/new-repo",
                "branch": "main",
                "cloneStatus": "cloning",
            },
            status_code=201,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.register_repository(
            alias="new-repo",
            remote="https://github.com/org/new-repo",
            branch="main",
        )

        assert result["name"] == "new-repo"
        assert result["cloneStatus"] == "cloning"


class TestClaudeServerClientJobOperations:
    """Tests for job creation and management."""

    @pytest.mark.asyncio
    async def test_create_job_returns_job_info(self, httpx_mock: HTTPXMock):
        """
        create_job() should create and return job info.

        Given a valid prompt and repositories
        When I call create_job(prompt, repositories)
        Then job is created and job_id returned
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
                "created_at": "2025-01-13T10:00:00Z",
            },
            status_code=201,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.create_job(
            prompt="Search for authentication bugs",
            repositories=["main-app", "auth-service"],
        )

        assert result["job_id"] == "job-12345"
        assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_start_job_returns_updated_status(self, httpx_mock: HTTPXMock):
        """
        start_job() should start job and return updated status.

        Given a created job
        When I call start_job(job_id)
        Then job is started and status is 'running'
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

        # Start job response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs/job-12345/start",
            json={
                "job_id": "job-12345",
                "status": "running",
                "started_at": "2025-01-13T10:01:00Z",
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.start_job("job-12345")

        assert result["job_id"] == "job-12345"
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_create_job_handles_401_with_retry(self, httpx_mock: HTTPXMock):
        """
        create_job() should handle 401 by refreshing token and retrying.

        Given an expired token
        When create_job() receives 401
        Then it re-authenticates and retries the request
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

        # First authenticate
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
            repositories=["test-repo"],
        )

        assert result["job_id"] == "job-retry"


class TestClaudeServerClientErrors:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_create_job_raises_on_server_error(self, httpx_mock: HTTPXMock):
        """
        create_job() should raise ClaudeServerError on 500.

        Given a server error
        When I call create_job()
        Then ClaudeServerError is raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Server error
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs",
            json={"detail": "Internal server error"},
            status_code=500,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        with pytest.raises(ClaudeServerError):
            await client.create_job(
                prompt="Test",
                repositories=["repo"],
            )

    @pytest.mark.asyncio
    async def test_connection_error_raises_claude_server_error(
        self, httpx_mock: HTTPXMock
    ):
        """
        Connection errors should raise ClaudeServerError.

        Given a network connectivity issue
        When I call any method
        Then ClaudeServerError is raised with connection info
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
    async def test_connection_error_does_not_expose_password(
        self, httpx_mock: HTTPXMock
    ):
        """
        Connection error exception should NOT contain password.

        Given a connection error during authentication
        When the error is raised
        Then the exception message must NOT contain the password
        """
        import httpx

        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        sensitive_password = "super_secret_password_123"
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=sensitive_password,
        )

        with pytest.raises(ClaudeServerError) as exc_info:
            await client.authenticate()

        # Password MUST NOT appear in exception message
        assert sensitive_password not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error_does_not_expose_password(self, httpx_mock: HTTPXMock):
        """
        Timeout error exception should NOT contain password.

        Given a timeout error during authentication
        When the error is raised
        Then the exception message must NOT contain the password
        """
        import httpx

        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        sensitive_password = "another_secret_password_456"
        httpx_mock.add_exception(httpx.TimeoutException("Request timed out"))

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=sensitive_password,
        )

        with pytest.raises(ClaudeServerError) as exc_info:
            await client.authenticate()

        # Password MUST NOT appear in exception message
        assert sensitive_password not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticated_request_connection_error_does_not_expose_data(
        self, httpx_mock: HTTPXMock
    ):
        """
        Connection error during authenticated request should not expose credentials.

        Given a connection error during an authenticated request
        When the error is raised
        Then the exception message must NOT contain password or token
        """
        import httpx

        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        sensitive_password = "request_secret_789"
        jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.sensitive"

        # Auth succeeds
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": jwt_token, "token_type": "bearer"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=sensitive_password,
        )

        # Authenticate first
        await client.ensure_authenticated()

        # Then connection error on subsequent request
        httpx_mock.add_exception(httpx.ConnectError("Connection lost"))

        with pytest.raises(ClaudeServerError) as exc_info:
            await client.check_repository_exists("test-repo")

        # Neither password nor token should appear in exception
        assert sensitive_password not in str(exc_info.value)
        assert jwt_token not in str(exc_info.value)


class TestClaudeServerClientRepr:
    """Tests for __repr__ preventing credential exposure."""

    def test_repr_does_not_expose_password(self):
        """
        __repr__ should NOT include password in string representation.

        Given a ClaudeServerClient with credentials
        When I call repr() or str() on it
        Then the password must NOT be visible
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        sensitive_password = "my_secret_password"
        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=sensitive_password,
        )

        repr_output = repr(client)

        # Password MUST NOT appear in repr
        assert sensitive_password not in repr_output
        # But base_url and username can appear (non-sensitive)
        assert TEST_BASE_URL in repr_output
        assert TEST_USERNAME in repr_output

    def test_repr_does_not_expose_jwt_token(self):
        """
        __repr__ should NOT include JWT token in string representation.

        Given a ClaudeServerClient with cached JWT token
        When I call repr() on it
        Then the token must NOT be visible
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Simulate cached token
        client._jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secret"

        repr_output = repr(client)

        # JWT token MUST NOT appear in repr
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in repr_output


class TestClaudeServerClientSecondAuth401:
    """Tests for authentication failure on second 401."""

    @pytest.mark.asyncio
    async def test_second_401_raises_auth_error(self, httpx_mock: HTTPXMock):
        """
        Second 401 should raise ClaudeServerAuthError instead of returning response.

        Given a request that gets 401, re-auth, and 401 again
        When _make_authenticated_request is called
        Then ClaudeServerAuthError must be raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerAuthError,
        )

        # Initial auth
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "first_token", "token_type": "bearer"},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # First authenticate
        await client.ensure_authenticated()

        # Request returns 401
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/test-repo",
            status_code=401,
        )

        # Re-auth succeeds
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "second_token", "token_type": "bearer"},
            status_code=200,
        )

        # Second attempt also returns 401
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/repositories/test-repo",
            status_code=401,
        )

        # Should raise ClaudeServerAuthError on second 401
        with pytest.raises(ClaudeServerAuthError) as exc_info:
            await client.check_repository_exists("test-repo")

        assert "authentication failed" in str(exc_info.value).lower()


class TestClaudeServerClientJobPolling:
    """Tests for job polling methods (Story #720)."""

    @pytest.mark.asyncio
    async def test_get_job_status_returns_in_progress(self, httpx_mock: HTTPXMock):
        """
        get_job_status() should return job status for in-progress job.

        Given a job that is in progress
        When I call get_job_status(job_id)
        Then the current status is returned
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

        # Job status response
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/jobs/job-12345",
            json={
                "job_id": "job-12345",
                "status": "in_progress",
                "repositories": [
                    {
                        "alias": "repo1",
                        "registered": True,
                        "cloned": True,
                        "indexed": True,
                    }
                ],
                "exchange_count": 5,
                "tool_use_count": 12,
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.get_job_status("job-12345")

        assert result["job_id"] == "job-12345"
        assert result["status"] == "in_progress"
        assert result["exchange_count"] == 5

    @pytest.mark.asyncio
    async def test_get_job_status_returns_completed(self, httpx_mock: HTTPXMock):
        """
        get_job_status() should return completed status with result.

        Given a completed job
        When I call get_job_status(job_id)
        Then status is 'completed' and result is included
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

        # Job status response
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/jobs/job-12345",
            json={
                "job_id": "job-12345",
                "status": "completed",
                "result": "The authentication uses JWT tokens...",
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.get_job_status("job-12345")

        assert result["status"] == "completed"
        assert "JWT tokens" in result["result"]

    @pytest.mark.asyncio
    async def test_get_job_status_raises_not_found_error_on_404(
        self, httpx_mock: HTTPXMock
    ):
        """
        get_job_status() should raise ClaudeServerNotFoundError for non-existent job.

        Given a non-existent job ID
        When I call get_job_status(job_id)
        Then ClaudeServerNotFoundError is raised (specific subclass)
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
            ClaudeServerNotFoundError,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Job not found
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/jobs/nonexistent-job",
            json={"detail": "Job not found"},
            status_code=404,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Should raise specific ClaudeServerNotFoundError
        with pytest.raises(ClaudeServerNotFoundError) as exc_info:
            await client.get_job_status("nonexistent-job")

        assert "not found" in str(exc_info.value).lower()
        # Also verify it's a subclass of ClaudeServerError for catch-all handling
        assert isinstance(exc_info.value, ClaudeServerError)

    @pytest.mark.asyncio
    async def test_get_job_conversation_returns_result(self, httpx_mock: HTTPXMock):
        """
        get_job_conversation() should return job conversation/result.

        Given a completed job
        When I call get_job_conversation(job_id)
        Then the conversation result is returned
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

        # Job conversation response
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/jobs/job-12345/conversation",
            json={
                "job_id": "job-12345",
                "result": "The authentication system uses JWT tokens for session management...",
                "exchanges": [
                    {"role": "user", "content": "How does auth work?"},
                    {"role": "assistant", "content": "The auth uses JWT..."},
                ],
            },
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        result = await client.get_job_conversation("job-12345")

        assert result["job_id"] == "job-12345"
        assert "JWT tokens" in result["result"]

    @pytest.mark.asyncio
    async def test_get_job_conversation_raises_not_found_error_on_404(
        self, httpx_mock: HTTPXMock
    ):
        """
        get_job_conversation() should raise ClaudeServerNotFoundError for non-existent job.

        Given a non-existent job ID
        When I call get_job_conversation(job_id)
        Then ClaudeServerNotFoundError is raised (specific subclass)
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
            ClaudeServerNotFoundError,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Job not found
        httpx_mock.add_response(
            method="GET",
            url=f"{TEST_BASE_URL}/jobs/nonexistent-job/conversation",
            json={"detail": "Job not found"},
            status_code=404,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Should raise specific ClaudeServerNotFoundError
        with pytest.raises(ClaudeServerNotFoundError) as exc_info:
            await client.get_job_conversation("nonexistent-job")

        assert "not found" in str(exc_info.value).lower()
        # Also verify it's a subclass of ClaudeServerError for catch-all handling
        assert isinstance(exc_info.value, ClaudeServerError)


class TestClaudeServerClientCallbackRegistration:
    """Tests for callback registration (Story #720)."""

    @pytest.mark.asyncio
    async def test_register_callback_success(self, httpx_mock: HTTPXMock):
        """
        register_callback() should register callback URL with Claude Server.

        Given a valid job_id and callback_url
        When I call register_callback(job_id, callback_url)
        Then the callback URL is registered with Claude Server
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

        # Register callback response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs/job-12345/callbacks",
            json={"registered": True},
            status_code=200,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        # Should not raise
        await client.register_callback(
            job_id="job-12345",
            callback_url="https://cidx.example.com/api/delegation/callback/job-12345",
        )

        # Verify the request was made with correct URL in JSON body
        requests = httpx_mock.get_requests()
        callback_request = requests[-1]
        assert callback_request.url.path == "/jobs/job-12345/callbacks"
        import json

        body = json.loads(callback_request.content)
        assert (
            body["url"] == "https://cidx.example.com/api/delegation/callback/job-12345"
        )

    @pytest.mark.asyncio
    async def test_register_callback_raises_on_error(self, httpx_mock: HTTPXMock):
        """
        register_callback() should raise on server error.

        Given a server error response
        When I call register_callback()
        Then ClaudeServerError is raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerError,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Server error
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs/job-12345/callbacks",
            json={"detail": "Internal server error"},
            status_code=500,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        with pytest.raises(ClaudeServerError):
            await client.register_callback(
                job_id="job-12345",
                callback_url="https://cidx.example.com/api/delegation/callback/job-12345",
            )

    @pytest.mark.asyncio
    async def test_register_callback_raises_not_found_for_unknown_job(
        self, httpx_mock: HTTPXMock
    ):
        """
        register_callback() should raise ClaudeServerNotFoundError for unknown job.

        Given a non-existent job_id
        When I call register_callback()
        Then ClaudeServerNotFoundError is raised
        """
        from code_indexer.server.clients.claude_server_client import (
            ClaudeServerClient,
            ClaudeServerNotFoundError,
        )

        # Auth response
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
            status_code=200,
        )

        # Job not found
        httpx_mock.add_response(
            method="POST",
            url=f"{TEST_BASE_URL}/jobs/nonexistent-job/callbacks",
            json={"detail": "Job not found"},
            status_code=404,
        )

        client = ClaudeServerClient(
            base_url=TEST_BASE_URL,
            username=TEST_USERNAME,
            password=TEST_PASSWORD,
        )

        with pytest.raises(ClaudeServerNotFoundError):
            await client.register_callback(
                job_id="nonexistent-job",
                callback_url="https://cidx.example.com/api/delegation/callback/nonexistent-job",
            )
