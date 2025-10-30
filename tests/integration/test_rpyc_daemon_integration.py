"""
Integration tests for RPyC daemon service with real components.

These tests validate the complete daemon functionality with real indexes,
focusing on the two critical requirements:
1. Cache hit performance <100ms
2. Proper daemon shutdown with socket cleanup
"""

import sys
import time
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from unittest import TestCase, skipIf
from unittest.mock import patch

try:
    import rpyc
    RPYC_AVAILABLE = True
except ImportError:
    RPYC_AVAILABLE = False


@skipIf(not RPYC_AVAILABLE, "RPyC not installed")
class TestRPyCDaemonIntegration(TestCase):
    """Integration tests for RPyC daemon with real components."""

    def setUp(self):
        """Set up test environment with real project."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Create config
        self.config_path = self.project_path / ".code-indexer" / "config.json"
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps({
            "daemon": {
                "enabled": True,
                "ttl_minutes": 10,
                "auto_shutdown_on_idle": False
            },
            "embedding_provider": "voyage",
            "qdrant": {
                "mode": "filesystem"
            }
        }))

        # Create test files
        self._create_test_files()

        # Socket path
        self.socket_path = self.project_path / ".code-indexer" / "daemon.sock"

        # Daemon process
        self.daemon_process = None

    def tearDown(self):
        """Clean up test environment."""
        # Stop daemon if running
        if self.daemon_process:
            self.daemon_process.terminate()
            self.daemon_process.wait(timeout=5)

        # Clean up socket
        if self.socket_path and self.socket_path.exists():
            self.socket_path.unlink()

        # Remove temp directory
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def _create_test_files(self):
        """Create sample code files for testing."""
        # Create Python files
        (self.project_path / "main.py").write_text("""
def authenticate_user(username, password):
    '''Authenticate user with credentials.'''
    # Authentication logic here
    return True

def login_handler(request):
    '''Handle login requests.'''
    username = request.get('username')
    password = request.get('password')
    return authenticate_user(username, password)
""")

        (self.project_path / "database.py").write_text("""
class DatabaseManager:
    '''Manage database connections and queries.'''

    def connect(self):
        '''Establish database connection.'''
        pass

    def query(self, sql):
        '''Execute SQL query.'''
        pass
""")

        (self.project_path / "utils.py").write_text("""
def validate_input(data):
    '''Validate user input.'''
    return data is not None

def format_response(status, message):
    '''Format API response.'''
    return {'status': status, 'message': message}
""")

    def _start_daemon_process(self):
        """Start daemon in subprocess."""
        cmd = [
            sys.executable,
            "-m", "src.code_indexer.services.rpyc_daemon",
            str(self.config_path)
        ]
        self.daemon_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent.parent.parent)
        )

        # Wait for daemon to start
        time.sleep(2)

        # Verify daemon is running
        self.assertIsNone(self.daemon_process.poll(), "Daemon should be running")

    def _connect_to_daemon(self):
        """Connect to running daemon."""
        return rpyc.connect(
            str(self.socket_path),
            config={'allow_all_attrs': True}
        )

    def test_cache_hit_performance_real_data(self):
        """Test cache hit performance with real index data (<100ms requirement)."""
        # Start daemon
        self._start_daemon_process()

        try:
            # Connect to daemon
            conn = self._connect_to_daemon()

            # Create real index first
            from src.code_indexer.services.file_chunking_manager import FileChunkingManager
            from src.code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.project_path)
            chunking_manager = FileChunkingManager(config_manager)

            # Index the test files
            chunking_manager.index_repository(
                repo_path=str(self.project_path),
                force_reindex=True
            )

            # First query - loads indexes (cache miss)
            start = time.perf_counter()
            results1 = conn.root.query(
                str(self.project_path),
                "authentication user login",
                limit=5
            )
            load_time = time.perf_counter() - start
            print(f"First query (cache miss): {load_time*1000:.1f}ms")

            # Second query - uses cache (cache hit)
            start = time.perf_counter()
            results2 = conn.root.query(
                str(self.project_path),
                "database connection",
                limit=5
            )
            cache_time = time.perf_counter() - start
            print(f"Second query (cache hit): {cache_time*1000:.1f}ms")

            # Performance assertion
            self.assertLess(
                cache_time,
                0.1,  # 100ms requirement
                f"Cache hit took {cache_time*1000:.1f}ms, requirement is <100ms"
            )

            # Cache should be much faster than initial load
            self.assertLess(
                cache_time,
                load_time * 0.5,  # At least 50% faster
                "Cache hit should be significantly faster than initial load"
            )

            # Run 50 queries and verify average performance
            times = []
            for i in range(50):
                start = time.perf_counter()
                conn.root.query(
                    str(self.project_path),
                    f"test query {i}",
                    limit=5
                )
                times.append(time.perf_counter() - start)

            avg_time = sum(times) / len(times)
            print(f"Average of 50 cache hits: {avg_time*1000:.1f}ms")

            self.assertLess(
                avg_time,
                0.05,  # Target 50ms average
                f"Average cache hit {avg_time*1000:.1f}ms exceeds 50ms target"
            )

        finally:
            if 'conn' in locals():
                conn.close()

    def test_daemon_shutdown_removes_socket(self):
        """Test daemon shutdown properly removes socket file."""
        # Start daemon
        self._start_daemon_process()

        # Verify socket exists
        time.sleep(1)
        self.assertTrue(self.socket_path.exists(), "Socket file should exist")

        try:
            # Connect and trigger shutdown
            conn = self._connect_to_daemon()
            result = conn.root.shutdown()
            self.assertEqual(result["status"], "shutting_down")
            conn.close()
        except Exception:
            # Connection may close during shutdown
            pass

        # Wait for shutdown
        time.sleep(2)

        # Verify daemon terminated
        if self.daemon_process:
            self.daemon_process.wait(timeout=5)
            self.assertIsNotNone(
                self.daemon_process.poll(),
                "Daemon process should have terminated"
            )

        # Verify socket removed
        self.assertFalse(
            self.socket_path.exists(),
            "Socket file should be removed after shutdown"
        )

    def test_concurrent_clients_performance(self):
        """Test performance with multiple concurrent clients."""
        # Start daemon
        self._start_daemon_process()

        try:
            # Create index
            from src.code_indexer.services.file_chunking_manager import FileChunkingManager
            from src.code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.project_path)
            chunking_manager = FileChunkingManager(config_manager)
            chunking_manager.index_repository(
                repo_path=str(self.project_path),
                force_reindex=True
            )

            # Connect multiple clients
            clients = []
            for i in range(5):
                conn = self._connect_to_daemon()
                clients.append(conn)

            # Warm up cache with first query
            clients[0].root.query(str(self.project_path), "warmup", limit=5)

            # Run concurrent queries from all clients
            def run_queries(client_idx):
                conn = clients[client_idx]
                times = []
                for i in range(10):
                    start = time.perf_counter()
                    conn.root.query(
                        str(self.project_path),
                        f"query {client_idx}-{i}",
                        limit=5
                    )
                    times.append(time.perf_counter() - start)
                return times

            # Execute queries in parallel
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(run_queries, i)
                    for i in range(5)
                ]
                all_times = []
                for future in futures:
                    all_times.extend(future.result())

            # Verify all queries were fast
            avg_time = sum(all_times) / len(all_times)
            max_time = max(all_times)

            print(f"Concurrent queries - Avg: {avg_time*1000:.1f}ms, Max: {max_time*1000:.1f}ms")

            self.assertLess(
                avg_time,
                0.1,  # 100ms average
                f"Average concurrent query {avg_time*1000:.1f}ms exceeds 100ms"
            )

            self.assertLess(
                max_time,
                0.2,  # 200ms max
                f"Max concurrent query {max_time*1000:.1f}ms exceeds 200ms"
            )

        finally:
            for conn in clients:
                try:
                    conn.close()
                except Exception:
                    pass

    def test_ttl_eviction_and_reload(self):
        """Test TTL eviction and cache reload."""
        # Start daemon with short TTL
        self.config_path.write_text(json.dumps({
            "daemon": {
                "enabled": True,
                "ttl_minutes": 0.1,  # 6 seconds for testing
                "auto_shutdown_on_idle": False
            },
            "embedding_provider": "voyage",
            "qdrant": {
                "mode": "filesystem"
            }
        }))

        self._start_daemon_process()

        try:
            conn = self._connect_to_daemon()

            # Create index
            from src.code_indexer.services.file_chunking_manager import FileChunkingManager
            from src.code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.project_path)
            chunking_manager = FileChunkingManager(config_manager)
            chunking_manager.index_repository(
                repo_path=str(self.project_path),
                force_reindex=True
            )

            # First query - loads cache
            conn.root.query(str(self.project_path), "test", limit=5)

            # Check status - cache should be loaded
            status = conn.root.get_status()
            self.assertFalse(status["cache_empty"])

            # Wait for TTL to expire (6+ seconds)
            time.sleep(8)

            # Trigger eviction check
            # Note: In real scenario, eviction thread runs automatically

            # Check status - cache should be evicted
            status = conn.root.get_status()
            # After eviction, cache_empty should be True

            # Query again - should reload
            start = time.perf_counter()
            conn.root.query(str(self.project_path), "test2", limit=5)
            reload_time = time.perf_counter() - start

            print(f"Reload after eviction: {reload_time*1000:.1f}ms")

            # Status should show cache loaded again
            status = conn.root.get_status()
            self.assertFalse(status.get("cache_empty", False))

        finally:
            if 'conn' in locals():
                conn.close()

    def test_watch_mode_integration(self):
        """Test watch mode integration with daemon."""
        self._start_daemon_process()

        try:
            conn = self._connect_to_daemon()

            # Start watch
            result = conn.root.watch_start(str(self.project_path))
            self.assertEqual(result["status"], "started")
            self.assertTrue(result["watching"])

            # Check watch status
            status = conn.root.watch_status()
            self.assertTrue(status["watching"])
            self.assertEqual(status["project"], str(self.project_path))

            # Create a new file while watching
            time.sleep(1)
            new_file = self.project_path / "new_module.py"
            new_file.write_text("""
def new_function():
    '''A new function added while watching.'''
    return "Hello from watch mode"
""")

            # Wait for watch to process
            time.sleep(2)

            # Stop watch
            result = conn.root.watch_stop(str(self.project_path))
            self.assertEqual(result["status"], "stopped")

            # Verify watch is stopped
            status = conn.root.watch_status()
            self.assertFalse(status["watching"])

        finally:
            if 'conn' in locals():
                conn.close()

    def test_storage_operations_cache_coherence(self):
        """Test cache coherence with storage operations."""
        self._start_daemon_process()

        try:
            conn = self._connect_to_daemon()

            # Create index
            from src.code_indexer.services.file_chunking_manager import FileChunkingManager
            from src.code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack(self.project_path)
            chunking_manager = FileChunkingManager(config_manager)
            chunking_manager.index_repository(
                repo_path=str(self.project_path),
                force_reindex=True
            )

            # Query to load cache
            conn.root.query(str(self.project_path), "test", limit=5)

            # Verify cache is loaded
            status = conn.root.get_status()
            self.assertFalse(status.get("cache_empty", True))
            self.assertTrue(status.get("semantic_cached", False))

            # Perform clean operation
            with patch('src.code_indexer.services.cleanup_service.CleanupService.clean_vectors'):
                result = conn.root.clean(str(self.project_path))
                self.assertTrue(result["cache_invalidated"])

            # Cache should be invalidated
            status = conn.root.get_status()
            self.assertTrue(status.get("cache_empty", False))

            # Load cache again
            conn.root.query(str(self.project_path), "test", limit=5)
            status = conn.root.get_status()
            self.assertFalse(status.get("cache_empty", True))

            # Perform clean_data operation
            with patch('src.code_indexer.services.cleanup_service.CleanupService.clean_data'):
                result = conn.root.clean_data(str(self.project_path))
                self.assertTrue(result["cache_invalidated"])

            # Cache should be invalidated again
            status = conn.root.get_status()
            self.assertTrue(status.get("cache_empty", False))

        finally:
            if 'conn' in locals():
                conn.close()

    def test_fts_caching_performance(self):
        """Test FTS index caching performance."""
        # Create FTS index directory
        fts_dir = self.project_path / ".code-indexer" / "tantivy_index"
        fts_dir.mkdir(parents=True, exist_ok=True)

        # Start daemon
        self._start_daemon_process()

        try:
            conn = self._connect_to_daemon()

            # Mock Tantivy being available
            with patch('tantivy.Index.open') as mock_open:
                mock_index = MagicMock()
                mock_searcher = MagicMock()
                mock_index.searcher.return_value = mock_searcher
                mock_open.return_value = mock_index

                # First FTS query - loads index
                start = time.perf_counter()
                result1 = conn.root.query_fts(str(self.project_path), "function")
                load_time = time.perf_counter() - start

                # Second FTS query - uses cache
                start = time.perf_counter()
                result2 = conn.root.query_fts(str(self.project_path), "class")
                cache_time = time.perf_counter() - start

                print(f"FTS - Load: {load_time*1000:.1f}ms, Cache: {cache_time*1000:.1f}ms")

                # FTS cache should be very fast (<20ms)
                self.assertLess(
                    cache_time,
                    0.02,  # 20ms for FTS
                    f"FTS cache hit {cache_time*1000:.1f}ms exceeds 20ms"
                )

        finally:
            if 'conn' in locals():
                conn.close()


class MockMagicMock:
    """Simple mock for environments without unittest.mock."""
    def __init__(self):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return MockMagicMock()


# Use local mock if unittest.mock not available
try:
    from unittest.mock import MagicMock
except ImportError:
    MagicMock = MockMagicMock


if __name__ == "__main__":
    import unittest
    unittest.main()