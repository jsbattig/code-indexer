"""
Stress test for Race Condition #1: Query/Indexing Cache Race.

This test reproduces the race condition where queries fail with NoneType errors
when cache is invalidated during query execution.

Race Scenario:
1. Query thread calls _ensure_cache_loaded() - cache loaded
2. Query thread releases cache_lock
3. Indexing thread calls exposed_index() - sets cache_entry = None
4. Query thread calls _execute_semantic_search() - CRASH (cache is None)

Expected Behavior After Fix:
- Queries hold cache_lock during entire execution
- Cache invalidation waits for queries to complete
- No NoneType errors during concurrent operations
"""

import threading
import time
from typing import List, Any, Tuple

import pytest


@pytest.mark.integration
@pytest.mark.daemon
class TestRaceConditionQueryIndexing:
    """Test suite for Race Condition #1: Query/Indexing Cache Race."""

    def test_concurrent_query_during_indexing(self, daemon_service_with_project):
        """
        Verify queries work while indexing runs without NoneType crashes.

        This stress test:
        1. Loads cache with initial query
        2. Starts indexing in background (invalidates cache)
        3. Runs 10 concurrent queries immediately
        4. All queries should succeed without NoneType errors
        """
        service, project_path = daemon_service_with_project

        # Initial query to load cache
        initial_results = service.exposed_query(
            project_path=str(project_path),
            query="test function",
            limit=5,
        )
        assert len(initial_results) > 0, "Initial query should return results"

        # Verify cache is loaded
        assert service.cache_entry is not None, "Cache should be loaded"

        # Storage for query results and errors
        query_results: List[Any] = []
        query_errors: List[Tuple[int, Exception]] = []
        query_lock = threading.Lock()

        def run_query(query_id: int):
            """Execute query and store results/errors."""
            try:
                results = service.exposed_query(
                    project_path=str(project_path),
                    query=f"test query {query_id}",
                    limit=5,
                )
                with query_lock:
                    query_results.append((query_id, results))
            except Exception as e:
                with query_lock:
                    query_errors.append((query_id, e))

        # Start indexing in background (this invalidates cache)
        indexing_response = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )
        assert indexing_response["status"] in ["started", "already_running"]

        # Immediately run 10 concurrent queries (race window!)
        query_threads = []
        for i in range(10):
            thread = threading.Thread(target=run_query, args=(i,), daemon=True)
            query_threads.append(thread)
            thread.start()

        # Wait for all queries to complete
        for thread in query_threads:
            thread.join(timeout=10)

        # CRITICAL ASSERTION: No NoneType errors should occur
        if query_errors:
            error_messages = [f"Query {qid}: {str(e)}" for qid, e in query_errors]
            pytest.fail(
                f"Race condition detected! {len(query_errors)}/10 queries failed:\n"
                + "\n".join(error_messages)
            )

        # All queries should succeed
        assert (
            len(query_results) == 10
        ), f"Expected 10 successful queries, got {len(query_results)}"

        # Wait for indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

    def test_cache_invalidation_during_query(self, daemon_service_with_project):
        """
        Verify cache invalidation doesn't crash in-progress queries.

        This test:
        1. Starts a slow query (holds cache lock)
        2. Attempts to invalidate cache via indexing
        3. Verifies query completes successfully
        4. Verifies indexing waits for query to complete
        """
        service, project_path = daemon_service_with_project

        # Load cache with initial query
        service.exposed_query(
            project_path=str(project_path),
            query="initial",
            limit=5,
        )
        assert service.cache_entry is not None

        query_completed = threading.Event()
        query_error = None

        def slow_query():
            """Execute query that simulates slow execution."""
            nonlocal query_error
            try:
                # This query should hold cache lock and complete successfully
                results = service.exposed_query(
                    project_path=str(project_path),
                    query="slow query test",
                    limit=10,
                )
                assert results is not None, "Query should return results"
                query_completed.set()
            except Exception as e:
                query_error = e
                query_completed.set()

        # Start slow query
        query_thread = threading.Thread(target=slow_query, daemon=True)
        query_thread.start()

        # Immediately attempt to invalidate cache via indexing
        time.sleep(0.01)  # Small delay to ensure query starts
        indexing_response = service.exposed_index(
            project_path=str(project_path),
            callback=None,
        )

        # Wait for query to complete
        query_thread.join(timeout=10)

        # Query should complete successfully
        assert query_completed.is_set(), "Query should complete"
        if query_error:
            pytest.fail(f"Query failed during cache invalidation: {query_error}")

        # Indexing should have started or be running
        assert indexing_response["status"] in ["started", "already_running"]

        # Wait for indexing to complete
        if service.indexing_thread:
            service.indexing_thread.join(timeout=30)

    def test_rapid_query_invalidation_cycles(self, daemon_service_with_project):
        """
        Stress test with rapid query-invalidation cycles.

        This test:
        1. Runs queries and invalidations in rapid succession
        2. Verifies no race conditions occur
        3. Ensures cache coherence throughout
        """
        service, project_path = daemon_service_with_project

        errors: List[Exception] = []
        errors_lock = threading.Lock()

        def query_loop():
            """Execute queries in a loop."""
            for i in range(5):
                try:
                    service.exposed_query(
                        project_path=str(project_path),
                        query=f"rapid query {i}",
                        limit=3,
                    )
                    time.sleep(0.01)
                except Exception as e:
                    with errors_lock:
                        errors.append(e)

        def invalidate_loop():
            """Invalidate cache in a loop."""
            for _ in range(5):
                try:
                    with service.cache_lock:
                        if service.cache_entry:
                            service.cache_entry = None
                    time.sleep(0.01)
                except Exception as e:
                    with errors_lock:
                        errors.append(e)

        # Run concurrent query and invalidation loops
        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=query_loop, daemon=True))
        for _ in range(2):
            threads.append(threading.Thread(target=invalidate_loop, daemon=True))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=15)

        # No race conditions should occur
        if errors:
            error_messages = [str(e) for e in errors]
            pytest.fail(
                "Race conditions detected in rapid cycles:\n"
                + "\n".join(error_messages)
            )
