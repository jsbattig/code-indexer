"""Real Test Suite for Base CIDX Remote API Client.

Foundation #1 Compliance: Zero mocks implementation using real infrastructure.
All operations use real HTTP servers, real JWT tokens, and real authentication flows.
"""

import asyncio
import pytest
import pytest_asyncio
from pathlib import Path
import tempfile

from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
)
from code_indexer.api_clients.network_error_handler import (
    NetworkConnectionError,
    NetworkTimeoutError,
    DNSResolutionError,
)
from code_indexer.api_clients.jwt_token_manager import JWTTokenManager

# Import real infrastructure (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext
from tests.infrastructure.real_jwt_manager import create_real_jwt_manager


class TestCIDXRemoteAPIClientRealAuthentication:
    """Test JWT authentication and token management with real server infrastructure."""

    @pytest_asyncio.fixture
    async def real_server(self):
        """Real CIDX server for testing."""
        async with CIDXServerTestContext() as server:
            # Add test repositories
            server.add_test_repository(
                repo_id="test-repo-1",
                name="Test Repository",
                path="/test/repo",
                branches=["main", "develop", "feature/test"],
                default_branch="main",
            )
            yield server

    @pytest.fixture
    def real_credentials(self):
        """Real credentials for test server."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest_asyncio.fixture
    async def real_api_client(self, real_server, real_credentials):
        """Real API client connected to real server."""
        client = CIDXRemoteAPIClient(
            server_url=real_server.base_url, credentials=real_credentials
        )
        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_real_authentication_success(self, real_api_client):
        """Test successful authentication with real server and JWT tokens."""
        # Get valid token through proper token management flow
        token = await real_api_client._get_valid_token()

        # Verify we got a real JWT token
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are substantial length
        assert "." in token  # JWT tokens have dots separating sections

        # Verify token is stored in current token
        assert real_api_client._current_token == token

        # Verify token can be used for authenticated requests
        response = await real_api_client._authenticated_request("GET", "/health")
        assert response.status_code == 200
        health_data = response.json()
        assert health_data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_real_authentication_invalid_credentials(self, real_server):
        """Test authentication failure with real invalid credentials."""
        invalid_credentials = {
            "username": "wronguser",
            "password": "wrongpass",
            "server_url": real_server.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server.base_url, credentials=invalid_credentials
        )

        try:
            # Should raise real authentication error from server
            with pytest.raises(AuthenticationError) as exc_info:
                await client._authenticate()

            assert "Invalid credentials" in str(exc_info.value)
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_token_refresh_workflow(self, real_api_client, real_server):
        """Test real token refresh using actual server communication."""
        # Get initial token
        initial_token = await real_api_client._authenticate()
        assert initial_token is not None

        # Wait a moment to ensure timestamp difference
        await asyncio.sleep(0.1)

        # Create real JWT manager to simulate near-expiry
        jwt_manager = create_real_jwt_manager()
        near_expiry_token = jwt_manager.create_near_expiry_token(
            "testuser", expiry_seconds=5
        )

        # Set the near-expiry token
        real_api_client._current_token = near_expiry_token

        # Force token refresh by making request with near-expiry token
        # This should trigger re-authentication
        response = await real_api_client._authenticated_request("GET", "/health")
        assert response.status_code == 200

        # Verify we got a new token (different from the near-expiry one)
        new_token = real_api_client._current_token
        assert new_token != near_expiry_token
        assert new_token is not None

    @pytest.mark.asyncio
    async def test_concurrent_authentication_real_server(self, real_api_client):
        """Test concurrent authentication requests don't cause race conditions."""
        # Clear any existing token
        real_api_client._current_token = None

        # Make multiple concurrent token requests
        tasks = [real_api_client._get_valid_token() for _ in range(5)]
        tokens = await asyncio.gather(*tasks)

        # Should all return the same token (only one auth request made)
        assert len(set(tokens)) == 1  # All tokens should be identical
        assert all(token == tokens[0] for token in tokens)

        # Verify token is valid by making authenticated request
        response = await real_api_client._authenticated_request("GET", "/health")
        assert response.status_code == 200


class TestCIDXRemoteAPIClientRealRequests:
    """Test authenticated HTTP requests with real server infrastructure."""

    @pytest_asyncio.fixture
    async def real_server_with_data(self):
        """Real server with test data."""
        async with CIDXServerTestContext() as server:
            # Add test repositories
            server.add_test_repository(
                repo_id="repo-123",
                name="Test Repo",
                path="/test/path",
                branches=["main", "develop"],
                default_branch="main",
            )

            # Add test jobs
            server.add_test_job("job-456", "repo-123", "running", 50)
            server.add_test_job("job-789", "repo-123", "completed", 100)

            yield server

    @pytest_asyncio.fixture
    async def authenticated_api_client(self, real_server_with_data):
        """Pre-authenticated API client."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_with_data.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_with_data.base_url, credentials=credentials
        )

        # Pre-authenticate
        await client._authenticate()

        yield client
        await client.close()

    @pytest.mark.asyncio
    async def test_real_authenticated_get_request(self, authenticated_api_client):
        """Test real authenticated GET request."""
        response = await authenticated_api_client._authenticated_request(
            "GET", "/api/repositories"
        )

        assert response.status_code == 200
        data = response.json()
        assert "repositories" in data
        assert data["total"] >= 1

        # Verify we got real repository data
        repo = data["repositories"][0]
        assert repo["id"] == "repo-123"
        assert repo["name"] == "Test Repo"

    @pytest.mark.asyncio
    async def test_real_job_status_request(self, authenticated_api_client):
        """Test real job status retrieval."""
        # Test existing job
        job_data = await authenticated_api_client.get_job_status("job-456")

        assert job_data["id"] == "job-456"
        assert job_data["repository_id"] == "repo-123"
        assert job_data["status"] == "running"
        assert job_data["progress"] == 50

    @pytest.mark.asyncio
    async def test_real_job_not_found_error(self, authenticated_api_client):
        """Test real 404 error handling."""
        with pytest.raises(APIClientError) as exc_info:
            await authenticated_api_client.get_job_status("nonexistent-job")

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_real_job_cancellation(
        self, authenticated_api_client, real_server_with_data
    ):
        """Test real job cancellation workflow."""
        # Cancel running job
        result = await authenticated_api_client.cancel_job(
            "job-456", "Test cancellation"
        )

        assert "cancelled successfully" in result["message"]
        assert result["reason"] == "Test cancellation"

        # Verify job status was updated on server
        updated_job = await authenticated_api_client.get_job_status("job-456")
        assert updated_job["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_real_unauthorized_retry_workflow(self, real_server_with_data):
        """Test real 401 handling and token retry."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_with_data.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_with_data.base_url, credentials=credentials
        )

        try:
            # Set an invalid token to trigger 401
            client._current_token = "invalid.jwt.token"

            # This should trigger re-authentication and succeed
            response = await client._authenticated_request("GET", "/health")
            assert response.status_code == 200

            # Verify we got a new valid token
            assert client._current_token != "invalid.jwt.token"
            assert client._current_token is not None

        finally:
            await client.close()


class TestCIDXRemoteAPIClientRealNetworkErrors:
    """Test real network error handling and recovery."""

    @pytest_asyncio.fixture
    async def real_server_with_errors(self):
        """Real server configured for error simulation."""
        async with CIDXServerTestContext() as server:
            yield server

    @pytest.mark.asyncio
    async def test_real_connection_error_handling(self):
        """Test handling of real connection errors."""
        # Use invalid server URL to trigger real connection error
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "http://nonexistent-server:9999",
        }

        client = CIDXRemoteAPIClient(
            server_url="http://nonexistent-server:9999", credentials=credentials
        )

        try:
            with pytest.raises(
                (NetworkConnectionError, DNSResolutionError, AuthenticationError)
            ) as exc_info:
                await client._authenticate()

            # Should get a real network error
            assert (
                "connection" in str(exc_info.value).lower()
                or "network" in str(exc_info.value).lower()
                or "resolve" in str(exc_info.value).lower()
                or "dns" in str(exc_info.value).lower()
            )

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_timeout_handling(self, real_server_with_errors):
        """Test real timeout error handling."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_with_errors.base_url,
        }

        # Create client with very short timeout
        client = CIDXRemoteAPIClient(
            server_url=real_server_with_errors.base_url, credentials=credentials
        )

        # Configure extremely short timeout to trigger timeout
        import httpx

        client.session.timeout = httpx.Timeout(0.001)  # 1ms timeout

        try:
            with pytest.raises((NetworkTimeoutError, AuthenticationError)) as exc_info:
                await client._authenticate()

            # Should get a real timeout error
            assert (
                "timeout" in str(exc_info.value).lower()
                or "timed out" in str(exc_info.value).lower()
            )

        finally:
            await client.close()


class TestCIDXRemoteAPIClientRealResourceManagement:
    """Test real resource management and cleanup."""

    @pytest_asyncio.fixture
    async def real_server_for_resources(self):
        """Real server for resource testing."""
        async with CIDXServerTestContext() as server:
            yield server

    @pytest.mark.asyncio
    async def test_real_session_cleanup(self, real_server_for_resources):
        """Test proper HTTP session cleanup."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_for_resources.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_for_resources.base_url, credentials=credentials
        )

        # Use the client to create a session
        await client._authenticate()
        session = client.session
        assert not session.is_closed

        # Close and verify cleanup
        await client.close()
        assert session.is_closed

    @pytest.mark.asyncio
    async def test_real_context_manager_cleanup(self, real_server_for_resources):
        """Test resource cleanup using context manager."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_for_resources.base_url,
        }

        session_ref = None

        async with CIDXRemoteAPIClient(
            server_url=real_server_for_resources.base_url, credentials=credentials
        ) as client:
            await client._authenticate()
            session_ref = client.session
            assert not session_ref.is_closed

        # Session should be closed after context exit
        assert session_ref.is_closed

    @pytest.mark.asyncio
    async def test_real_session_recreation(self, real_server_for_resources):
        """Test session recreation after close."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_for_resources.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_for_resources.base_url, credentials=credentials
        )

        try:
            # Get initial session
            original_session = client.session
            assert not original_session.is_closed

            # Close client
            await client.close()
            assert original_session.is_closed

            # Access session again should create new one
            new_session = client.session
            assert new_session is not original_session
            assert not new_session.is_closed

        finally:
            await client.close()


class TestRealJWTTokenManagerIntegration:
    """Test JWT manager integration with real tokens and validation."""

    @pytest_asyncio.fixture
    async def real_server_jwt(self):
        """Real server for JWT testing."""
        async with CIDXServerTestContext() as server:
            yield server

    @pytest.mark.asyncio
    async def test_real_jwt_manager_initialization(self, real_server_jwt):
        """Test JWT manager initialization with real components."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_jwt.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_jwt.base_url, credentials=credentials
        )

        try:
            assert client.jwt_manager is not None
            assert isinstance(client.jwt_manager, JWTTokenManager)
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_token_validation_workflow(self, real_server_jwt):
        """Test complete token validation using real JWT manager."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_jwt.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_jwt.base_url, credentials=credentials
        )

        try:
            # Get real token from server
            token = await client._authenticate()

            # Test real token validation
            is_expired = client.jwt_manager.is_token_expired(token)
            assert not is_expired  # Fresh token should not be expired

            is_near_expiry = client.jwt_manager.is_token_near_expiry(token)
            # Fresh token may or may not be near expiry depending on server config
            assert isinstance(is_near_expiry, bool)

            # Test token can be used successfully
            response = await client._authenticated_request("GET", "/health")
            assert response.status_code == 200

        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_real_expired_token_detection(self, real_server_jwt):
        """Test detection of real expired tokens."""
        credentials = {
            "username": "testuser",
            "password": "testpass123",
            "server_url": real_server_jwt.base_url,
        }

        client = CIDXRemoteAPIClient(
            server_url=real_server_jwt.base_url, credentials=credentials
        )

        try:
            # Create real JWT manager for creating expired token
            jwt_manager = create_real_jwt_manager()
            expired_token = jwt_manager.create_expired_token("testuser")

            # Set expired token
            client._current_token = expired_token

            # Verify JWT manager detects expiration
            is_expired = client.jwt_manager.is_token_expired(expired_token)
            assert is_expired

            # Making request should trigger re-authentication
            response = await client._authenticated_request("GET", "/health")
            assert response.status_code == 200

            # Should have new token now
            assert client._current_token != expired_token

        finally:
            await client.close()


class TestRealPersistentTokenStorage:
    """Test persistent token storage with real file operations."""

    @pytest.mark.asyncio
    async def test_real_persistent_token_storage(self):
        """Test real persistent token storage and retrieval."""
        with tempfile.TemporaryDirectory() as temp_dir:
            async with CIDXServerTestContext() as server:
                project_root = Path(temp_dir)

                credentials = {
                    "username": "testuser",
                    "password": "testpass123",
                    "server_url": server.base_url,
                }

                # First client - authenticate and store token
                client1 = CIDXRemoteAPIClient(
                    server_url=server.base_url,
                    credentials=credentials,
                    project_root=project_root,
                )

                try:
                    await client1._authenticate()
                    await client1.close()

                    # Second client - should load stored token
                    client2 = CIDXRemoteAPIClient(
                        server_url=server.base_url,
                        credentials=credentials,
                        project_root=project_root,
                    )

                    try:
                        # Should load persistent token without server call
                        await client2._get_valid_token()

                        # Verify we can use the loaded token
                        response = await client2._authenticated_request(
                            "GET", "/health"
                        )
                        assert response.status_code == 200

                    finally:
                        await client2.close()

                finally:
                    if not client1.session.is_closed:
                        await client1.close()


# Integration tests combining real server, real JWT, and real HTTP operations
class TestRealEndToEndIntegration:
    """End-to-end integration tests with zero mocks."""

    @pytest.mark.asyncio
    async def test_complete_real_workflow(self):
        """Test complete workflow using only real implementations."""
        async with CIDXServerTestContext() as server:
            # Add test data to server
            server.add_test_repository(
                "integration-repo", "Integration Test", "/test", ["main"]
            )
            server.add_test_job("integration-job", "integration-repo", "pending", 0)

            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            # Create real client
            async with CIDXRemoteAPIClient(
                server_url=server.base_url, credentials=credentials
            ) as client:
                # 1. Real authentication
                token = await client._authenticate()
                assert token is not None

                # 2. Real repository listing
                repos_response = await client._authenticated_request(
                    "GET", "/api/repositories"
                )
                assert repos_response.status_code == 200
                repos_data = repos_response.json()
                assert len(repos_data["repositories"]) == 1

                # 3. Real job status check
                job_data = await client.get_job_status("integration-job")
                assert job_data["status"] == "pending"

                # 4. Real job cancellation
                cancel_result = await client.cancel_job(
                    "integration-job", "Integration test cleanup"
                )
                assert "cancelled successfully" in cancel_result["message"]

                # 5. Verify real state change
                updated_job = await client.get_job_status("integration-job")
                assert updated_job["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_real_error_recovery_workflow(self):
        """Test error recovery using real network conditions."""
        async with CIDXServerTestContext() as server:
            credentials = {
                "username": "testuser",
                "password": "testpass123",
                "server_url": server.base_url,
            }

            async with CIDXRemoteAPIClient(
                server_url=server.base_url, credentials=credentials
            ) as client:
                # 1. Successful authentication
                await client._authenticate()

                # 2. Break authentication by setting invalid token
                client._current_token = "broken.token.here"

                # 3. Make request that should trigger re-authentication
                response = await client._authenticated_request("GET", "/health")
                assert response.status_code == 200

                # 4. Verify we got a new valid token
                assert client._current_token != "broken.token.here"
                assert client._current_token is not None

                # 5. Verify token works for subsequent requests
                health_response = await client._authenticated_request("GET", "/health")
                assert health_response.status_code == 200
                health_data = health_response.json()
                assert health_data["status"] == "healthy"
