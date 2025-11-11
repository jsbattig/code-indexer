"""Unit tests for TTL eviction thread.

Tests TTL-based cache eviction, auto-shutdown on idle, and background thread behavior.
"""

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


class TestTTLEvictionThreadInitialization:
    """Test TTL eviction thread initialization."""

    def test_ttl_eviction_thread_initializes(self):
        """Test TTL eviction thread initializes with daemon service."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        thread = TTLEvictionThread(mock_service, check_interval=60)

        assert thread.daemon_service is mock_service
        assert thread.check_interval == 60
        assert thread.running is True
        assert thread.daemon is True  # Thread should be daemon thread

    def test_ttl_eviction_thread_custom_check_interval(self):
        """Test TTL eviction thread accepts custom check interval."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        thread = TTLEvictionThread(mock_service, check_interval=30)

        assert thread.check_interval == 30

    def test_ttl_eviction_thread_inherits_from_threading_thread(self):
        """Test TTL eviction thread inherits from threading.Thread."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        thread = TTLEvictionThread(mock_service)

        assert isinstance(thread, threading.Thread)


class TestTTLEvictionBasicBehavior:
    """Test basic TTL eviction behavior."""

    def test_check_and_evict_does_nothing_with_no_cache(self):
        """Test _check_and_evict does nothing when cache is None."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = None
        mock_service.cache_lock = threading.Lock()

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Should complete without errors, cache remains None
        assert mock_service.cache_entry is None

    def test_check_and_evict_preserves_fresh_cache(self):
        """Test _check_and_evict preserves cache that hasn't expired."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        fresh_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=10)
        mock_service.cache_entry = fresh_entry
        mock_service.cache_lock = threading.Lock()
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Fresh cache should be preserved
        assert mock_service.cache_entry is fresh_entry

    def test_check_and_evict_removes_expired_cache(self):
        """Test _check_and_evict removes expired cache entry."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        expired_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)
        # Backdate to simulate expiration
        expired_entry.last_accessed = datetime.now() - timedelta(minutes=2)
        mock_service.cache_entry = expired_entry
        mock_service.cache_lock = threading.Lock()
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Expired cache should be evicted
        assert mock_service.cache_entry is None


class TestTTLEvictionAutoShutdown:
    """Test auto-shutdown behavior on idle."""

    def test_should_shutdown_returns_false_with_active_cache(self):
        """Test _should_shutdown returns False when cache is active."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = CacheEntry(Path("/tmp/test"))
        mock_service.config = Mock(auto_shutdown_on_idle=True)

        thread = TTLEvictionThread(mock_service)

        assert thread._should_shutdown() is False

    def test_should_shutdown_returns_false_when_auto_shutdown_disabled(self):
        """Test _should_shutdown returns False when auto-shutdown is disabled."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = None
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        thread = TTLEvictionThread(mock_service)

        assert thread._should_shutdown() is False

    def test_should_shutdown_returns_true_when_idle_and_enabled(self):
        """Test _should_shutdown returns True when idle with auto-shutdown enabled."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = None
        mock_service.config = Mock(auto_shutdown_on_idle=True)

        thread = TTLEvictionThread(mock_service)

        assert thread._should_shutdown() is True

    @patch("os._exit")
    def test_check_and_evict_triggers_shutdown_on_expired_idle(self, mock_exit):
        """Test _check_and_evict triggers shutdown when cache expires and auto-shutdown enabled."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        expired_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)
        expired_entry.last_accessed = datetime.now() - timedelta(minutes=2)
        mock_service.cache_entry = expired_entry
        mock_service.cache_lock = threading.Lock()
        mock_service.config = Mock(auto_shutdown_on_idle=True)

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Cache should be evicted and shutdown triggered
        assert mock_service.cache_entry is None
        mock_exit.assert_called_once_with(0)

    @patch("os._exit")
    def test_check_and_evict_no_shutdown_when_disabled(self, mock_exit):
        """Test _check_and_evict does not shutdown when auto-shutdown disabled."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        expired_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)
        expired_entry.last_accessed = datetime.now() - timedelta(minutes=2)
        mock_service.cache_entry = expired_entry
        mock_service.cache_lock = threading.Lock()
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Cache should be evicted but no shutdown
        assert mock_service.cache_entry is None
        mock_exit.assert_not_called()


class TestTTLEvictionThreadLifecycle:
    """Test TTL eviction thread lifecycle management."""

    def test_stop_sets_running_to_false(self):
        """Test stop() sets running flag to False."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        thread = TTLEvictionThread(mock_service)

        assert thread.running is True
        thread.stop()
        assert thread.running is False

    def test_run_loop_exits_when_stopped(self):
        """Test run loop exits when running is set to False."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = None
        mock_service.cache_lock = threading.Lock()

        thread = TTLEvictionThread(mock_service, check_interval=0.01)

        # Start thread
        thread.start()

        # Give it a moment to run
        time.sleep(0.05)

        # Stop thread
        thread.stop()

        # Thread should exit shortly
        thread.join(timeout=1.0)
        assert not thread.is_alive()

    @patch("time.sleep")
    def test_run_loop_sleeps_between_checks(self, mock_sleep):
        """Test run loop sleeps for check_interval between eviction checks."""
        from code_indexer.daemon.cache import TTLEvictionThread

        mock_service = Mock()
        mock_service.cache_entry = None
        mock_service.cache_lock = threading.Lock()

        # Mock sleep to prevent actual waiting and stop after first iteration
        def stop_after_sleep(duration):
            thread.running = False

        mock_sleep.side_effect = stop_after_sleep

        thread = TTLEvictionThread(mock_service, check_interval=60)
        thread.run()

        # Should have slept for check_interval
        mock_sleep.assert_called_once_with(60)


class TestTTLEvictionConcurrency:
    """Test TTL eviction thread concurrency and locking."""

    def test_check_and_evict_acquires_cache_lock(self):
        """Test _check_and_evict acquires cache lock before eviction."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        expired_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)
        expired_entry.last_accessed = datetime.now() - timedelta(minutes=2)
        mock_service.cache_entry = expired_entry

        # Track lock acquisition
        lock_acquired = []
        original_lock = threading.Lock()

        class TrackedLock:
            def __enter__(self):
                lock_acquired.append(True)
                return original_lock.__enter__()

            def __exit__(self, *args):
                return original_lock.__exit__(*args)

        mock_service.cache_lock = TrackedLock()
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        thread = TTLEvictionThread(mock_service)
        thread._check_and_evict()

        # Lock should have been acquired
        assert len(lock_acquired) == 1

    def test_eviction_thread_safe_with_concurrent_access(self):
        """Test eviction thread is safe with concurrent cache access."""
        from code_indexer.daemon.cache import CacheEntry, TTLEvictionThread

        mock_service = Mock()
        cache_entry = CacheEntry(Path("/tmp/test"), ttl_minutes=1)
        mock_service.cache_entry = cache_entry
        mock_service.cache_lock = threading.Lock()
        mock_service.config = Mock(auto_shutdown_on_idle=False)

        # Simulate concurrent access
        access_errors = []

        def concurrent_access():
            """Simulate concurrent cache access."""
            try:
                with mock_service.cache_lock:
                    if mock_service.cache_entry:
                        mock_service.cache_entry.update_access()
            except Exception as e:
                access_errors.append(e)

        # Start eviction thread
        thread = TTLEvictionThread(mock_service, check_interval=0.01)
        thread.start()

        # Simulate concurrent access
        access_thread = threading.Thread(target=concurrent_access)
        access_thread.start()
        access_thread.join()

        # Stop eviction thread
        thread.stop()
        thread.join(timeout=1.0)

        # No errors should have occurred
        assert len(access_errors) == 0
