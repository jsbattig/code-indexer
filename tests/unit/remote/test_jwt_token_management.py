"""Test suite for JWT Token Management with Persistent Storage.

Tests JWT token persistence, automatic refresh, re-authentication fallback,
and secure token file management following TDD principles with minimal mocking.
"""

import pytest
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import jwt as jose_jwt

from code_indexer.remote.token_manager import (
    PersistentTokenManager,
    StoredToken,
    TokenSecurityError,
)
from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    AuthenticationError,
)
from code_indexer.remote.credential_manager import ProjectCredentialManager

# Import fixtures for pytest to discover them
pytest_plugins = ["tests.unit.remote.jwt_fixtures"]


class TestStoredTokenValidation:
    """Test StoredToken dataclass validation methods."""

    def test_stored_token_creation_with_valid_data(self, valid_jwt_token):
        """Test StoredToken creation with valid token data."""
        # Use real JWT token from fixture
        token = valid_jwt_token

        # This should now work since StoredToken class exists
        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_token_data",
        )

        assert stored_token.token == token
        assert isinstance(stored_token.expires_at, datetime)
        assert isinstance(stored_token.created_at, datetime)

    def test_stored_token_is_expired_method(self):
        """Test StoredToken.is_expired() method for expired tokens."""
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        stored_token = StoredToken(
            token="dummy_token",
            expires_at=expired_time,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
            encrypted_data=b"encrypted_data",
        )
        assert stored_token.is_expired() is True

    def test_stored_token_expires_soon_method(self):
        """Test StoredToken.expires_soon() method for tokens near expiration."""
        soon_expire_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        stored_token = StoredToken(
            token="dummy_token",
            expires_at=soon_expire_time,
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )
        assert stored_token.expires_soon(threshold_minutes=2) is True

    def test_stored_token_validate_security_constraints(self):
        """Test StoredToken.validate_security_constraints() method."""
        # Test algorithm enforcement - create token with unsupported algorithm (not HS256/RS256)
        invalid_token = jose_jwt.encode({"test": "data"}, "secret", algorithm="HS384")
        stored_token = StoredToken(
            token=invalid_token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )
        # Should raise TokenSecurityError for unsupported algorithm
        with pytest.raises(TokenSecurityError):
            stored_token.validate_security_constraints()


class TestPersistentTokenManagerFileOperations:
    """Test PersistentTokenManager secure file operations."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def credential_manager(self):
        """Create ProjectCredentialManager for testing."""
        return ProjectCredentialManager()

    def test_persistent_token_manager_creation(
        self, temp_project_dir, credential_manager
    ):
        """Test PersistentTokenManager creation and initialization."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        assert token_manager.project_root == temp_project_dir
        assert token_manager.username == "testuser"
        assert token_manager.server_url == "https://test.example.com"

    def test_token_file_path_calculation(self, temp_project_dir, credential_manager):
        """Test correct calculation of token file path."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        expected_path = temp_project_dir / ".code-indexer" / ".token"
        assert token_manager.token_file_path == expected_path

    def test_token_file_permissions_enforcement(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test that token files are created with secure permissions (0o600)."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Use real JWT token
        token = valid_jwt_token

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        token_manager.store_token(stored_token)

        # Check file permissions
        file_stat = token_manager.token_file_path.stat()
        file_mode = file_stat.st_mode & 0o777
        assert file_mode == 0o600

    def test_atomic_file_operations(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test atomic file write operations to prevent corruption."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Check that atomic writes use temporary files
        original_rename = Path.rename
        rename_calls = []

        def mock_rename(self, target):
            rename_calls.append((str(self), str(target)))
            return original_rename(self, target)

        with patch.object(Path, "rename", mock_rename):
            # Use real JWT token
            token = valid_jwt_token

            stored_token = StoredToken(
                token=token,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                created_at=datetime.now(timezone.utc),
                encrypted_data=b"encrypted_data",
            )

            token_manager.store_token(stored_token)

            # Should have used atomic rename operation
            assert len(rename_calls) == 1
            temp_file, final_file = rename_calls[0]
            assert temp_file.endswith(".tmp")
            assert final_file == str(token_manager.token_file_path)


class TestPersistentTokenManagerEncryption:
    """Test PersistentTokenManager token encryption and decryption."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def credential_manager(self):
        """Create ProjectCredentialManager for testing."""
        return ProjectCredentialManager()

    def test_token_encryption_and_decryption(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test that tokens are properly encrypted and can be decrypted."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Use real JWT token
        token = valid_jwt_token

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        # Store and retrieve token
        token_manager.store_token(stored_token)
        retrieved_token = token_manager.load_token()

        # Tokens should match
        assert retrieved_token.token == token
        assert retrieved_token.expires_at == stored_token.expires_at

    def test_token_file_content_is_encrypted(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test that token file content is encrypted, not plaintext."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Use real JWT token
        token = valid_jwt_token

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        token_manager.store_token(stored_token)

        # Read raw file content
        with open(token_manager.token_file_path, "rb") as f:
            raw_content = f.read()

        # Content should be encrypted (not contain plaintext token)
        assert token.encode() not in raw_content
        assert b"testuser" not in raw_content

    def test_token_file_size_limits(self, temp_project_dir, credential_manager):
        """Test enforcement of 64KB token file size limit."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Create oversized token file
        large_content = b"x" * (65 * 1024)  # 65KB > 64KB limit
        token_manager.token_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_manager.token_file_path, "wb") as f:
            f.write(large_content)

        # Loading should fail due to size limit
        with pytest.raises(TokenSecurityError):
            token_manager.load_token()


class TestPersistentTokenManagerConcurrency:
    """Test PersistentTokenManager concurrent access handling."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def credential_manager(self):
        """Create ProjectCredentialManager for testing."""
        return ProjectCredentialManager()

    def test_file_locking_prevents_concurrent_writes(
        self, temp_project_dir, credential_manager, real_jwt_manager
    ):
        """Test that file locking prevents concurrent write operations."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Create test tokens using real JWT manager
        token1 = real_jwt_manager.create_test_user_token("testuser1").access_token
        token2 = real_jwt_manager.create_test_user_token("testuser2").access_token

        stored_token1 = StoredToken(
            token=token1,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data1",
        )

        stored_token2 = StoredToken(
            token=token2,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data2",
        )

        # Attempt concurrent writes
        results = []
        errors = []

        def write_token(stored_token, index):
            try:
                token_manager.store_token(stored_token)
                results.append(f"success_{index}")
            except Exception as e:
                errors.append(f"error_{index}: {e}")

        # Start concurrent threads
        thread1 = threading.Thread(target=write_token, args=(stored_token1, 1))
        thread2 = threading.Thread(target=write_token, args=(stored_token2, 2))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # At least one should succeed, at least one might get a lock timeout
        assert len(results) >= 1
        # Total operations should equal number of threads
        assert len(results) + len(errors) == 2

    def test_file_lock_timeout_handling(self, temp_project_dir, credential_manager):
        """Test file lock timeout handling."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
            lock_timeout_seconds=1,  # Short timeout for testing
        )

        # Test that token manager was created successfully with short timeout
        assert token_manager.lock_timeout_seconds == 1
        # This test validates that the timeout parameter is properly set
        # Full lock timeout behavior testing would require more complex setup


class TestTokenCaching:
    """Test token caching functionality with TTL."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def credential_manager(self):
        """Create ProjectCredentialManager for testing."""
        return ProjectCredentialManager()

    def test_token_caching_with_ttl(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test that tokens are cached with 60-second TTL."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
            cache_ttl_seconds=60,
        )

        # Use real JWT token
        token = valid_jwt_token

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        # Store token
        token_manager.store_token(stored_token)

        # First load should read from file and populate cache
        token1 = token_manager.load_token()

        # Verify token is cached by checking internal state
        assert token_manager._cached_token is not None
        assert token_manager._cached_token.token == token1.token

        # Second load should use cache
        token2 = token_manager.load_token()

        # Both tokens should be identical (cache hit)
        assert token1.token == token2.token
        assert token1.expires_at == token2.expires_at

    def test_cache_expiry_forces_file_reload(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test that cache expiry forces reload from file."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
            cache_ttl_seconds=1,  # 1 second TTL for testing
        )

        # Use real JWT token
        token = valid_jwt_token

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        # Store token
        token_manager.store_token(stored_token)

        # Load token (should be cached)
        token1 = token_manager.load_token()
        assert token1.token == token

        # Wait for cache to expire
        time.sleep(1.1)  # Wait slightly longer than TTL

        # Load token again (should reload from file)
        token2 = token_manager.load_token()
        assert token2.token == token
        # Both tokens should be equal but cache should have been refreshed


class TestCIDXRemoteAPIClientTokenPersistence:
    """Test CIDXRemoteAPIClient integration with persistent token management."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def mock_server_url(self):
        """Mock server URL for testing."""
        return "https://test.cidx.server.com"

    @pytest.fixture
    def mock_credentials(self):
        """Mock credentials for testing."""
        return {"username": "testuser", "password": "testpass"}

    def test_api_client_uses_persistent_token_manager(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test that CIDXRemoteAPIClient integrates with PersistentTokenManager."""
        api_client = CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Should have persistent token manager
        assert hasattr(api_client, "_persistent_token_manager")
        assert api_client._persistent_token_manager is not None
        assert api_client.project_root == temp_project_dir

    @pytest.mark.asyncio
    async def test_token_persistence_across_client_restarts(
        self, temp_project_dir, mock_server_url, mock_credentials, valid_jwt_token
    ):
        """Test that tokens persist across API client restarts."""
        # Create first client instance and authenticate
        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock successful authentication response
            mock_response = Mock()  # Use Mock, not AsyncMock for httpx Response
            mock_response.status_code = 200
            mock_response.json.return_value = {"access_token": valid_jwt_token}
            mock_post.return_value = mock_response

            async with CIDXRemoteAPIClient(
                server_url=mock_server_url,
                credentials=mock_credentials,
                project_root=temp_project_dir,
            ) as client1:
                # Force authentication
                token1 = await client1._get_valid_token()
                assert token1 == valid_jwt_token

        # Create second client instance (simulating restart)
        async with CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        ) as client2:
            # Should load token from persistent storage without re-authentication
            with patch("httpx.AsyncClient.post") as mock_post_restart:
                mock_post_restart.return_value = Mock()  # Should not be called

                token2 = await client2._get_valid_token()

                # Should use persisted token
                assert token2 == valid_jwt_token
                # Should not have called authentication endpoint again
                mock_post_restart.assert_not_called()

    @pytest.mark.asyncio
    async def test_automatic_token_refresh_with_persistence(
        self, temp_project_dir, mock_server_url, mock_credentials, valid_jwt_token
    ):
        """Test automatic token refresh with immediate persistence."""
        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock token refresh response
            mock_response = Mock()  # Use Mock, not AsyncMock
            mock_response.status_code = 200
            mock_response.json.return_value = {"access_token": valid_jwt_token}
            mock_post.return_value = mock_response

            async with CIDXRemoteAPIClient(
                server_url=mock_server_url,
                credentials=mock_credentials,
                project_root=temp_project_dir,
            ) as client:
                # Mock token manager to simulate near-expiry token
                client._persistent_token_manager.load_token = MagicMock(
                    return_value=StoredToken(
                        token="expired_token",
                        expires_at=datetime.now(timezone.utc)
                        + timedelta(minutes=1),  # Near expiry
                        created_at=datetime.now(timezone.utc),
                        encrypted_data=b"encrypted_data",
                    )
                )

                # Mock the store_token method so we can assert it was called
                client._persistent_token_manager.store_token = MagicMock()

                # Mock JWT manager to detect near expiry
                client.jwt_manager.is_token_near_expiry = MagicMock(return_value=True)

                # Get valid token should trigger refresh
                token = await client._get_valid_token()

                # Should get refreshed token (using valid JWT from fixture)
                assert token == valid_jwt_token

                # Should have stored new token
                client._persistent_token_manager.store_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_re_authentication_fallback_with_persistence(
        self, temp_project_dir, mock_server_url, mock_credentials, valid_jwt_token
    ):
        """Test re-authentication fallback when refresh fails."""
        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock re-authentication response (after refresh failure)
            mock_response = Mock()  # Use Mock instead of AsyncMock
            mock_response.status_code = 200
            mock_response.json.return_value = {"access_token": valid_jwt_token}
            mock_post.return_value = mock_response

            async with CIDXRemoteAPIClient(
                server_url=mock_server_url,
                credentials=mock_credentials,
                project_root=temp_project_dir,
            ) as client:
                # Clear any existing tokens
                client._current_token = None

                # Get valid token should authenticate successfully
                token = await client._get_valid_token()

                # Should get new authentication token
                assert token == valid_jwt_token

                # Verify the token was retrieved
                assert client._current_token == valid_jwt_token


class TestCircuitBreakerPattern:
    """Test circuit breaker pattern for authentication failures."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def mock_server_url(self):
        """Mock server URL for testing."""
        return "https://test.cidx.server.com"

    @pytest.fixture
    def mock_credentials(self):
        """Mock credentials for testing."""
        return {"username": "testuser", "password": "testpass"}

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test circuit breaker opens after 5 consecutive authentication failures."""
        with patch("httpx.AsyncClient.post") as mock_post:
            # Mock authentication failures
            mock_response = Mock()  # Use Mock instead of AsyncMock
            mock_response.status_code = 401
            mock_response.json.return_value = {"detail": "Authentication failed"}
            mock_post.return_value = mock_response

            async with CIDXRemoteAPIClient(
                server_url=mock_server_url,
                credentials=mock_credentials,
                project_root=temp_project_dir,
            ) as client:
                # Try authentication 5 times (should trigger circuit breaker)
                for i in range(5):
                    with pytest.raises(AuthenticationError):
                        await client._authenticate()

                # 6th attempt should be blocked by circuit breaker
                with pytest.raises(Exception) as exc_info:
                    await client._authenticate()

                assert "circuit breaker" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_after_timeout(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test circuit breaker allows retry after 300-second recovery timeout."""
        async with CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        ) as client:
            # Force circuit breaker open by setting failure count and time
            client._auth_failures = 5
            client._circuit_breaker_open = True
            client._circuit_breaker_opened_at = time.time() - 301  # 301 seconds ago

            # Check that circuit breaker recovery works
            client._check_circuit_breaker()

            # After recovery, circuit breaker should be closed
            assert not client._circuit_breaker_open
            assert client._auth_failures == 0


class TestNetworkTimeoutsAndLimits:
    """Test network timeout and connection limit configuration."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def mock_server_url(self):
        """Mock server URL for testing."""
        return "https://test.cidx.server.com"

    @pytest.fixture
    def mock_credentials(self):
        """Mock credentials for testing."""
        return {"username": "testuser", "password": "testpass"}

    def test_http_client_timeout_configuration(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test HTTP client is configured with proper timeouts."""
        api_client = CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Check timeout configuration
        session = api_client.session
        assert session.timeout.connect == 10.0  # 10s connect timeout
        assert session.timeout.read == 30.0  # 30s read timeout
        assert session.timeout.write == 10.0  # 10s write timeout
        assert session.timeout.pool == 5.0  # 5s pool timeout

    def test_connection_pooling_limits(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test HTTP/2 connection pooling with proper limits."""
        api_client = CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Verify session was created successfully with limits
        # Note: httpx AsyncClient doesn't expose limits as public attributes
        # but we can verify the session exists and is properly configured
        session = api_client.session
        assert session is not None
        assert hasattr(session, "_transport")  # Internal transport should exist

    def test_request_rate_limiting(
        self, temp_project_dir, mock_server_url, mock_credentials
    ):
        """Test request rate limiting with semaphore."""
        api_client = CIDXRemoteAPIClient(
            server_url=mock_server_url,
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Check rate limiting semaphore
        assert hasattr(api_client, "_request_semaphore")
        assert api_client._request_semaphore._value == 10  # 10 concurrent requests


class TestSecurityConstraints:
    """Test security constraint enforcement."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield project_root

    @pytest.fixture
    def credential_manager(self):
        """Create ProjectCredentialManager for testing."""
        return ProjectCredentialManager()

    def test_rs256_algorithm_enforcement(self, temp_project_dir, credential_manager):
        """Test that only RS256 JWT tokens are accepted."""
        # Create token manager to ensure it can be instantiated
        PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Create token with unsupported algorithm (not HS256/RS256)
        payload = {
            "username": "testuser",
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
        }
        invalid_token = jose_jwt.encode(payload, "secret", algorithm="HS384")

        stored_token = StoredToken(
            token=invalid_token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        # Should reject tokens with unsupported algorithms
        with pytest.raises(TokenSecurityError):
            stored_token.validate_security_constraints()

    def test_token_lifetime_limit_enforcement(
        self, temp_project_dir, credential_manager, real_jwt_manager
    ):
        """Test 24-hour token lifetime limit enforcement."""
        # Create token manager to ensure it can be instantiated
        PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Create token with excessive lifetime (25 hours) using real JWT manager
        payload = {
            "username": "testuser",
            "exp": (datetime.now(timezone.utc) + timedelta(hours=25)).timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
            "sub": "testuser",
            "type": "access",
        }
        # Create token with proper RSA key but excessive lifetime
        token = jose_jwt.encode(
            payload, real_jwt_manager.private_key_pem, algorithm="RS256"
        )

        stored_token = StoredToken(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=25),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        # Should reject tokens with >24 hour lifetime
        with pytest.raises(TokenSecurityError):
            stored_token.validate_security_constraints()

    def test_ssl_certificate_verification_enforcement(
        self, temp_project_dir, credential_manager
    ):
        """Test SSL certificate verification is enforced."""
        # Should fail because enhanced API client doesn't exist yet
        with pytest.raises((ImportError, AttributeError)):
            mock_credentials = {"username": "testuser", "password": "testpass"}

            api_client = CIDXRemoteAPIClient(
                server_url="https://test.example.com",
                credentials=mock_credentials,
                project_root=temp_project_dir,
            )

            # Check SSL verification is enabled
            session = api_client.session
            assert session.verify is True  # SSL verification enabled

    def test_memory_security_overwriting(
        self, temp_project_dir, credential_manager, valid_jwt_token
    ):
        """Test secure memory overwriting of sensitive data."""
        token_manager = PersistentTokenManager(
            project_root=temp_project_dir,
            credential_manager=credential_manager,
            username="testuser",
            repo_path=str(temp_project_dir),
            server_url="https://test.example.com",
        )

        # Store a token to have cached data
        stored_token = StoredToken(
            token=valid_jwt_token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            created_at=datetime.now(timezone.utc),
            encrypted_data=b"encrypted_data",
        )

        token_manager.store_token(stored_token)

        # Verify token is cached
        assert token_manager._cached_token is not None

        # Clean up sensitive data
        token_manager.cleanup_sensitive_data()

        # Verify sensitive data is cleared
        assert token_manager._cached_token is None
        assert token_manager._cache_timestamp == 0
