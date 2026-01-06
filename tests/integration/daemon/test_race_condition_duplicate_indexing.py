"""
Stress test for Race Condition #2: TOCTOU in exposed_index.

This test reproduces the race condition where multiple indexing threads
can be started simultaneously due to time-of-check-time-of-use vulnerability.

Race Scenario:
1. Thread A checks indexing_thread.is_alive() - False (passes)
2. Thread A releases indexing_lock_internal
3. Thread B acquires indexing_lock_internal, checks is_alive() - False (passes)
4. Thread B starts indexing thread
5. Thread A acquires cache_lock, invalidates cache
6. Thread A acquires indexing_lock_internal again, starts SECOND indexing thread
7. TWO indexing threads running simultaneously - DUPLICATE INDEXING!

Expected Behavior After Fix:
- Single lock scope covers entire operation
- Only one indexing thread can run at a time
- Second call returns "already_running" status
- No duplicate indexing threads
"""

import threading
import time
from typing import List, Dict, Any, Tuple

import pytest


@pytest.mark.integration
@pytest.mark.daemon
class TestRaceConditionDuplicateIndexing:
    """Test suite for Race Condition #2: TOCTOU in exposed_index."""

    def test_duplicate_indexing_prevention(self, daemon_service_with_project):
        """
        Verify only one indexing thread runs at a time.

        This stress test:
        1. Starts two index calls simultaneously
        2. First should start indexing
        3. Second should return "already_running"
        4. Verifies only ONE indexing thread exists
        """
        service, project_path = daemon_service_with_project

        # Storage for indexing responses
        responses: List[Tuple[int, Dict[str, Any]]] = []
        responses_lock = threading.Lock()

        def start_indexing(call_id: int):
            """Attempt to start indexing."""
            response = service.exposed_index(
                project_path=str(project_path),
                callback=None,
            )
            with responses_lock:
                responses.append((call_id, response))

        # Start two indexing calls simultaneously
        thread1 = threading.Thread(target=start_indexing, args=(1,), daemon=True)
        thread2 = threading.Thread(target=start_indexing, args=(2,), daemon=True)

        thread1.start()
        thread2.start()

        thread1.join(timeout=10)
        thread2.join(timeout=10)

        # Should have exactly 2 responses
        assert len(responses) == 2, f"Expected 2 responses, got {len(responses)}"

        # Extract statuses
        statuses = [resp[1]["status"] for resp in responses]

        # CRITICAL ASSERTION: One should be "started", one should be "already_running"
        started_count = statuses.count("started")
        already_running_count = statuses.count("already_running")

        assert started_count == 1, (
            f"Expected exactly 1 'started' status, got {started_count}. "
            f"Statuses: {statuses}"
        )
        assert already_running_count == 1, (
            f"Expected exactly 1 'already_running' status, got {already_running_count}. "
            f"Statuses: {statuses}"
        )

        # Verify only ONE indexing thread exists
        with service.indexing_lock_internal:
            thread_count = (
                1
                if (service.indexing_thread and service.indexing_thread.is_alive())
                else 0
            )

        assert thread_count == 1, (
            f"Expected exactly 1 indexing thread, got {thread_count}. "
            f"Race condition: duplicate indexing threads detected!"
        )

        # Wait for indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

    def test_sequential_indexing_allowed(self, daemon_service_with_project):
        """
        Verify sequential indexing is allowed after first completes.

        This test:
        1. Starts first indexing operation
        2. Waits for it to complete
        3. Starts second indexing operation
        4. Verifies both succeed without errors
        """
        service, project_path = daemon_service_with_project

        # First indexing operation
        response1 = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )
        assert response1["status"] == "started"

        # Wait for first indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

        # Verify indexing thread is cleared
        with service.indexing_lock_internal:
            assert service.indexing_thread is None, "Indexing thread should be cleared"

        # Second indexing operation should succeed
        response2 = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )
        assert response2["status"] == "started", "Sequential indexing should be allowed"

        # Wait for second indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

    def test_concurrent_indexing_stress(self, daemon_service_with_project):
        """
        Stress test with 10 concurrent indexing attempts.

        This test:
        1. Attempts 10 simultaneous indexing operations
        2. Verifies only 1 succeeds with "started"
        3. Verifies remaining 9 return "already_running"
        4. Confirms no duplicate threads
        """
        service, project_path = daemon_service_with_project

        # Storage for responses
        responses: List[Tuple[int, Dict[str, Any]]] = []
        responses_lock = threading.Lock()

        def attempt_indexing(attempt_id: int):
            """Attempt to start indexing."""
            response = service.exposed_index(
                project_path=str(project_path),
                callback=None,
            )
            with responses_lock:
                responses.append((attempt_id, response))

        # Start 10 concurrent indexing attempts
        threads = []
        for i in range(10):
            thread = threading.Thread(target=attempt_indexing, args=(i,), daemon=True)
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=10)

        # Should have 10 responses
        assert len(responses) == 10, f"Expected 10 responses, got {len(responses)}"

        # Extract statuses
        statuses = [resp[1]["status"] for resp in responses]
        started_count = statuses.count("started")
        already_running_count = statuses.count("already_running")

        # CRITICAL ASSERTION: Exactly 1 "started", rest "already_running"
        assert started_count == 1, (
            f"Race condition detected! Expected 1 'started' status, got {started_count}. "
            f"Multiple indexing threads may have started!"
        )
        assert (
            already_running_count == 9
        ), f"Expected 9 'already_running' statuses, got {already_running_count}."

        # Verify only ONE indexing thread exists
        with service.indexing_lock_internal:
            thread_exists = (
                service.indexing_thread is not None
                and service.indexing_thread.is_alive()
            )

        assert thread_exists, "One indexing thread should be running"

        # Wait for indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

    def test_indexing_state_cleanup_on_completion(self, daemon_service_with_project):
        """
        Verify indexing state is properly cleaned up after completion.

        This test:
        1. Starts indexing operation
        2. Waits for completion
        3. Verifies indexing_thread is cleared
        4. Verifies indexing_project_path is cleared
        5. Verifies new indexing can start
        """
        service, project_path = daemon_service_with_project

        # Start indexing
        response = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )
        assert response["status"] == "started"

        # Wait for completion
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

        # Give cleanup time to run
        time.sleep(0.1)

        # Verify state is cleaned up
        with service.indexing_lock_internal:
            assert service.indexing_thread is None, "indexing_thread should be None"
            assert (
                service.indexing_project_path is None
            ), "indexing_project_path should be None"

        # Verify new indexing can start
        response2 = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )
        assert (
            response2["status"] == "started"
        ), "New indexing should be allowed after cleanup"

        # Wait for second indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)
