"""
Tests for scheduler Event signaling (Story #620, Priority 3B).

Validates that RefreshScheduler uses threading.Event instead of time.sleep() polling:
- stop() interrupts wait immediately
- No CPU polling (Event-based wait)
- Graceful shutdown with fast response time

These tests verify AC3B: Event signaling eliminates busy-wait CPU polling.
"""

import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_indexer.global_repos.cleanup_manager import CleanupManager
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.refresh_scheduler import RefreshScheduler


class TestSchedulerEventSignaling:
    """Test scheduler Event signaling for efficient wait/wake."""

    @pytest.fixture
    def scheduler_setup(self, tmp_path: Path):
        """Create scheduler instance with mocked dependencies."""
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal registry file
        registry_file = golden_repos_dir / "global-repos.json"
        registry_file.write_text("{}")

        # Create mock config source (30 second interval for testing)
        config_source = Mock()
        config_source.get_global_refresh_interval.return_value = 30

        # Create mocks
        query_tracker = Mock(spec=QueryTracker)
        cleanup_manager = Mock(spec=CleanupManager)

        scheduler = RefreshScheduler(
            golden_repos_dir=str(golden_repos_dir),
            config_source=config_source,
            query_tracker=query_tracker,
            cleanup_manager=cleanup_manager,
        )

        return scheduler

    def test_stop_interrupts_wait(self, scheduler_setup: RefreshScheduler):
        """
        Test that stop() interrupts sleep immediately instead of waiting.

        Story #620, AC3B: Event.wait() allows stop() to signal wake.
        Expected behavior: stop() completes in <1 second even with 30s interval.
        """
        scheduler = scheduler_setup

        # Start scheduler (30 second interval)
        scheduler.start()
        assert scheduler.is_running()

        # Wait a bit to ensure scheduler enters wait loop
        time.sleep(0.5)

        # Measure stop time
        start_time = time.time()
        scheduler.stop()
        stop_duration = time.time() - start_time

        # Verify stop completed quickly (not 30 seconds)
        # Should complete in <1 second with Event signaling
        assert (
            stop_duration < 1.0
        ), f"stop() took {stop_duration:.2f}s, expected <1s with Event signaling"

        assert not scheduler.is_running()

    def test_no_cpu_polling(self, scheduler_setup: RefreshScheduler):
        """
        Test that scheduler uses Event.wait() instead of CPU polling.

        Story #620, AC3B: Event-based wait instead of sleep+check loops.
        Verifies implementation uses threading.Event for wait.
        """
        scheduler = scheduler_setup

        # Verify scheduler has _stop_event attribute (Event-based implementation)
        assert hasattr(
            scheduler, "_stop_event"
        ), "Scheduler must have _stop_event threading.Event"

        # Verify it's a threading.Event instance
        assert isinstance(
            scheduler._stop_event, threading.Event
        ), "_stop_event must be a threading.Event instance"

        # Start scheduler
        scheduler.start()
        time.sleep(0.5)

        # Verify event is not set while running
        assert (
            not scheduler._stop_event.is_set()
        ), "Event should not be set while running"

        # Stop scheduler
        scheduler.stop()

        # Verify event was set during stop
        assert scheduler._stop_event.is_set(), "Event should be set after stop()"

    def test_graceful_shutdown(self, scheduler_setup: RefreshScheduler):
        """
        Test that scheduler shuts down gracefully with Event signaling.

        Story #620, AC3B: Fast, responsive shutdown using Event.
        """
        scheduler = scheduler_setup

        # Start scheduler
        scheduler.start()
        assert scheduler.is_running()

        # Let scheduler run for a bit
        time.sleep(1.0)

        # Stop and verify thread terminates quickly
        start_time = time.time()
        scheduler.stop()
        shutdown_time = time.time() - start_time

        # Verify graceful shutdown
        assert not scheduler.is_running()
        assert scheduler._thread is None or not scheduler._thread.is_alive()

        # Shutdown should be fast (<1s)
        assert shutdown_time < 1.0, f"Shutdown took {shutdown_time:.2f}s, expected <1s"
