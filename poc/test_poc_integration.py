"""Integration tests for RPyC daemon and client.

These tests start a real daemon process and connect with the client.
"""

import multiprocessing
import socket
import time
from pathlib import Path
from typing import Generator

import pytest

from poc.client import CIDXClient
from poc.daemon_service import start_daemon


SOCKET_PATH = "/tmp/cidx-poc-daemon.sock"


@pytest.fixture
def clean_socket() -> Generator[None, None, None]:
    """Ensure socket is cleaned up before and after test."""
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()
    yield
    if Path(SOCKET_PATH).exists():
        Path(SOCKET_PATH).unlink()


@pytest.fixture
def daemon_process(clean_socket) -> Generator[multiprocessing.Process, None, None]:
    """Start daemon in subprocess and clean up after test."""

    def run_daemon():
        start_daemon(SOCKET_PATH)

    process = multiprocessing.Process(target=run_daemon)
    process.start()

    # Wait for daemon to start
    max_wait = 5.0
    start_time = time.time()
    while time.time() - start_time < max_wait:
        if Path(SOCKET_PATH).exists():
            # Try to connect to ensure it's ready
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(SOCKET_PATH)
                sock.close()
                break
            except (ConnectionRefusedError, FileNotFoundError):
                sock.close()
                time.sleep(0.1)
    else:
        process.terminate()
        process.join(timeout=2)
        pytest.fail("Daemon failed to start within 5 seconds")

    yield process

    # Cleanup
    process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill()
        process.join()


class TestDaemonClientIntegration:
    """Integration tests for daemon and client."""

    def test_client_connects_to_running_daemon(self, daemon_process):
        """Test client successfully connects to running daemon."""
        client = CIDXClient(SOCKET_PATH)

        connected = client.connect()
        assert connected is True
        assert client.connection is not None
        assert client.connection_time_ms > 0

        client.close()

    def test_client_connection_time_under_50ms(self, daemon_process):
        """Test connection time is under 50ms target."""
        client = CIDXClient(SOCKET_PATH)

        connected = client.connect()
        assert connected is True
        # Connection should be very fast for local Unix socket
        assert (
            client.connection_time_ms < 50
        ), f"Connection took {client.connection_time_ms}ms, target <50ms"

        client.close()

    def test_ping_measures_rpc_overhead(self, daemon_process):
        """Test ping method for measuring RPC overhead."""
        client = CIDXClient(SOCKET_PATH)
        client.connect()

        start_time = time.perf_counter()
        response = client.ping()
        rpc_overhead_ms = (time.perf_counter() - start_time) * 1000

        assert response == "pong"
        # RPC overhead should be very low for Unix socket
        # Using <50ms threshold for CI environment tolerance
        assert (
            rpc_overhead_ms < 50
        ), f"RPC overhead {rpc_overhead_ms}ms, target <50ms for Unix socket"

        client.close()

    def test_query_returns_results(self, daemon_process):
        """Test query execution returns results."""
        client = CIDXClient(SOCKET_PATH)
        client.connect()

        results = client.query("test query", search_mode="semantic", limit=5)

        assert "results" in results
        assert "count" in results
        assert "mode" in results
        assert results["mode"] == "semantic"
        assert len(results["results"]) > 0

        client.close()

    def test_query_caching_improves_performance(self, daemon_process):
        """Test cached queries are faster than first query."""
        client = CIDXClient(SOCKET_PATH)
        client.connect()

        # First query (uncached)
        results1 = client.query("cache test", search_mode="semantic", limit=5)
        first_time = results1["timing_ms"]
        assert results1["cached"] is False

        # Second query (should be cached)
        results2 = client.query("cache test", search_mode="semantic", limit=5)
        cached_time = results2["timing_ms"]
        assert results2["cached"] is True

        # Cached query should be significantly faster
        # Using <20ms threshold to account for CI environment overhead
        assert (
            cached_time < 20
        ), f"Cached query took {cached_time}ms, target <20ms (5ms sleep + overhead)"
        assert cached_time < first_time, "Cached query should be faster than first query"

        client.close()

    def test_get_stats_returns_cache_info(self, daemon_process):
        """Test get_stats returns cache statistics."""
        client = CIDXClient(SOCKET_PATH)
        client.connect()

        # Execute a query to populate cache
        client.query("stats test", search_mode="semantic", limit=5)

        # Get stats
        stats = client.get_stats()

        assert "cache_size" in stats
        assert "cache_keys" in stats
        assert stats["cache_size"] > 0

        client.close()


class TestClientRetry:
    """Test client retry logic with exponential backoff."""

    def test_client_retries_when_daemon_not_running(self, clean_socket):
        """Test client retries with exponential backoff when daemon not running."""
        client = CIDXClient(SOCKET_PATH)

        start_time = time.perf_counter()
        connected = client.connect()
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        assert connected is False
        assert client.connection is None

        # Should have tried all backoff delays: 100 + 500 + 1000 + 2000 = 3600ms
        # Allow some overhead for execution
        assert (
            elapsed_ms >= 3600
        ), f"Should have waited at least 3600ms, got {elapsed_ms}ms"

    def test_client_stops_retrying_after_exhaustion(self, clean_socket):
        """Test client stops retrying after all attempts exhausted."""
        client = CIDXClient(SOCKET_PATH)

        connected = client.connect()

        assert connected is False
        # Should not raise exception, just return False
