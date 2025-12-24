"""Integration tests for query caching with real indexes.

Tests that daemon loads indexes into memory and serves queries from cache.
"""

import json
import signal
import subprocess
import time

import pytest
import rpyc


class TestQueryCaching:
    """Test query caching with real index loading."""

    @pytest.fixture
    def daemon_with_project(self, tmp_path):
        """Start daemon with a mock project structure."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        # Create .code-indexer structure
        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        # Create config
        config_file = config_dir / "config.json"
        config = {"embedding_provider": "voyageai", "api_key": "test-key"}
        config_file.write_text(json.dumps(config))

        # Create empty index directory (simulates indexed project)
        index_dir = config_dir / "index"
        index_dir.mkdir()

        socket_path = config_dir / "daemon.sock"

        # Start daemon
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

    def test_first_query_loads_cache(self, daemon_with_project):
        """First query should load indexes into cache."""
        socket_path, project_path, proc = daemon_with_project

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Get initial status
            status_before = conn.root.exposed_get_status()
            assert status_before["cache_loaded"] is False

            # Execute query (will load cache)
            # Note: Will return empty results since no real index exists
            conn.root.exposed_query(str(project_path), "test query", limit=10)

            # Cache should now be loaded
            status_after = conn.root.exposed_get_status()
            assert status_after["cache_loaded"] is True

        finally:
            conn.close()

    def test_second_query_reuses_cache(self, daemon_with_project):
        """Second query should reuse cached indexes."""
        socket_path, project_path, proc = daemon_with_project

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # First query
            conn.root.exposed_query(str(project_path), "first query")

            # Get status after first query
            status_first = conn.root.exposed_get_status()
            assert status_first["cache_loaded"] is True
            access_count_first = status_first["access_count"]

            # Second query
            conn.root.exposed_query(str(project_path), "second query")

            # Access count should increment (reusing cache)
            status_second = conn.root.exposed_get_status()
            assert status_second["cache_loaded"] is True
            assert status_second["access_count"] > access_count_first

        finally:
            conn.close()

    def test_cache_tracks_access_time(self, daemon_with_project):
        """Cache should track last access timestamp."""
        socket_path, project_path, proc = daemon_with_project

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Execute query
            conn.root.exposed_query(str(project_path), "test")

            # Get status
            status = conn.root.exposed_get_status()
            assert "last_accessed" in status
            assert status["expired"] is False

        finally:
            conn.close()

    def test_different_project_replaces_cache(self, daemon_with_project, tmp_path):
        """Querying different project should replace cache entry."""
        socket_path, project_path1, proc = daemon_with_project

        # Create second project
        project_path2 = tmp_path / "test_project2"
        project_path2.mkdir()
        config_dir2 = project_path2 / ".code-indexer"
        config_dir2.mkdir()

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Query first project
            conn.root.exposed_query(str(project_path1), "query1")
            status1 = conn.root.exposed_get_status()
            assert str(project_path1) in status1["project_path"]

            # Query second project
            conn.root.exposed_query(str(project_path2), "query2")
            status2 = conn.root.exposed_get_status()
            assert str(project_path2) in status2["project_path"]

        finally:
            conn.close()


class TestFTSCaching:
    """Test FTS index caching."""

    @pytest.fixture
    def daemon_with_fts(self, tmp_path):
        """Start daemon with FTS index structure."""
        project_path = tmp_path / "test_project"
        project_path.mkdir()

        config_dir = project_path / ".code-indexer"
        config_dir.mkdir()

        config_file = config_dir / "config.json"
        config = {"embedding_provider": "voyageai", "api_key": "test-key"}
        config_file.write_text(json.dumps(config))

        # Create empty FTS index directory
        fts_dir = config_dir / "tantivy_index"
        fts_dir.mkdir()

        socket_path = config_dir / "daemon.sock"

        # Start daemon
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

    def test_fts_query_loads_tantivy_index(self, daemon_with_fts):
        """FTS query should attempt to load Tantivy index."""
        socket_path, project_path, proc = daemon_with_fts

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Execute FTS query (will try to load FTS indexes)
            # Note: Will fail to load since directory is empty, but should try
            result = conn.root.exposed_query_fts(str(project_path), "test")

            # Should return (possibly empty) results
            assert isinstance(result, list)

        finally:
            conn.close()

    def test_hybrid_query_executes_both_searches(self, daemon_with_fts):
        """Hybrid query should execute both semantic and FTS."""
        socket_path, project_path, proc = daemon_with_fts

        conn = rpyc.utils.factory.unix_connect(str(socket_path))
        try:
            # Execute hybrid query
            result = conn.root.exposed_query_hybrid(str(project_path), "test")

            # Should have both result types
            assert "semantic" in result
            assert "fts" in result
            assert isinstance(result["semantic"], list)
            assert isinstance(result["fts"], list)

        finally:
            conn.close()


class TestConcurrentQueries:
    """Test concurrent query handling."""

    @pytest.fixture
    def running_daemon(self, tmp_path):
        """Start daemon for concurrent testing."""
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

    def test_multiple_concurrent_connections(self, running_daemon):
        """Multiple clients should be able to query concurrently."""
        socket_path, project_path, proc = running_daemon

        # Create multiple connections
        connections = []
        try:
            for _ in range(3):
                conn = rpyc.utils.factory.unix_connect(str(socket_path))
                connections.append(conn)

            # All should be able to query
            for i, conn in enumerate(connections):
                result = conn.root.exposed_query(str(project_path), f"query{i}")
                assert isinstance(result, list)

        finally:
            for conn in connections:
                conn.close()
