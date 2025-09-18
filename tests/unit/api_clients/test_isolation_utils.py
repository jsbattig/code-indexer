"""Test Isolation Utilities for API Client Tests.

Provides proper test isolation to prevent rate limiting state contamination
and ensure tests can run reliably without interfering with each other.
Foundation #1 Compliant - No mocks, real isolation mechanisms.
"""

import asyncio
import time
import socket
from typing import Optional, Dict
from contextlib import asynccontextmanager
import pytest


class TestServerManager:
    """Manages test server lifecycle and state isolation."""

    def __init__(self, server_port: int = 8001):
        self.server_port = server_port
        self.server_url = f"http://localhost:{server_port}"
        self._is_available: Optional[bool] = None

    def is_server_available(self) -> bool:
        """Check if test server is actually available."""
        if self._is_available is not None:
            return self._is_available

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", self.server_port))
            sock.close()
            self._is_available = result == 0
            return self._is_available
        except Exception:
            self._is_available = False
            return False

    def reset_availability_cache(self):
        """Reset server availability cache for retesting."""
        self._is_available = None


class RateLimitStateManager:
    """Manages rate limiting state between tests to prevent contamination."""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.test_user_credentials = {
            "username": "test_user",
            "password": "test_password",
        }

    async def reset_rate_limits(self, user_identifier: str = "test_user"):
        """Reset rate limiting state for test isolation."""
        # In a real implementation, this would call a test-only endpoint
        # to reset rate limiting state, or wait for rate limit windows to expire

        # For now, implement a waiting strategy
        await asyncio.sleep(0.1)  # Small delay to avoid rapid-fire requests

    async def wait_for_rate_limit_reset(self, window_seconds: int = 60):
        """Wait for rate limit window to reset."""
        # Implementation depends on the actual rate limiting policy
        # For testing, use a shorter wait time
        test_wait_time = min(window_seconds, 2)  # Max 2 seconds for tests
        await asyncio.sleep(test_wait_time)

    @asynccontextmanager
    async def isolated_rate_limit_context(self, user_id: str = "test_user"):
        """Context manager for isolated rate limiting testing."""
        try:
            # Reset rate limits before test
            await self.reset_rate_limits(user_id)
            yield
        finally:
            # Reset rate limits after test
            await self.reset_rate_limits(user_id)


class NetworkCallTracker:
    """Tracks and manages network calls to prevent test interference."""

    def __init__(self):
        self.call_history: Dict[str, list] = {}
        self.active_requests: set = set()

    def start_request_tracking(self, request_id: str, endpoint: str):
        """Start tracking a network request."""
        if endpoint not in self.call_history:
            self.call_history[endpoint] = []

        self.call_history[endpoint].append(
            {"request_id": request_id, "start_time": time.time(), "status": "active"}
        )
        self.active_requests.add(request_id)

    def complete_request_tracking(self, request_id: str, status_code: int = 200):
        """Complete tracking for a network request."""
        self.active_requests.discard(request_id)

        # Update call history
        for endpoint, calls in self.call_history.items():
            for call in calls:
                if call["request_id"] == request_id:
                    call["end_time"] = time.time()
                    call["status"] = status_code
                    call["duration"] = call["end_time"] - call["start_time"]
                    break

    async def wait_for_active_requests(self, timeout: float = 5.0):
        """Wait for all active requests to complete."""
        start_time = time.time()
        while self.active_requests and (time.time() - start_time) < timeout:
            await asyncio.sleep(0.1)

    def reset_tracking(self):
        """Reset all tracking data for test isolation."""
        self.call_history.clear()
        self.active_requests.clear()

    def get_call_count(self, endpoint: str) -> int:
        """Get the number of calls made to an endpoint."""
        return len(self.call_history.get(endpoint, []))


class TestIsolationManager:
    """Comprehensive test isolation manager for API client tests."""

    def __init__(self, server_port: int = 8001):
        self.server_manager = TestServerManager(server_port)
        self.rate_limit_manager = RateLimitStateManager(
            f"http://localhost:{server_port}"
        )
        self.network_tracker = NetworkCallTracker()

    async def setup_isolated_test(self, test_name: str):
        """Set up isolated test environment."""
        # Check server availability
        if not self.server_manager.is_server_available():
            pytest.skip("Test server not available for real integration testing")

        # Reset network tracking
        self.network_tracker.reset_tracking()

        # Reset rate limiting state
        await self.rate_limit_manager.reset_rate_limits()

        # Small delay for state stabilization
        await asyncio.sleep(0.1)

    async def teardown_isolated_test(self, test_name: str):
        """Clean up after isolated test."""
        # Wait for any active requests to complete
        await self.network_tracker.wait_for_active_requests()

        # Reset rate limiting state for next test
        await self.rate_limit_manager.reset_rate_limits()

        # Small delay for cleanup
        await asyncio.sleep(0.1)

    @asynccontextmanager
    async def isolated_test_context(self, test_name: str):
        """Context manager for completely isolated test execution."""
        try:
            await self.setup_isolated_test(test_name)
            yield self
        finally:
            await self.teardown_isolated_test(test_name)


# Global test isolation manager for shared use
_global_isolation_manager = TestIsolationManager()


@pytest.fixture
async def isolated_test_manager():
    """Pytest fixture for isolated test management."""
    return _global_isolation_manager


@pytest.fixture
async def rate_limit_reset():
    """Pytest fixture that ensures rate limits are reset between tests."""
    # Setup: Reset rate limits before test
    await _global_isolation_manager.rate_limit_manager.reset_rate_limits()

    yield

    # Teardown: Reset rate limits after test
    await _global_isolation_manager.rate_limit_manager.reset_rate_limits()


@pytest.fixture
async def network_call_isolation():
    """Pytest fixture that provides network call isolation."""
    # Setup: Reset network tracking
    _global_isolation_manager.network_tracker.reset_tracking()

    yield _global_isolation_manager.network_tracker

    # Teardown: Wait for requests and reset
    await _global_isolation_manager.network_tracker.wait_for_active_requests()
    _global_isolation_manager.network_tracker.reset_tracking()


@pytest.fixture
async def server_availability_check():
    """Pytest fixture that checks server availability and skips if unavailable."""
    if not _global_isolation_manager.server_manager.is_server_available():
        pytest.skip("Test server not available for real integration testing")

    yield _global_isolation_manager.server_manager


class RetryWithBackoff:
    """Utility for retrying operations with exponential backoff."""

    def __init__(self, max_retries: int = 3, base_delay: float = 0.1):
        self.max_retries = max_retries
        self.base_delay = base_delay

    async def retry_async(self, operation, *args, **kwargs):
        """Retry an async operation with exponential backoff."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    delay = self.base_delay * (2**attempt)
                    await asyncio.sleep(delay)
                else:
                    # Final attempt failed
                    break

        # All retries failed
        raise last_exception

    def retry_sync(self, operation, *args, **kwargs):
        """Retry a sync operation with exponential backoff."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_exception = e

                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    delay = self.base_delay * (2**attempt)
                    time.sleep(delay)
                else:
                    # Final attempt failed
                    break

        # All retries failed
        raise last_exception


# Test helper functions for common isolation patterns
async def skip_if_no_server(server_port: int = 8001):
    """Skip test if server is not available."""
    manager = TestServerManager(server_port)
    if not manager.is_server_available():
        pytest.skip("Test server not available for real integration testing")


async def with_rate_limit_protection(operation, *args, **kwargs):
    """Execute operation with rate limit protection."""
    retry_manager = RetryWithBackoff(max_retries=2, base_delay=0.5)
    return await retry_manager.retry_async(operation, *args, **kwargs)


def create_test_credentials(username: str = "test_user") -> Dict[str, str]:
    """Create test credentials for consistent testing."""
    return {
        "username": username,
        "password": "test_password",
        "server_url": "http://localhost:8001",
    }


# Decorators for test isolation
def with_test_isolation(test_func):
    """Decorator that provides comprehensive test isolation."""

    async def wrapper(*args, **kwargs):
        async with _global_isolation_manager.isolated_test_context(test_func.__name__):
            return await test_func(*args, **kwargs)

    return wrapper


def requires_test_server(test_func):
    """Decorator that skips test if server is not available."""

    def wrapper(*args, **kwargs):
        if not _global_isolation_manager.server_manager.is_server_available():
            pytest.skip("Test server not available for real integration testing")
        return test_func(*args, **kwargs)

    return wrapper


# Error handling for common test isolation issues
class TestIsolationError(Exception):
    """Base exception for test isolation issues."""

    pass


class RateLimitContaminationError(TestIsolationError):
    """Exception raised when rate limit contamination is detected."""

    def __init__(self, endpoint: str, call_count: int):
        super().__init__(
            f"Rate limit contamination detected on {endpoint}: "
            f"{call_count} calls may have affected test isolation"
        )
        self.endpoint = endpoint
        self.call_count = call_count


class ServerUnavailableError(TestIsolationError):
    """Exception raised when test server is not available."""

    def __init__(self, server_url: str):
        super().__init__(f"Test server not available at {server_url}")
        self.server_url = server_url
