"""Unit tests for RPyC client PoC."""

from pathlib import Path
from typing import Generator

import pytest


SOCKET_PATH = "/tmp/cidx-poc-daemon.sock"


@pytest.fixture
def clean_socket() -> Generator[None, None, None]:
    """Ensure socket is cleaned up before and after test."""
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()
    yield
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()


class TestClientConnection:
    """Test client connection logic."""

    def test_client_connects_successfully_when_daemon_running(self, clean_socket):
        """Test client connects when daemon is already running."""
        pytest.skip("Client not yet implemented")

    def test_client_uses_exponential_backoff_retry(self, clean_socket):
        """Test client retries with exponential backoff [100, 500, 1000, 2000]ms."""
        pytest.skip("Client not yet implemented")

    def test_client_fails_after_max_retries(self, clean_socket):
        """Test client fails after exhausting all retry attempts."""
        pytest.skip("Client not yet implemented")

    def test_client_finds_socket_path_from_config(self, clean_socket):
        """Test client finds socket path by backtracking to .code-indexer/config.json."""
        pytest.skip("Client not yet implemented")


class TestClientTiming:
    """Test client timing measurements."""

    def test_client_measures_connection_time(self, clean_socket):
        """Test client measures time to establish connection."""
        pytest.skip("Client not yet implemented")

    def test_client_measures_query_time(self, clean_socket):
        """Test client measures time for query execution."""
        pytest.skip("Client not yet implemented")

    def test_client_measures_total_time(self, clean_socket):
        """Test client measures total time (connection + query)."""
        pytest.skip("Client not yet implemented")


class TestExponentialBackoff:
    """Test exponential backoff implementation."""

    def test_backoff_delays_are_correct(self):
        """Test exponential backoff uses exact delays: [100, 500, 1000, 2000]ms."""
        from poc.client import ExponentialBackoff

        backoff = ExponentialBackoff()
        expected_delays = [100, 500, 1000, 2000]  # milliseconds

        for expected_ms in expected_delays:
            delay_ms = backoff.next_delay_ms()
            assert delay_ms == expected_ms, f"Expected {expected_ms}ms, got {delay_ms}ms"

    def test_backoff_exhausts_after_max_attempts(self):
        """Test backoff indicates exhaustion after all retries."""
        from poc.client import ExponentialBackoff

        backoff = ExponentialBackoff()
        delays = [100, 500, 1000, 2000]

        for _ in delays:
            assert not backoff.exhausted()
            backoff.next_delay_ms()

        # After 4 attempts, should be exhausted
        assert backoff.exhausted()

    def test_backoff_reset_starts_over(self):
        """Test backoff reset restarts the sequence."""
        from poc.client import ExponentialBackoff

        backoff = ExponentialBackoff()

        # Use up some retries
        backoff.next_delay_ms()
        backoff.next_delay_ms()

        # Reset
        backoff.reset()

        # Should start from beginning
        assert backoff.next_delay_ms() == 100
