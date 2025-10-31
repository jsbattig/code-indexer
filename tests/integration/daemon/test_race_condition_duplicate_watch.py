"""
Stress test for Race Condition #3: Unsynchronized Watch State.

This test reproduces the race condition where multiple watch handlers
can be started simultaneously due to unsynchronized state access.

Race Scenario:
1. Thread A checks watch_thread.is_alive() - False (passes) NO LOCK
2. Thread B checks watch_thread.is_alive() - False (passes) NO LOCK
3. Thread A starts watch handler, sets self.watch_handler
4. Thread B starts watch handler, OVERWRITES self.watch_handler
5. TWO watch handlers running, file events processed multiple times

Expected Behavior After Fix:
- All watch state access protected by cache_lock
- Only one watch handler can run at a time
- Second call returns "already running" error
- No duplicate watch handlers
"""

import threading
import time
from typing import List, Dict, Any

import pytest


@pytest.mark.integration
@pytest.mark.daemon
class TestRaceConditionDuplicateWatch:
    """Test suite for Race Condition #3: Unsynchronized Watch State."""

    def test_duplicate_watch_prevention(self, daemon_service_with_project):
        """
        Verify only one watch handler runs at a time.

        This stress test:
        1. Starts two watch calls simultaneously
        2. First should start watching
        3. Second should return "already running" error
        4. Verifies only ONE watch thread exists
        """
        service, project_path = daemon_service_with_project

        # Storage for watch responses
        responses: List[Dict[str, Any]] = []
        responses_lock = threading.Lock()

        def start_watch(call_id: int):
            """Attempt to start watch."""
            response = service.exposed_watch_start(
                project_path=str(project_path),
                callback=None,
                debounce_seconds=1.0,
            )
            with responses_lock:
                responses.append((call_id, response))

        # Start two watch calls simultaneously
        thread1 = threading.Thread(target=start_watch, args=(1,), daemon=True)
        thread2 = threading.Thread(target=start_watch, args=(2,), daemon=True)

        thread1.start()
        thread2.start()

        thread1.join(timeout=10)
        thread2.join(timeout=10)

        # Should have exactly 2 responses
        assert len(responses) == 2, f"Expected 2 responses, got {len(responses)}"

        # Extract statuses
        statuses = [resp[1]["status"] for resp in responses]

        # CRITICAL ASSERTION: One should be "success", one should be "error" (already running)
        success_count = statuses.count("success")
        error_count = statuses.count("error")

        assert success_count == 1, (
            f"Expected exactly 1 'success' status, got {success_count}. "
            f"Statuses: {statuses}. "
            f"Race condition: multiple watch handlers may have started!"
        )
        assert error_count == 1, (
            f"Expected exactly 1 'error' status, got {error_count}. "
            f"Statuses: {statuses}"
        )

        # Verify error message is "Watch already running"
        error_response = next(resp[1] for resp in responses if resp[1]["status"] == "error")
        assert "already running" in error_response.get("message", "").lower(), (
            f"Error message should indicate 'already running', got: {error_response.get('message')}"
        )

        # Verify only ONE watch handler exists
        assert service.watch_handler is not None, "Watch handler should exist"
        assert service.watch_thread is not None, "Watch thread should exist"
        assert service.watch_thread.is_alive(), "Watch thread should be alive"

        # Stop watch
        service.exposed_watch_stop(str(project_path))

    def test_watch_status_synchronization(self, daemon_service_with_project):
        """
        Verify watch status is properly synchronized.

        This test:
        1. Checks status before watch starts (should be not running)
        2. Starts watch
        3. Checks status during watch (should be running)
        4. Stops watch
        5. Checks status after stop (should be not running)
        """
        service, project_path = daemon_service_with_project

        # Status before watch starts
        status1 = service.exposed_watch_status()
        assert not status1["running"], "Watch should not be running initially"

        # Start watch
        response = service.exposed_watch_start(
            project_path=str(project_path),
            callback=None,
            debounce_seconds=1.0,
        )
        assert response["status"] == "success", "Watch start should succeed"

        # Status during watch
        status2 = service.exposed_watch_status()
        assert status2["running"], "Watch should be running"
        assert status2["project_path"] == str(project_path), "Project path should match"

        # Stop watch
        stop_response = service.exposed_watch_stop(str(project_path))
        assert stop_response["status"] == "success", "Watch stop should succeed"

        # Status after stop
        status3 = service.exposed_watch_status()
        assert not status3["running"], "Watch should not be running after stop"

    def test_concurrent_watch_stress(self, daemon_service_with_project):
        """
        Stress test with 10 concurrent watch start attempts.

        This test:
        1. Attempts 10 simultaneous watch starts
        2. Verifies only 1 succeeds with "success"
        3. Verifies remaining 9 return "error" (already running)
        4. Confirms no duplicate watch handlers
        """
        service, project_path = daemon_service_with_project

        # Storage for responses
        responses: List[Dict[str, Any]] = []
        responses_lock = threading.Lock()

        def attempt_watch(attempt_id: int):
            """Attempt to start watch."""
            response = service.exposed_watch_start(
                project_path=str(project_path),
                callback=None,
                debounce_seconds=1.0,
            )
            with responses_lock:
                responses.append((attempt_id, response))

        # Start 10 concurrent watch attempts
        threads = []
        for i in range(10):
            thread = threading.Thread(target=attempt_watch, args=(i,), daemon=True)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=10)

        # Should have 10 responses
        assert len(responses) == 10, f"Expected 10 responses, got {len(responses)}"

        # Extract statuses
        statuses = [resp[1]["status"] for resp in responses]
        success_count = statuses.count("success")
        error_count = statuses.count("error")

        # CRITICAL ASSERTION: Exactly 1 "success", rest "error"
        assert success_count == 1, (
            f"Race condition detected! Expected 1 'success' status, got {success_count}. "
            f"Multiple watch handlers may have started!"
        )
        assert error_count == 9, (
            f"Expected 9 'error' statuses, got {error_count}."
        )

        # Verify only ONE watch handler exists
        assert service.watch_handler is not None, "One watch handler should exist"
        assert service.watch_thread is not None and service.watch_thread.is_alive(), (
            "One watch thread should be running"
        )

        # Stop watch
        service.exposed_watch_stop(str(project_path))

    def test_watch_state_cleanup_on_stop(self, daemon_service_with_project):
        """
        Verify watch state is properly cleaned up after stop.

        This test:
        1. Starts watch operation
        2. Stops watch
        3. Verifies watch_handler is cleared
        4. Verifies watch_thread is cleared
        5. Verifies watch_project_path is cleared
        6. Verifies new watch can start
        """
        service, project_path = daemon_service_with_project

        # Start watch
        response = service.exposed_watch_start(
            project_path=str(project_path),
            callback=None,
            debounce_seconds=1.0,
        )
        assert response["status"] == "success"

        # Stop watch
        stop_response = service.exposed_watch_stop(str(project_path))
        assert stop_response["status"] == "success"

        # Give cleanup time to run
        time.sleep(0.2)

        # Verify state is cleaned up
        assert service.watch_handler is None, "watch_handler should be None"
        assert service.watch_thread is None, "watch_thread should be None"
        assert service.watch_project_path is None, "watch_project_path should be None"

        # Verify new watch can start
        response2 = service.exposed_watch_start(
            project_path=str(project_path),
            callback=None,
            debounce_seconds=1.0,
        )
        assert response2["status"] == "success", "New watch should be allowed after cleanup"

        # Stop second watch
        service.exposed_watch_stop(str(project_path))

    def test_watch_stop_on_non_running_watch(self, daemon_service_with_project):
        """
        Verify watch stop handles non-running watch gracefully.

        This test:
        1. Attempts to stop watch when no watch is running
        2. Verifies error is returned
        3. Ensures no crashes occur
        """
        service, project_path = daemon_service_with_project

        # Ensure no watch is running
        if service.watch_handler:
            service.exposed_watch_stop(str(project_path))
            time.sleep(0.1)

        # Attempt to stop non-running watch
        response = service.exposed_watch_stop(str(project_path))

        # Should return error (not crash)
        assert response["status"] == "error", "Should return error for non-running watch"
        assert "no watch running" in response.get("message", "").lower(), (
            f"Error message should indicate no watch running, got: {response.get('message')}"
        )
