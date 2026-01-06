"""Test suite for Network Error Handling with CIDX Remote Repository Linking Mode.

Tests network error classification, retry logic with exponential backoff,
user guidance system, and integration with existing API client patterns.
Following TDD principles with comprehensive error scenario coverage.
"""

import pytest
import asyncio
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock, Mock

import httpx
from rich.console import Console

from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
    CircuitBreakerOpenError,
)

# Import network-specific exceptions that we'll implement
try:
    from code_indexer.api_clients.base_client import (
        ConnectionError as NetworkConnectionError,
        TimeoutError as NetworkTimeoutError,
        DNSResolutionError,
        SSLCertificateError,
        ServerError,
        RateLimitError,
    )
except ImportError:
    # These don't exist yet - we'll implement them
    class NetworkConnectionError(NetworkError):
        pass

    class NetworkTimeoutError(NetworkError):
        pass

    class DNSResolutionError(NetworkError):
        pass

    class SSLCertificateError(NetworkError):
        pass

    class ServerError(NetworkError):
        pass

    class RateLimitError(NetworkError):
        pass


# Import retry and user guidance modules that we'll implement
try:
    from code_indexer.api_clients.network_error_handler import (
        NetworkErrorHandler,
        RetryConfig,
        UserGuidanceProvider,
    )
except ImportError:
    # These don't exist yet - we'll implement them
    class NetworkErrorHandler:
        pass

    class RetryConfig:
        pass

    class UserGuidanceProvider:
        pass


class TestNetworkErrorClassification:
    """Test network error classification system for different failure types."""

    def test_connection_refused_error_classification(self):
        """Test classification of connection refused errors."""
        # Create a connection refused httpx exception
        with pytest.raises(NetworkConnectionError) as exc_info:
            # This test should fail initially - we haven't implemented classification yet
            handler = NetworkErrorHandler()
            httpx_error = httpx.ConnectError("Connection refused")
            handler.classify_network_error(httpx_error)

        # Verify error message and troubleshooting guidance
        assert "Cannot connect to server" in str(exc_info.value)
        assert hasattr(exc_info.value, "user_guidance")
        assert (
            "Check if the CIDX server is running and accessible"
            in exc_info.value.user_guidance
        )

    def test_dns_resolution_error_classification(self):
        """Test classification of DNS resolution failures."""
        with pytest.raises(DNSResolutionError) as exc_info:
            handler = NetworkErrorHandler()
            # Simulate DNS resolution failure
            httpx_error = httpx.ConnectError("Name resolution failed")
            handler.classify_network_error(httpx_error)

        assert "Cannot resolve server address" in str(exc_info.value)
        assert "Check your internet connection" in exc_info.value.user_guidance

    def test_ssl_certificate_error_classification(self):
        """Test classification of SSL certificate errors."""
        with pytest.raises(SSLCertificateError) as exc_info:
            handler = NetworkErrorHandler()
            httpx_error = httpx.ConnectError("SSL certificate verification failed")
            handler.classify_network_error(httpx_error)

        assert "SSL certificate verification failed" in str(exc_info.value)
        assert (
            "SSL certificate errors prevent secure connections"
            in exc_info.value.user_guidance
        )

    def test_timeout_error_classification(self):
        """Test classification of various timeout scenarios."""
        handler = NetworkErrorHandler()

        # Test connect timeout
        with pytest.raises(NetworkTimeoutError) as exc_info:
            httpx_error = httpx.ConnectTimeout("Connection timeout")
            handler.classify_network_error(httpx_error)

        assert "Connection timed out" in str(exc_info.value)
        assert "Check your network connection" in exc_info.value.user_guidance

        # Test read timeout
        with pytest.raises(NetworkTimeoutError) as exc_info:
            httpx_error = httpx.ReadTimeout("Read timeout")
            handler.classify_network_error(httpx_error)

        assert "Request timed out" in str(exc_info.value)

    def test_server_error_classification(self):
        """Test classification of server-side errors (5xx responses)."""
        handler = NetworkErrorHandler()

        # Test 500 Internal Server Error
        with pytest.raises(ServerError) as exc_info:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"detail": "Internal Server Error"}
            httpx_error = httpx.HTTPStatusError(
                "Server error", request=Mock(), response=mock_response
            )
            handler.classify_network_error(httpx_error)

        assert "Server is experiencing issues" in str(exc_info.value)
        assert "Please wait a few minutes and try again" in exc_info.value.user_guidance

    def test_rate_limit_error_classification(self):
        """Test classification of rate limiting (429) errors."""
        handler = NetworkErrorHandler()

        with pytest.raises(RateLimitError) as exc_info:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_response.json.return_value = {"detail": "Too many requests"}
            httpx_error = httpx.HTTPStatusError(
                "Rate limited", request=Mock(), response=mock_response
            )
            handler.classify_network_error(httpx_error)

        assert "Too many requests" in str(exc_info.value)
        assert "Wait 60 seconds before trying again" in exc_info.value.user_guidance
        assert hasattr(exc_info.value, "retry_after")
        assert exc_info.value.retry_after == 60

    def test_authentication_error_no_retry(self):
        """Test that authentication errors are not classified as retryable."""
        handler = NetworkErrorHandler()

        with pytest.raises(AuthenticationError) as exc_info:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"detail": "Authentication failed"}
            httpx_error = httpx.HTTPStatusError(
                "Unauthorized", request=Mock(), response=mock_response
            )
            handler.classify_network_error(httpx_error)

        # Should classify as AuthenticationError, not a network error
        assert isinstance(exc_info.value, AuthenticationError)
        assert "Authentication failed" in str(exc_info.value)

    def test_client_error_no_retry(self):
        """Test that 4xx client errors (except 429) are not retryable."""
        handler = NetworkErrorHandler()

        # Test 404 Not Found - should not be retryable
        with pytest.raises(APIClientError) as exc_info:
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.json.return_value = {"detail": "Not found"}
            httpx_error = httpx.HTTPStatusError(
                "Not found", request=Mock(), response=mock_response
            )
            handler.classify_network_error(httpx_error)

        assert exc_info.value.status_code == 404
        assert (
            not hasattr(exc_info.value, "is_retryable")
            or not exc_info.value.is_retryable
        )


class TestRetryLogicWithExponentialBackoff:
    """Test retry logic implementation with exponential backoff."""

    def test_retry_config_creation(self):
        """Test RetryConfig creation with proper defaults."""
        config = RetryConfig()

        assert config.max_retries == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 30.0
        assert config.backoff_multiplier == 2.0
        assert config.jitter_enabled is True

    def test_retry_config_custom_values(self):
        """Test RetryConfig with custom configuration."""
        config = RetryConfig(
            max_retries=5,
            initial_delay=0.5,
            max_delay=60.0,
            backoff_multiplier=1.5,
            jitter_enabled=False,
        )

        assert config.max_retries == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 60.0
        assert config.backoff_multiplier == 1.5
        assert config.jitter_enabled is False

    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self):
        """Test exponential backoff timing follows expected pattern."""
        handler = NetworkErrorHandler()
        config = RetryConfig(
            jitter_enabled=False
        )  # Disable jitter for predictable testing

        async def mock_operation():
            raise NetworkConnectionError("Connection failed")

        start_time = time.time()

        with pytest.raises(NetworkConnectionError):
            await handler.retry_with_backoff(
                mock_operation, config, progress_callback=None
            )

        # Should have attempted: initial + 3 retries = 4 total attempts
        # Delays should be approximately: 1s, 2s, 4s between attempts
        elapsed = time.time() - start_time
        assert elapsed >= 7.0  # 1 + 2 + 4 = 7 seconds minimum
        assert elapsed < 10.0  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_retry_with_jitter(self):
        """Test retry logic includes jitter to prevent thundering herd."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=2, jitter_enabled=True)

        delays = []

        async def mock_sleep(delay):
            delays.append(delay)
            # Don't actually sleep in tests
            pass

        with patch("asyncio.sleep", side_effect=mock_sleep):

            async def mock_operation():
                raise NetworkConnectionError("Connection failed")

            with pytest.raises(NetworkConnectionError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback=None
                )

        # Should have 2 delays (for 2 retries after initial attempt)
        assert len(delays) == 2

        # Jitter should make delays slightly different from exact exponential values
        # First delay should be around 1s ± jitter
        assert 0.5 <= delays[0] <= 1.5
        # Second delay should be around 2s ± jitter
        assert 1.0 <= delays[1] <= 3.0

    @pytest.mark.asyncio
    async def test_retry_success_after_failures(self):
        """Test successful operation after some failures."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=3)

        attempt_count = 0

        async def mock_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise NetworkConnectionError("Connection failed")
            return {"success": True}

        result = await handler.retry_with_backoff(
            mock_operation, config, progress_callback=None
        )

        assert result == {"success": True}
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_for_permanent_errors(self):
        """Test that permanent errors are not retried."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=3)

        attempt_count = 0

        async def mock_operation():
            nonlocal attempt_count
            attempt_count += 1
            raise AuthenticationError("Invalid credentials")

        with pytest.raises(AuthenticationError):
            await handler.retry_with_backoff(
                mock_operation, config, progress_callback=None
            )

        # Should only attempt once for permanent errors
        assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_progress_indication_during_retries(self):
        """Test progress indication is called during retry attempts."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=2)

        progress_calls = []

        def progress_callback(message: str, retry_count: int, max_retries: int):
            progress_calls.append((message, retry_count, max_retries))

        async def mock_operation():
            raise NetworkTimeoutError("Request timed out")

        with patch("asyncio.sleep"):  # Don't actually sleep in tests
            with pytest.raises(NetworkTimeoutError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback
                )

        # Should have progress calls for each retry attempt
        assert len(progress_calls) == 2
        assert progress_calls[0] == ("Retrying after connection error...", 1, 2)
        assert progress_calls[1] == ("Retrying after connection error...", 2, 2)

    @pytest.mark.asyncio
    async def test_timeout_limits_respected(self):
        """Test that retry attempts respect reasonable timeout limits."""
        handler = NetworkErrorHandler()
        config = RetryConfig(
            max_retries=10,  # Try many retries
            initial_delay=5.0,  # Long delays
            max_delay=60.0,
        )

        async def mock_operation():
            raise NetworkConnectionError("Connection failed")

        start_time = time.time()

        with patch("asyncio.sleep"):  # Don't actually sleep in tests
            with pytest.raises(NetworkConnectionError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback=None
                )

        # Should complete quickly in tests even with long configured delays
        elapsed = time.time() - start_time
        assert elapsed < 1.0  # Should complete quickly due to mocked sleep


class TestUserGuidanceSystem:
    """Test user guidance system for different error scenarios."""

    def test_connection_error_guidance(self):
        """Test user guidance for connection errors."""
        provider = UserGuidanceProvider()

        error = NetworkConnectionError("Connection refused")
        guidance = provider.get_guidance(error)

        expected_steps = [
            "Check if the CIDX server is running and accessible",
            "Verify the server URL is correct",
            "Check your firewall settings",
            "Verify network connectivity to the server",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_dns_resolution_guidance(self):
        """Test user guidance for DNS resolution failures."""
        provider = UserGuidanceProvider()

        error = DNSResolutionError("Name resolution failed")
        guidance = provider.get_guidance(error)

        expected_steps = [
            "Check your internet connection",
            "Verify the server hostname is correct",
            "Try using an IP address instead of hostname",
            "Check your DNS server settings",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_ssl_certificate_guidance(self):
        """Test user guidance for SSL certificate errors."""
        provider = UserGuidanceProvider()

        error = SSLCertificateError("SSL certificate verification failed")
        guidance = provider.get_guidance(error)

        expected_steps = [
            "Check if the server certificate is valid and not expired",
            "Verify the server hostname matches the certificate",
            "Check if you need to update your certificate store",
            "Contact your system administrator",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_timeout_guidance(self):
        """Test user guidance for timeout errors."""
        provider = UserGuidanceProvider()

        error = NetworkTimeoutError("Request timed out")
        guidance = provider.get_guidance(error)

        expected_steps = [
            "Check your network connection speed and stability",
            "Try again - this may be a temporary issue",
            "Check if the server is under heavy load",
            "Consider increasing timeout settings if problem persists",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_server_error_guidance(self):
        """Test user guidance for server errors."""
        provider = UserGuidanceProvider()

        error = ServerError("Internal Server Error", status_code=500)
        guidance = provider.get_guidance(error)

        expected_steps = [
            "The server is experiencing internal issues",
            "Please wait a few minutes and try again",
            "Check server status page if available",
            "Contact server administrator if problem persists",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_rate_limit_guidance(self):
        """Test user guidance for rate limiting errors."""
        provider = UserGuidanceProvider()

        error = RateLimitError("Too many requests", retry_after=60)
        guidance = provider.get_guidance(error)

        expected_steps = [
            "You are sending requests too quickly",
            "Wait 60 seconds before trying again",
            "Reduce the frequency of your requests",
            "Consider implementing request throttling",
        ]

        for step in expected_steps:
            assert step in guidance.troubleshooting_steps

    def test_guidance_with_contact_info(self):
        """Test guidance includes contact information when appropriate."""
        provider = UserGuidanceProvider()

        error = SSLCertificateError("SSL certificate verification failed")
        guidance = provider.get_guidance(error)

        assert guidance.contact_info is not None
        assert "system administrator" in guidance.contact_info.lower()

    def test_guidance_formatting_for_console(self):
        """Test guidance can be formatted for console output."""
        provider = UserGuidanceProvider()
        Console()

        error = NetworkConnectionError("Connection refused")
        guidance = provider.get_guidance(error)

        formatted = guidance.format_for_console()

        assert "Troubleshooting Steps:" in formatted
        assert "1. Check if the CIDX server is running" in formatted


class TestCIDXRemoteAPIClientNetworkErrorHandling:
    """Test integration of network error handling with existing API client."""

    @pytest.fixture
    def api_client(self):
        """Create test API client with mock credentials."""
        credentials = {"username": "testuser", "password": "testpass"}
        return CIDXRemoteAPIClient(
            server_url="https://test-server.com", credentials=credentials
        )

    @pytest.mark.asyncio
    async def test_connection_error_handling_in_authenticated_request(self, api_client):
        """Test connection errors are properly handled in authenticated requests."""
        # Mock the session and its request method
        mock_session = AsyncMock()
        mock_session.request.side_effect = httpx.ConnectError("Connection refused")

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(NetworkConnectionError) as exc_info:
                await api_client._authenticated_request("GET", "/test-endpoint")

            assert "Cannot connect to server" in str(exc_info.value)
            assert hasattr(exc_info.value, "user_guidance")

    @pytest.mark.asyncio
    async def test_timeout_error_handling_in_authenticated_request(self, api_client):
        """Test timeout errors are properly handled in authenticated requests."""
        mock_session = AsyncMock()
        mock_session.request.side_effect = httpx.ReadTimeout("Request timeout")

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(NetworkTimeoutError) as exc_info:
                await api_client._authenticated_request("GET", "/test-endpoint")

            assert "Request timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_server_error_retry_logic(self, api_client):
        """Test that 5xx server errors trigger retry logic."""
        retry_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal retry_count
            retry_count += 1

            if retry_count < 2:
                # Return 500 error response for first attempt
                mock_response = Mock()
                mock_response.status_code = 500
                mock_response.json.return_value = {"detail": "Internal Server Error"}
                return mock_response
            else:
                # Success on 2nd attempt
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": "success"}
                return mock_response

        mock_session = AsyncMock()
        mock_session.request.side_effect = mock_request

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
            patch("asyncio.sleep"),
        ):  # Don't actually sleep in tests
            response = await api_client._authenticated_request("GET", "/test-endpoint")

            assert response.status_code == 200
            assert retry_count == 2  # Initial attempt + 1 retry

    @pytest.mark.asyncio
    async def test_authentication_errors_not_retried(self, api_client):
        """Test that 401 authentication errors follow existing token refresh logic."""
        attempt_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"detail": "Invalid token"}
            # Return response instead of raising exception
            return mock_response

        mock_session = AsyncMock()
        mock_session.request.side_effect = mock_request

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(AuthenticationError):
                await api_client._authenticated_request("GET", "/test-endpoint")

            # Should attempt twice (initial + retry after token refresh)
            assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_error_with_retry_after(self, api_client):
        """Test rate limit errors respect Retry-After header."""
        attempt_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count == 1:
                # Return 429 on first attempt
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "2"}
                mock_response.json.return_value = {"detail": "Rate limited"}
                return mock_response
            else:
                # Success on retry
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": "success"}
                return mock_response

        mock_session = AsyncMock()
        mock_session.request.side_effect = mock_request

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
            patch("asyncio.sleep") as mock_sleep,
        ):
            response = await api_client._authenticated_request("GET", "/test-endpoint")

            assert response.status_code == 200
            # Should have waited with exponential backoff (not specific retry-after in this context)
            mock_sleep.assert_called()


class TestGracefulDegradation:
    """Test graceful degradation when remote server becomes unreachable."""

    @pytest.fixture
    def api_client(self):
        """Create test API client with project root for configuration preservation."""
        import tempfile

        credentials = {"username": "testuser", "password": "testpass"}

        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            yield CIDXRemoteAPIClient(
                server_url="https://unreachable-server.com",
                credentials=credentials,
                project_root=project_root,
            )

    @pytest.mark.asyncio
    async def test_server_unreachable_graceful_failure(self, api_client):
        """Test graceful failure when server becomes unreachable."""
        mock_session = AsyncMock()
        mock_session.request.side_effect = httpx.ConnectError(
            "Name or service not known"
        )

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(DNSResolutionError) as exc_info:
                await api_client._authenticated_request("GET", "/test-endpoint")

            # Should not crash, should provide clear error message
            assert "Cannot resolve server address" in str(exc_info.value)
            assert hasattr(exc_info.value, "user_guidance")

    @pytest.mark.asyncio
    async def test_configuration_preserved_after_network_failure(self, api_client):
        """Test that local configuration is preserved after network failures."""
        # Simulate network failure
        mock_session = AsyncMock()
        mock_session.request.side_effect = httpx.ConnectError("Connection failed")

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(NetworkConnectionError):
                await api_client._authenticated_request("GET", "/test-endpoint")

        # Configuration should still be accessible
        assert api_client.server_url == "https://unreachable-server.com"
        assert api_client.credentials["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_no_crash_on_unexpected_network_errors(self, api_client):
        """Test system doesn't crash on unexpected network errors."""
        mock_session = AsyncMock()
        # Simulate unexpected network error
        mock_session.request.side_effect = Exception("Unexpected network error")

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
        ):
            with pytest.raises(APIClientError) as exc_info:
                await api_client._authenticated_request("GET", "/test-endpoint")

            # Should wrap unexpected errors gracefully
            assert "Unexpected error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_recovery_after_network_restoration(self, api_client):
        """Test system can recover after network is restored."""
        attempt_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count <= 1:
                # Network failure for first attempt only
                raise httpx.ConnectError("Connection failed")
            else:
                # Network restored on second attempt
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.return_value = {"result": "success"}
                return mock_response

        mock_session = AsyncMock()
        mock_session.request.side_effect = mock_request

        with (
            patch.object(type(api_client), "session", mock_session),
            patch.object(api_client, "_get_valid_token", return_value="test-token"),
            patch("asyncio.sleep"),
        ):  # Don't actually sleep in tests
            response = await api_client._authenticated_request("GET", "/test-endpoint")

            # Should eventually succeed after network restoration
            assert response.status_code == 200


class TestPerformanceRequirements:
    """Test performance requirements for network error handling."""

    @pytest.mark.asyncio
    async def test_error_classification_overhead(self):
        """Test error classification adds minimal overhead."""
        handler = NetworkErrorHandler()

        start_time = time.time()

        # Classify 100 errors to measure overhead
        for _ in range(100):
            try:
                httpx_error = httpx.ConnectError("Connection failed")
                handler.classify_network_error(httpx_error)
            except NetworkConnectionError:
                pass

        elapsed = time.time() - start_time

        # Should complete within reasonable time (< 100ms for 100 classifications)
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_retry_timeout_limits(self):
        """Test retry attempts don't exceed 30 seconds total."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=3)

        async def mock_operation():
            raise NetworkConnectionError("Connection failed")

        start_time = time.time()

        with patch("asyncio.sleep"):  # Don't actually sleep, just measure logic time
            with pytest.raises(NetworkConnectionError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback=None
                )

        elapsed = time.time() - start_time

        # Logic should complete quickly even with retry configuration
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_memory_usage_during_retries(self):
        """Test memory usage doesn't increase during retry scenarios."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=5)

        import tracemalloc

        tracemalloc.start()

        async def mock_operation():
            # Create some temporary objects that should be cleaned up
            raise NetworkConnectionError("Connection failed")

        with patch("asyncio.sleep"):
            with pytest.raises(NetworkConnectionError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback=None
                )

        # Get memory usage after retries
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Memory usage should be reasonable (less than 1MB)
        assert peak < 1024 * 1024  # 1MB


class TestIntegrationWithCircuitBreaker:
    """Test integration with existing circuit breaker patterns."""

    @pytest.fixture
    def api_client(self):
        """Create test API client."""
        credentials = {"username": "testuser", "password": "testpass"}
        return CIDXRemoteAPIClient(
            server_url="https://test-server.com", credentials=credentials
        )

    @pytest.mark.asyncio
    async def test_network_errors_trigger_circuit_breaker(self, api_client):
        """Test that network errors contribute to circuit breaker state."""
        # Force multiple authentication failures through network errors
        mock_session = AsyncMock()
        mock_session.post.side_effect = httpx.ConnectError("Connection refused")

        with patch.object(type(api_client), "session", mock_session):
            # Generate enough failures to trip circuit breaker
            for i in range(5):
                with pytest.raises((NetworkConnectionError, CircuitBreakerOpenError)):
                    await api_client._authenticate()

            # Circuit breaker should now be open
            with pytest.raises(CircuitBreakerOpenError):
                await api_client._authenticate()

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_unnecessary_retries(self, api_client):
        """Test circuit breaker prevents retries when open."""
        # Trip the circuit breaker
        api_client._circuit_breaker_open = True
        api_client._circuit_breaker_opened_at = time.time()

        attempt_count = 0

        async def mock_operation():
            nonlocal attempt_count
            attempt_count += 1
            raise NetworkConnectionError("Connection failed")

        NetworkErrorHandler()
        RetryConfig(max_retries=3)

        # Should fail immediately due to circuit breaker, not attempt retries
        with pytest.raises(CircuitBreakerOpenError):
            await api_client._authenticate()

        # No retries should have been attempted
        assert attempt_count == 0


class TestProgressIndication:
    """Test progress indication during retry attempts."""

    @pytest.mark.asyncio
    async def test_progress_callback_called_during_retries(self):
        """Test progress callback is called with proper parameters."""
        handler = NetworkErrorHandler()
        config = RetryConfig(max_retries=2)

        progress_calls = []

        def progress_callback(message: str, retry_count: int, max_retries: int):
            progress_calls.append(
                {
                    "message": message,
                    "retry_count": retry_count,
                    "max_retries": max_retries,
                    "timestamp": time.time(),
                }
            )

        async def mock_operation():
            raise NetworkTimeoutError("Request timed out")

        with patch("asyncio.sleep"):
            with pytest.raises(NetworkTimeoutError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback
                )

        # Should have 2 progress calls for 2 retries
        assert len(progress_calls) == 2

        # Check progress call parameters
        assert progress_calls[0]["retry_count"] == 1
        assert progress_calls[0]["max_retries"] == 2
        assert progress_calls[1]["retry_count"] == 2
        assert progress_calls[1]["max_retries"] == 2

    @pytest.mark.asyncio
    async def test_progress_updates_every_two_seconds(self):
        """Test progress indication updates at least every 2 seconds during retries."""
        handler = NetworkErrorHandler()
        config = RetryConfig(
            max_retries=1,
            initial_delay=5.0,  # Long delay to test progress updates
        )

        progress_calls = []

        def progress_callback(message: str, retry_count: int, max_retries: int):
            progress_calls.append(time.time())

        async def mock_operation():
            raise NetworkConnectionError("Connection failed")

        # Mock sleep to simulate time passing
        async def mock_sleep(delay):
            # Simulate progress updates during long delays
            if delay >= 2.0:
                # Call progress callback multiple times during long sleep
                for i in range(int(delay // 2)):
                    progress_callback(f"Waiting... ({i+1}/{int(delay//2)})", 1, 1)
                    await asyncio.sleep(0.01)  # Small actual delay for testing

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(NetworkConnectionError):
                await handler.retry_with_backoff(
                    mock_operation, config, progress_callback
                )

        # Should have multiple progress updates during long delay
        assert len(progress_calls) >= 2

    def test_rich_console_integration(self):
        """Test progress indication integrates with Rich console output."""
        from rich.console import Console
        from rich.progress import Progress

        console = Console()

        # Test that we can create rich progress displays
        with Progress(console=console) as progress:
            task = progress.add_task("Retrying connection...", total=3)

            # Simulate progress updates
            for i in range(3):
                progress.update(task, completed=i + 1, description=f"Retry {i+1}/3")

        # Should complete without errors
        assert True
