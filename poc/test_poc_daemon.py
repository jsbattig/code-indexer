"""Unit tests for RPyC daemon PoC."""

import socket
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


class TestDaemonSocketBinding:
    """Test daemon socket binding as atomic lock."""

    def test_daemon_binds_to_socket_successfully(self, clean_socket):
        """Test daemon can bind to Unix socket successfully."""
        # This will be implemented when daemon_service.py exists
        # For now, test raw socket binding
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(SOCKET_PATH)
            sock.listen(1)
            assert Path(SOCKET_PATH).exists()
        finally:
            sock.close()

    def test_second_daemon_fails_with_address_in_use(self, clean_socket):
        """Test second daemon fails to bind when socket is already bound."""
        # First socket
        sock1 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock1.bind(SOCKET_PATH)
        sock1.listen(1)

        # Second socket should fail
        sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            with pytest.raises(OSError) as exc_info:
                sock2.bind(SOCKET_PATH)
            assert "Address already in use" in str(exc_info.value)
        finally:
            sock1.close()
            sock2.close()

    def test_socket_cleanup_on_daemon_exit(self, clean_socket):
        """Test socket is cleaned up when daemon exits."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(SOCKET_PATH)
        sock.listen(1)
        assert Path(SOCKET_PATH).exists()

        sock.close()
        # Socket file should still exist after close (needs explicit unlink)
        assert Path(SOCKET_PATH).exists()

        # Clean up manually
        Path(SOCKET_PATH).unlink()
        assert not Path(SOCKET_PATH).exists()


class TestDaemonService:
    """Test minimal daemon service implementation."""

    def test_daemon_service_initializes_cache(self, clean_socket):
        """Test daemon service initializes with empty cache."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        assert hasattr(service, "query_cache")
        assert isinstance(service.query_cache, dict)
        assert len(service.query_cache) == 0

    def test_preimport_heavy_modules_imports_successfully(self, clean_socket):
        """Test _preimport_heavy_modules imports argparse and rich."""
        import sys
        from poc.daemon_service import CIDXDaemonService

        # Create service (calls _preimport_heavy_modules in __init__)
        _service = CIDXDaemonService()  # Variable needed to trigger __init__

        # Verify argparse is loaded
        assert "argparse" in sys.modules

        # Verify rich modules are loaded
        assert "rich.console" in sys.modules
        assert "rich.progress" in sys.modules

    def test_simulate_query_semantic_mode(self, clean_socket):
        """Test _simulate_query returns correct structure for semantic mode."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service._simulate_query("test query", "semantic", 5, None)

        assert "results" in result
        assert "count" in result
        assert "mode" in result
        assert result["mode"] == "semantic"
        assert isinstance(result["results"], list)
        assert result["count"] == 5

    def test_simulate_query_fts_mode(self, clean_socket):
        """Test _simulate_query returns correct structure for fts mode."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service._simulate_query("test query", "fts", 3, None)

        assert "results" in result
        assert "count" in result
        assert "mode" in result
        assert result["mode"] == "fts"
        assert result["count"] == 3

    def test_simulate_query_hybrid_mode(self, clean_socket):
        """Test _simulate_query returns correct structure for hybrid mode."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service._simulate_query("test query", "hybrid", 10, None)

        assert "results" in result
        assert "count" in result
        assert "mode" in result
        assert result["mode"] == "hybrid"
        assert result["count"] == 5  # Limited by min(limit, 5)

    def test_simulate_query_respects_limit(self, clean_socket):
        """Test _simulate_query respects result limit."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()

        # Request 2 results
        result = service._simulate_query("test query", "semantic", 2, None)
        assert result["count"] == 2
        assert len(result["results"]) == 2

    def test_simulate_query_includes_language_filter(self, clean_socket):
        """Test _simulate_query accepts language parameter."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service._simulate_query("test query", "semantic", 5, "python")

        # Language filter is accepted but not used in simulation
        assert result is not None
        assert "results" in result

    def test_exposed_get_stats_returns_cache_info(self, clean_socket):
        """Test exposed_get_stats returns cache statistics."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()

        # Initially empty cache
        stats = service.exposed_get_stats()
        assert "cache_size" in stats
        assert "cache_keys" in stats
        assert stats["cache_size"] == 0
        assert stats["cache_keys"] == []

        # Add item to cache
        service.query_cache["test_key"] = {"test": "data"}

        # Verify stats reflect cache state
        stats = service.exposed_get_stats()
        assert stats["cache_size"] == 1
        assert "test_key" in stats["cache_keys"]


class TestQueryMethods:
    """Test exposed query methods on daemon."""

    def test_exposed_query_returns_results(self, clean_socket):
        """Test exposed_query method returns query results."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("test query", "semantic", 5, None)

        assert "results" in result
        assert "count" in result
        assert "timing_ms" in result
        assert "cached" in result
        assert result["cached"] is False  # First query is not cached

    def test_exposed_query_cache_hit(self, clean_socket):
        """Test cached query returns faster."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()

        # First query (uncached)
        result1 = service.exposed_query("cache test", "semantic", 5, None)
        assert result1["cached"] is False

        # Second query (should be cached)
        result2 = service.exposed_query("cache test", "semantic", 5, None)
        assert result2["cached"] is True
        # Cached query should be faster
        assert result2["timing_ms"] < result1["timing_ms"]

    def test_exposed_query_handles_semantic_search(self, clean_socket):
        """Test exposed_query handles semantic search queries."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("semantic test", "semantic", 5, None)

        assert result["mode"] == "semantic"
        assert "results" in result

    def test_exposed_query_handles_fts_search(self, clean_socket):
        """Test exposed_query handles FTS search queries."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("fts test", "fts", 5, None)

        assert result["mode"] == "fts"
        assert "results" in result

    def test_exposed_query_handles_hybrid_search(self, clean_socket):
        """Test exposed_query handles hybrid search queries."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("hybrid test", "hybrid", 5, None)

        assert result["mode"] == "hybrid"
        assert "results" in result

    def test_exposed_query_respects_limit(self, clean_socket):
        """Test exposed_query respects result limit."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("limit test", "semantic", 3, None)

        assert result["count"] == 3

    def test_exposed_query_with_language_filter(self, clean_socket):
        """Test exposed_query accepts language parameter."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        result = service.exposed_query("python test", "semantic", 5, "python")

        # Language filter is passed through but not used in simulation
        assert "results" in result

    def test_exposed_ping_returns_pong(self, clean_socket):
        """Test exposed_ping returns 'pong'."""
        from poc.daemon_service import CIDXDaemonService

        service = CIDXDaemonService()
        response = service.exposed_ping()

        assert response == "pong"
