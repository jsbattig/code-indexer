"""Integration tests for storage coherence.

Tests that cache is properly invalidated when storage operations modify data.
"""

import json
import signal
import subprocess
import time

import pytest
import rpyc


class TestCacheInvalidation:
    """Test cache invalidation on storage operations."""

    @pytest.fixture
    def daemon_with_cache(self, tmp_path):
        """Start daemon with cached project."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        config_file = config_dir / "config.json"
        config = {"embedding_provider": "voyageai", "api_key": "test-key"}
        config_file.write_text(json.dumps(config))

        index_dir = config_dir / "index"
        index_dir.mkdir()

        socket_path = config_dir / "daemon.sock"

        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(config_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for daemon
        for _ in range(50):
            if socket_path.exists():
                try:
                    conn = rpyc.utils.factory.unix_connect(str(socket_path))
                    conn.close()
                    break
                except Exception:
                    pass
            time.sleep(0.1)

        yield socket_path, project_path, proc

        # Cleanup
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        if socket_path.exists():
            socket_path.unlink()

    def test_clean_invalidates_cache(self, daemon_with_cache):
        """exposed_clean should invalidate cache before clearing vectors."""
        socket_path, project_path, proc = daemon_with_cache

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Load cache with query
            conn.root.exposed_query(str(project_path), "test")
            status_before = conn.root.exposed_get_status()
            assert status_before["cache_loaded"] is True

            # Clean vectors
            clean_result = conn.root.exposed_clean(str(project_path))
            assert clean_result["status"] == "success"

            # Cache should be invalidated
            status_after = conn.root.exposed_get_status()
            assert status_after["cache_loaded"] is False

        finally:
            conn.close()

    def test_clean_data_invalidates_cache(self, daemon_with_cache):
        """exposed_clean_data should invalidate cache before clearing data."""
        socket_path, project_path, proc = daemon_with_cache

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Load cache
            conn.root.exposed_query(str(project_path), "test")
            assert conn.root.exposed_get_status()["cache_loaded"] is True

            # Clean data
            clean_result = conn.root.exposed_clean_data(str(project_path))
            assert clean_result["status"] == "success"

            # Cache should be invalidated
            assert conn.root.exposed_get_status()["cache_loaded"] is False

        finally:
            conn.close()

    def test_index_invalidates_cache(self, daemon_with_cache):
        """exposed_index should invalidate cache before indexing."""
        socket_path, project_path, proc = daemon_with_cache

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Load cache
            conn.root.exposed_query(str(project_path), "test")
            assert conn.root.exposed_get_status()["cache_loaded"] is True

            # Index (will invalidate cache)
            # Note: May fail due to missing dependencies, but should invalidate cache first
            try:
                conn.root.exposed_index(str(project_path))
            except Exception:
                pass  # Indexing may fail, but cache should still be invalidated

            # Cache should be invalidated
            assert conn.root.exposed_get_status()["cache_loaded"] is False

        finally:
            conn.close()

    def test_manual_clear_cache(self, daemon_with_cache):
        """exposed_clear_cache should clear cache manually."""
        socket_path, project_path, proc = daemon_with_cache

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Load cache
            conn.root.exposed_query(str(project_path), "test")
            assert conn.root.exposed_get_status()["cache_loaded"] is True

            # Clear cache manually
            clear_result = conn.root.exposed_clear_cache()
            assert clear_result["status"] == "success"

            # Cache should be cleared
            assert conn.root.exposed_get_status()["cache_loaded"] is False

        finally:
            conn.close()


class TestStatusReporting:
    """Test status reporting with cache state."""

    @pytest.fixture
    def running_daemon(self, tmp_path):
        """Start daemon."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        config_file = config_dir / "config.json"
        config = {"embedding_provider": "voyageai", "api_key": "test-key"}
        config_file.write_text(json.dumps(config))

        index_dir = config_dir / "index"
        index_dir.mkdir()

        socket_path = config_dir / "daemon.sock"

        proc = subprocess.Popen(
            ["python3", "-m", "code_indexer.daemon", str(config_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for daemon
        for _ in range(50):
            if socket_path.exists():
                try:
                    conn = rpyc.utils.factory.unix_connect(str(socket_path))
                    conn.close()
                    break
                except Exception:
                    pass
            time.sleep(0.1)

        yield socket_path, project_path, proc

        # Cleanup
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
        if socket_path.exists():
            socket_path.unlink()

    def test_status_returns_combined_daemon_and_storage_stats(self, running_daemon):
        """exposed_status should return daemon and storage statistics."""
        socket_path, project_path, proc = running_daemon

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Get status
            status = conn.root.exposed_status(str(project_path))

            # Should have both cache and storage sections
            assert "cache" in status
            assert "storage" in status

        finally:
            conn.close()

    def test_get_status_returns_daemon_stats_only(self, running_daemon):
        """exposed_get_status should return daemon cache stats only."""
        socket_path, project_path, proc = running_daemon

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Get daemon status
            status = conn.root.exposed_get_status()

            # Should have cache_loaded field
            assert "cache_loaded" in status
            assert isinstance(status["cache_loaded"], bool)

        finally:
            conn.close()

    def test_status_after_query_shows_cache_info(self, running_daemon):
        """Status after query should show cache information."""
        socket_path, project_path, proc = running_daemon

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Execute query to load cache
            conn.root.exposed_query(str(project_path), "test")

            # Get status
            status = conn.root.exposed_get_status()

            # Should show cache loaded with metadata
            assert status["cache_loaded"] is True
            assert "access_count" in status
            assert status["access_count"] > 0
            assert "last_accessed" in status

        finally:
            conn.close()
