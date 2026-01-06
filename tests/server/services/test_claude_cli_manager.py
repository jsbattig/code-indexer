"""
Comprehensive tests for ClaudeCliManager.

Tests cover:
- Worker pool initialization
- Non-blocking work submission
- Atomic API key synchronization with file locking
- CLI availability checking with caching
- Graceful shutdown
"""

import fcntl
import json
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch, MagicMock


from code_indexer.server.services.claude_cli_manager import ClaudeCliManager


class TestClaudeCliManagerInitialization:
    """Test ClaudeCliManager initialization and worker pool setup."""

    def test_initializes_with_correct_number_of_workers(self):
        """AC1: ClaudeCliManager creates specified number of worker threads."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=4)

        assert len(manager._worker_threads) == 4
        assert all(t.is_alive() for t in manager._worker_threads)

        manager.shutdown()

    def test_worker_threads_are_daemon_threads(self):
        """AC1: Worker threads are daemon threads (don't block shutdown)."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        assert all(t.daemon for t in manager._worker_threads)

        manager.shutdown()

    def test_creates_work_queue(self):
        """AC1: ClaudeCliManager creates work queue."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        assert isinstance(manager._work_queue, queue.Queue)

        manager.shutdown()

    def test_default_max_workers(self):
        """ClaudeCliManager defaults to 4 workers if not specified."""
        manager = ClaudeCliManager(api_key="test-key")

        assert len(manager._worker_threads) == 4

        manager.shutdown()


class TestNonBlockingWorkSubmission:
    """Test non-blocking work submission and callback invocation."""

    def test_submit_work_returns_immediately(self):
        """AC2: submit_work() returns immediately (non-blocking)."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        callback_invoked = threading.Event()

        def slow_callback(success: bool, result: str):
            time.sleep(0.1)  # Simulate slow callback
            callback_invoked.set()

        # Measure time to submit work
        start = time.time()
        manager.submit_work(Path("/tmp/test-repo"), slow_callback)
        elapsed = time.time() - start

        # Should return in <10ms (well before callback completes)
        assert (
            elapsed < 0.01
        ), f"submit_work took {elapsed*1000:.2f}ms (should be <10ms)"

        # Wait for callback to complete
        callback_invoked.wait(timeout=2.0)
        assert callback_invoked.is_set()

        manager.shutdown()

    def test_submit_work_queues_work_correctly(self):
        """AC2: Work is queued and processed by workers."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        results: List[Tuple[bool, str]] = []
        results_lock = threading.Lock()
        completion_event = threading.Event()

        def callback(success: bool, result: str):
            with results_lock:
                results.append((success, result))
                if len(results) == 3:
                    completion_event.set()

        # Submit multiple work items
        for i in range(3):
            manager.submit_work(Path(f"/tmp/repo-{i}"), callback)

        # Wait for all work to complete
        completion_event.wait(timeout=5.0)

        assert len(results) == 3
        assert all(success for success, _ in results)

        manager.shutdown()

    def test_callback_invoked_with_success_result(self):
        """AC2: Callback is invoked with (success, result) on completion."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)

        callback_result = []
        completion_event = threading.Event()

        def callback(success: bool, result: str):
            callback_result.append((success, result))
            completion_event.set()

        # Mock check_cli_available to return True
        with patch.object(manager, "check_cli_available", return_value=True):
            manager.submit_work(Path("/tmp/test-repo"), callback)

        completion_event.wait(timeout=2.0)

        assert len(callback_result) == 1
        success, result = callback_result[0]
        assert isinstance(success, bool)
        assert isinstance(result, str)

        manager.shutdown()

    def test_callback_invoked_with_failure_when_cli_unavailable(self):
        """AC2: Callback is invoked with failure when CLI unavailable."""
        # Mock subprocess to simulate CLI not available
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            manager = ClaudeCliManager(api_key="test-key", max_workers=1)

            callback_result = []
            completion_event = threading.Event()

            def callback(success: bool, result: str):
                callback_result.append((success, result))
                completion_event.set()

            manager.submit_work(Path("/tmp/test-repo"), callback)
            completion_event.wait(timeout=2.0)

            assert len(callback_result) == 1
            success, result = callback_result[0]
            assert success is False
            assert "not available" in result.lower()

            manager.shutdown()


class TestApiKeySync:
    """Test atomic API key synchronization with file locking."""

    def test_sync_api_key_writes_correct_json(self):
        """AC3: sync_api_key() writes ~/.claude.json with primaryApiKey field."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / ".claude.json"

            manager = ClaudeCliManager(api_key="sk-ant-test-key-12345", max_workers=1)

            # Mock Path.home() to use tmpdir
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                manager.sync_api_key()

            assert json_path.exists()
            config = json.loads(json_path.read_text())
            assert config["primaryApiKey"] == "sk-ant-test-key-12345"

            manager.shutdown()

    def test_sync_api_key_preserves_existing_fields(self):
        """AC3: sync_api_key() preserves existing fields in ~/.claude.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / ".claude.json"

            # Create existing config with other fields
            existing = {
                "primaryApiKey": "old-key",
                "otherField": "value123",
                "nested": {"key": "value"},
            }
            json_path.write_text(json.dumps(existing, indent=2))

            manager = ClaudeCliManager(api_key="new-key", max_workers=1)

            # Mock Path.home() to use tmpdir
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                manager.sync_api_key()

            config = json.loads(json_path.read_text())
            assert config["primaryApiKey"] == "new-key"
            assert config["otherField"] == "value123"
            assert config["nested"] == {"key": "value"}

            manager.shutdown()

    def test_sync_api_key_uses_file_locking(self):
        """AC3: sync_api_key() uses file locking for atomic writes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir) / ".claude.json.lock"

            manager = ClaudeCliManager(api_key="test-key", max_workers=1)

            lock_acquired = []

            # Patch fcntl.flock to track lock acquisition
            original_flock = fcntl.flock

            def tracked_flock(fd, operation):
                lock_acquired.append(operation)
                return original_flock(fd, operation)

            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                with patch("fcntl.flock", side_effect=tracked_flock):
                    manager.sync_api_key()

            # Should acquire exclusive lock then release
            assert fcntl.LOCK_EX in lock_acquired
            assert fcntl.LOCK_UN in lock_acquired

            manager.shutdown()

    def test_sync_api_key_skips_if_no_api_key(self):
        """AC3: sync_api_key() skips if no API key configured."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / ".claude.json"

            manager = ClaudeCliManager(api_key=None, max_workers=1)

            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                manager.sync_api_key()

            # Should not create file if no API key
            assert not json_path.exists()

            manager.shutdown()

    def test_sync_api_key_called_before_cli_invocation(self):
        """AC3: sync_api_key() is called before Claude CLI invocation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sync_called = threading.Event()
            completion_event = threading.Event()

            def callback(success: bool, result: str):
                completion_event.set()

            # Mock Path.home and subprocess to allow full execution
            mock_subprocess = MagicMock()
            mock_subprocess.returncode = 0

            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                with patch("subprocess.run", return_value=mock_subprocess):
                    manager = ClaudeCliManager(api_key="test-key", max_workers=1)

                    original_sync = manager.sync_api_key

                    def tracked_sync():
                        sync_called.set()
                        original_sync()

                    manager.sync_api_key = tracked_sync
                    manager.submit_work(Path("/tmp/test"), callback)
                    completion_event.wait(timeout=2.0)

                    assert sync_called.is_set()

                    manager.shutdown()


class TestCliAvailabilityCheck:
    """Test CLI availability checking with caching."""

    def test_check_cli_available_returns_true_when_installed(self):
        """AC4: check_cli_available() returns True when Claude CLI is installed."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)

        # Mock subprocess.run to simulate CLI installed
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = manager.check_cli_available()

        assert result is True

        manager.shutdown()

    def test_check_cli_available_returns_false_when_not_installed(self):
        """AC4: check_cli_available() returns False when Claude CLI is not installed."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)

        # Mock subprocess.run to simulate CLI not installed
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            result = manager.check_cli_available()

        assert result is False

        manager.shutdown()

    def test_check_cli_available_handles_timeout(self):
        """AC4: check_cli_available() handles subprocess timeout."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("which", 5)):
            result = manager.check_cli_available()

        assert result is False

        manager.shutdown()

    def test_check_cli_available_caches_result(self):
        """AC4: check_cli_available() caches result to avoid repeated checks."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)

        call_count = 0

        def counting_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result

        with patch("subprocess.run", side_effect=counting_run):
            # First call - should execute subprocess
            result1 = manager.check_cli_available()
            assert result1 is True
            assert call_count == 1

            # Second call - should use cache
            result2 = manager.check_cli_available()
            assert result2 is True
            assert call_count == 1  # No additional call

        manager.shutdown()

    def test_check_cli_available_cache_expires_after_ttl(self):
        """AC4: check_cli_available() cache expires after TTL."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=1)
        manager._cli_check_ttl = 0.1  # 100ms TTL for testing

        call_count = 0

        def counting_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            mock_result.returncode = 0
            return mock_result

        with patch("subprocess.run", side_effect=counting_run):
            # First call
            result1 = manager.check_cli_available()
            assert result1 is True
            assert call_count == 1

            # Wait for cache to expire
            time.sleep(0.15)

            # Second call - should execute subprocess again
            result2 = manager.check_cli_available()
            assert result2 is True
            assert call_count == 2

        manager.shutdown()


class TestGracefulShutdown:
    """Test graceful shutdown of worker threads."""

    def test_shutdown_stops_workers_gracefully(self):
        """AC1: shutdown() stops worker threads gracefully."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=3)

        # Verify workers are running
        assert all(t.is_alive() for t in manager._worker_threads)

        # Shutdown
        manager.shutdown(timeout=2.0)

        # Verify workers have stopped
        time.sleep(0.1)  # Small delay to ensure threads complete
        assert all(not t.is_alive() for t in manager._worker_threads)

    def test_shutdown_completes_queued_work(self):
        """shutdown() allows queued work to complete before stopping."""
        # Mock subprocess at module level so it stays active
        mock_subprocess = MagicMock()
        mock_subprocess.returncode = 0

        with patch("subprocess.run", return_value=mock_subprocess):
            manager = ClaudeCliManager(api_key="test-key", max_workers=1)

            results = []
            results_lock = threading.Lock()

            def callback(success: bool, result: str):
                with results_lock:
                    results.append((success, result))

            # Submit work
            for i in range(5):
                manager.submit_work(Path(f"/tmp/repo-{i}"), callback)

            # Shutdown (should complete pending work)
            manager.shutdown(timeout=5.0)

            # All work should have completed
            assert len(results) == 5

    def test_shutdown_sets_shutdown_event(self):
        """shutdown() sets shutdown event to signal workers."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        assert not manager._shutdown_event.is_set()

        manager.shutdown(timeout=1.0)

        assert manager._shutdown_event.is_set()


class TestExternalApiNonBlocking:
    """Test external API non-blocking behavior."""

    def test_submit_work_external_api_returns_immediately(self):
        """AC5: External API endpoints calling submit_work() return immediately."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        # Simulate external API endpoint calling submit_work
        def simulated_api_endpoint():
            start = time.time()
            manager.submit_work(
                Path("/tmp/test"),
                lambda success, result: time.sleep(0.5),  # Slow callback
            )
            elapsed = time.time() - start
            return elapsed

        elapsed = simulated_api_endpoint()

        # Should return immediately (<10ms), not wait for callback
        assert elapsed < 0.01

        manager.shutdown()


class TestConcurrencyControl:
    """Test concurrency control with worker pool."""

    def test_max_workers_limits_concurrent_execution(self):
        """Worker pool limits concurrent CLI invocations to max_workers."""
        manager = ClaudeCliManager(api_key="test-key", max_workers=2)

        active_workers = []
        active_workers_lock = threading.Lock()
        max_concurrent = 0
        completion_event = threading.Event()
        completed_count = 0

        def slow_callback(success: bool, result: str):
            nonlocal completed_count
            with active_workers_lock:
                active_workers.append(threading.current_thread())
                nonlocal max_concurrent
                max_concurrent = max(max_concurrent, len(active_workers))

            time.sleep(0.1)  # Simulate work

            with active_workers_lock:
                active_workers.remove(threading.current_thread())
                completed_count += 1
                if completed_count == 5:
                    completion_event.set()

        # Submit 5 work items
        with patch.object(manager, "check_cli_available", return_value=True):
            for i in range(5):
                manager.submit_work(Path(f"/tmp/repo-{i}"), slow_callback)

        completion_event.wait(timeout=5.0)

        # Should never exceed max_workers (2)
        assert max_concurrent <= 2

        manager.shutdown()


class TestApiKeySyncEdgeCases:
    """Test edge cases in API key synchronization."""

    def test_sync_api_key_handles_invalid_json(self):
        """AC3: sync_api_key() handles invalid JSON in ~/.claude.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / ".claude.json"

            # Create file with invalid JSON
            json_path.write_text("{invalid json content")

            manager = ClaudeCliManager(api_key="new-key", max_workers=1)

            # Mock Path.home() to use tmpdir
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                manager.sync_api_key()

            # Should have overwritten invalid JSON with valid config
            config = json.loads(json_path.read_text())
            assert config["primaryApiKey"] == "new-key"

            manager.shutdown()
