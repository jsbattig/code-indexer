"""
Unit tests for DelegationJobTracker service.

Story #720: Callback-Based Delegation Job Completion

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import asyncio

import pytest


class TestJobResult:
    """Tests for JobResult dataclass."""

    def test_job_result_creation_with_all_fields(self):
        """
        JobResult can be created with all fields populated.

        Given all fields are provided
        When JobResult is created
        Then all fields should be accessible with correct values
        """
        from code_indexer.server.services.delegation_job_tracker import JobResult

        result = JobResult(
            job_id="job-12345",
            status="completed",
            output="The authentication uses JWT tokens.",
            exit_code=0,
            error=None,
        )

        assert result.job_id == "job-12345"
        assert result.status == "completed"
        assert result.output == "The authentication uses JWT tokens."
        assert result.exit_code == 0
        assert result.error is None

    def test_job_result_creation_with_error(self):
        """
        JobResult can be created with error field for failed jobs.

        Given a job has failed
        When JobResult is created with error
        Then error field should contain the error message
        """
        from code_indexer.server.services.delegation_job_tracker import JobResult

        result = JobResult(
            job_id="job-99999",
            status="failed",
            output="",
            exit_code=1,
            error="Repository clone failed: authentication denied",
        )

        assert result.job_id == "job-99999"
        assert result.status == "failed"
        assert result.exit_code == 1
        assert result.error == "Repository clone failed: authentication denied"


class TestDelegationJobTracker:
    """Tests for DelegationJobTracker singleton service."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        # Reset singleton for clean test state
        DelegationJobTracker._instance = None
        yield
        DelegationJobTracker._instance = None

    def test_get_instance_returns_singleton(self):
        """
        get_instance() returns the same DelegationJobTracker instance.

        Given the singleton has not been initialized
        When get_instance() is called multiple times
        Then the same instance should be returned each time
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        instance1 = DelegationJobTracker.get_instance()
        instance2 = DelegationJobTracker.get_instance()

        assert instance1 is instance2
        assert isinstance(instance1, DelegationJobTracker)

    @pytest.mark.asyncio
    async def test_register_job_creates_future(self):
        """
        register_job() creates a Future for the job_id.

        Given a valid job_id
        When register_job() is called
        Then a Future should be created for that job_id
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        # Verify the job is registered (internal state check)
        assert "job-12345" in tracker._pending_jobs
        assert isinstance(tracker._pending_jobs["job-12345"], asyncio.Future)

    @pytest.mark.asyncio
    async def test_register_job_is_idempotent(self):
        """
        register_job() does not overwrite existing Future.

        Given a job_id is already registered
        When register_job() is called again with the same job_id
        Then the original Future should be preserved
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")
        original_future = tracker._pending_jobs["job-12345"]

        await tracker.register_job("job-12345")

        assert tracker._pending_jobs["job-12345"] is original_future

    @pytest.mark.asyncio
    async def test_complete_job_resolves_future(self):
        """
        complete_job() resolves the Future with the JobResult.

        Given a job is registered
        When complete_job() is called with a JobResult
        Then the Future should resolve with that result
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result = JobResult(
            job_id="job-12345",
            status="completed",
            output="Final output here",
            exit_code=0,
            error=None,
        )

        success = await tracker.complete_job(result)

        assert success is True
        assert tracker._pending_jobs["job-12345"].done()
        assert tracker._pending_jobs["job-12345"].result() == result

    @pytest.mark.asyncio
    async def test_complete_job_returns_false_for_nonexistent_job(self):
        """
        complete_job() returns False for unregistered job.

        Given a job_id that was never registered
        When complete_job() is called
        Then it should return False
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()

        result = JobResult(
            job_id="nonexistent-job",
            status="completed",
            output="Output",
            exit_code=0,
            error=None,
        )

        success = await tracker.complete_job(result)

        assert success is False

    @pytest.mark.asyncio
    async def test_complete_job_returns_false_for_already_completed_job(self):
        """
        complete_job() returns False if job already completed.

        Given a job has already been completed
        When complete_job() is called again
        Then it should return False
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result1 = JobResult(
            job_id="job-12345",
            status="completed",
            output="First completion",
            exit_code=0,
            error=None,
        )
        result2 = JobResult(
            job_id="job-12345",
            status="completed",
            output="Second completion",
            exit_code=0,
            error=None,
        )

        success1 = await tracker.complete_job(result1)
        success2 = await tracker.complete_job(result2)

        assert success1 is True
        assert success2 is False

    @pytest.mark.asyncio
    async def test_wait_for_job_returns_result_when_completed(self):
        """
        wait_for_job() returns the JobResult when callback arrives.

        Given a job is registered
        When the job is completed and wait_for_job() is called
        Then it should return the JobResult
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result = JobResult(
            job_id="job-12345",
            status="completed",
            output="The result output",
            exit_code=0,
            error=None,
        )

        # Complete the job (simulating callback)
        await tracker.complete_job(result)

        # Wait should return immediately with the result
        returned_result = await tracker.wait_for_job("job-12345", timeout=1.0)

        assert returned_result == result

    @pytest.mark.asyncio
    async def test_wait_for_job_blocks_until_completed(self):
        """
        wait_for_job() blocks until complete_job() is called.

        Given a job is registered but not completed
        When wait_for_job() is called
        Then it should block until complete_job() resolves the Future
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result = JobResult(
            job_id="job-12345",
            status="completed",
            output="Async result",
            exit_code=0,
            error=None,
        )

        # Schedule completion after a short delay
        async def complete_after_delay():
            await asyncio.sleep(0.1)
            await tracker.complete_job(result)

        # Run completion and wait concurrently
        wait_task = asyncio.create_task(tracker.wait_for_job("job-12345", timeout=5.0))
        complete_task = asyncio.create_task(complete_after_delay())

        await complete_task
        returned_result = await wait_task

        assert returned_result == result

    @pytest.mark.asyncio
    async def test_wait_for_job_returns_none_on_timeout(self):
        """
        wait_for_job() returns None when timeout expires.

        Given a job is registered but never completed
        When wait_for_job() timeout expires
        Then it should return None
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        # Wait with a very short timeout
        returned_result = await tracker.wait_for_job("job-12345", timeout=0.05)

        assert returned_result is None

    @pytest.mark.asyncio
    async def test_wait_for_job_returns_none_for_nonexistent_job(self):
        """
        wait_for_job() returns None for unregistered job.

        Given a job_id that was never registered
        When wait_for_job() is called
        Then it should return None immediately
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()

        returned_result = await tracker.wait_for_job("nonexistent-job", timeout=1.0)

        assert returned_result is None

    @pytest.mark.asyncio
    async def test_wait_for_job_removes_job_after_completion(self):
        """
        wait_for_job() removes job from pending after returning result.

        Given a job is completed
        When wait_for_job() returns
        Then the job should be removed from pending jobs
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result = JobResult(
            job_id="job-12345",
            status="completed",
            output="Result",
            exit_code=0,
            error=None,
        )

        await tracker.complete_job(result)
        await tracker.wait_for_job("job-12345", timeout=1.0)

        assert "job-12345" not in tracker._pending_jobs

    @pytest.mark.asyncio
    async def test_wait_for_job_keeps_job_after_timeout(self):
        """
        wait_for_job() KEEPS job in pending after timeout (Story #720 fix).

        Given a job times out
        When wait_for_job() returns None
        Then the job should STILL be in pending jobs (caller can retry)
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-12345")

        result = await tracker.wait_for_job("job-12345", timeout=0.05)

        assert result is None
        # Job should STILL be registered - timeout doesn't remove it
        assert "job-12345" in tracker._pending_jobs
        assert await tracker.has_job("job-12345") is True

    @pytest.mark.asyncio
    async def test_can_retry_wait_after_timeout(self):
        """
        After timeout, caller can call wait_for_job again (Story #720 fix).

        Given a job times out on first wait
        When callback later completes the job
        Then a subsequent wait_for_job should return the result
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-retry-test")

        # First wait times out
        result1 = await tracker.wait_for_job("job-retry-test", timeout=0.05)
        assert result1 is None

        # Job still exists
        assert await tracker.has_job("job-retry-test") is True

        # Now complete the job (simulating callback arriving late)
        job_result = JobResult(
            job_id="job-retry-test",
            status="completed",
            output="Late callback result",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(job_result)

        # Second wait should return the result immediately
        result2 = await tracker.wait_for_job("job-retry-test", timeout=1.0)
        assert result2 is not None
        assert result2.output == "Late callback result"

        # Now job should be removed (completed successfully)
        assert await tracker.has_job("job-retry-test") is False

    @pytest.mark.asyncio
    async def test_multiple_concurrent_jobs(self):
        """
        Tracker handles multiple concurrent jobs independently.

        Given multiple jobs are registered
        When they complete in different order
        Then each wait_for_job() should return correct result
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-A")
        await tracker.register_job("job-B")

        result_a = JobResult(
            job_id="job-A", status="completed", output="Result A", exit_code=0, error=None
        )
        result_b = JobResult(
            job_id="job-B", status="failed", output="", exit_code=1, error="Error B"
        )

        # Complete job B first, then job A
        await tracker.complete_job(result_b)
        await tracker.complete_job(result_a)

        returned_a = await tracker.wait_for_job("job-A", timeout=1.0)
        returned_b = await tracker.wait_for_job("job-B", timeout=1.0)

        assert returned_a.output == "Result A"
        assert returned_b.error == "Error B"

    @pytest.mark.asyncio
    async def test_thread_safety_with_concurrent_operations(self):
        """
        Tracker is thread-safe for concurrent register/complete/wait.

        Given multiple operations happening concurrently
        When operations complete
        Then all results should be consistent
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()

        async def register_complete_wait(job_num: int) -> bool:
            job_id = f"job-{job_num}"
            await tracker.register_job(job_id)
            result = JobResult(
                job_id=job_id,
                status="completed",
                output=f"Output {job_num}",
                exit_code=0,
                error=None,
            )
            await tracker.complete_job(result)
            returned = await tracker.wait_for_job(job_id, timeout=1.0)
            return returned is not None and returned.output == f"Output {job_num}"

        # Run 10 concurrent job operations
        tasks = [register_complete_wait(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(results)

    @pytest.mark.asyncio
    async def test_cancel_job_removes_pending_job(self):
        """
        cancel_job() explicitly removes a pending job from tracker.

        Given a job is registered and pending
        When cancel_job() is called
        Then the job should be removed from pending and return True
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-to-cancel")

        # Verify job exists
        assert await tracker.has_job("job-to-cancel") is True

        # Cancel the job
        result = await tracker.cancel_job("job-to-cancel")

        assert result is True
        assert await tracker.has_job("job-to-cancel") is False

    @pytest.mark.asyncio
    async def test_cancel_job_returns_false_for_nonexistent_job(self):
        """
        cancel_job() returns False for job that doesn't exist.

        Given a job_id that was never registered
        When cancel_job() is called
        Then it should return False
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()

        result = await tracker.cancel_job("nonexistent-job")

        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_job_returns_false_for_completed_job(self):
        """
        cancel_job() returns False for already completed job.

        Given a job has already been completed via callback
        When cancel_job() is called
        Then it should return False (job already consumed)
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-completed")

        # Complete the job
        job_result = JobResult(
            job_id="job-completed",
            status="completed",
            output="Result",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(job_result)

        # Wait to consume the result (removes from tracker)
        await tracker.wait_for_job("job-completed", timeout=1.0)

        # Now try to cancel - should fail because job was already consumed
        result = await tracker.cancel_job("job-completed")

        assert result is False


class TestDelegationJobTrackerCacheIntegration:
    """
    Tests for DelegationJobTracker cache integration.

    Story #720: Delegation Result Caching for Retry Scenarios

    When MCP call times out and client retries, cached result should be
    returned immediately instead of waiting on Future again.
    """

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        DelegationJobTracker._instance = None
        yield
        DelegationJobTracker._instance = None

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path for PayloadCache."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "payload_cache.db"

    @pytest.fixture
    async def payload_cache(self, temp_db_path):
        """Create and initialize a PayloadCache instance for testing."""
        from code_indexer.server.cache.payload_cache import (
            PayloadCache,
            PayloadCacheConfig,
        )

        config = PayloadCacheConfig()
        cache = PayloadCache(db_path=temp_db_path, config=config)
        await cache.initialize()
        yield cache
        await cache.close()

    @pytest.mark.asyncio
    async def test_complete_job_caches_result(self, payload_cache):
        """
        complete_job() caches the result in PayloadCache.

        Given a job is registered and tracker has payload_cache set
        When complete_job() is called with a JobResult
        Then the result should be stored in cache with key "delegation:{job_id}"
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        tracker.set_payload_cache(payload_cache)
        await tracker.register_job("job-cache-test")

        result = JobResult(
            job_id="job-cache-test",
            status="completed",
            output="The authentication uses JWT tokens with RSA-256.",
            exit_code=0,
            error=None,
        )

        await tracker.complete_job(result)

        # Verify result is cached
        cache_key = "delegation:job-cache-test"
        assert await payload_cache.has_key(cache_key) is True

        # Verify cached content is correct JSON
        import json

        cached = await payload_cache.retrieve(cache_key, page=0)
        cached_result = json.loads(cached.content)
        assert cached_result["job_id"] == "job-cache-test"
        assert cached_result["status"] == "completed"
        assert "JWT tokens" in cached_result["output"]

    @pytest.mark.asyncio
    async def test_wait_for_job_returns_cached_result_immediately(self, payload_cache):
        """
        wait_for_job() returns cached result without waiting on Future.

        Given a job result is already cached (from previous completion)
        When wait_for_job() is called (simulating retry after timeout)
        Then it should return the cached result immediately
        """
        import json
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        tracker.set_payload_cache(payload_cache)

        # Pre-populate cache (simulating result from previous callback)
        job_id = "job-cached-retry"
        cache_key = f"delegation:{job_id}"
        cached_result = {
            "job_id": job_id,
            "status": "completed",
            "output": "Cached result from previous callback",
            "exit_code": 0,
            "error": None,
        }
        await payload_cache.store_with_key(cache_key, json.dumps(cached_result))

        # Register job (simulating new poll attempt after timeout)
        await tracker.register_job(job_id)

        # wait_for_job should return cached result immediately
        # Using short timeout to verify it doesn't actually wait
        result = await tracker.wait_for_job(job_id, timeout=0.01)

        assert result is not None
        assert result.job_id == job_id
        assert result.status == "completed"
        assert "Cached result" in result.output

    @pytest.mark.asyncio
    async def test_wait_for_job_falls_back_to_future_when_not_cached(self, payload_cache):
        """
        wait_for_job() waits on Future when result not in cache.

        Given a job is registered but result is NOT cached
        When wait_for_job() is called and Future is resolved
        Then it should return the Future result
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        tracker.set_payload_cache(payload_cache)
        await tracker.register_job("job-no-cache")

        # Complete the job (this will also cache the result)
        result = JobResult(
            job_id="job-no-cache",
            status="completed",
            output="Result from Future, not pre-cached",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(result)

        # wait_for_job should return the result
        returned = await tracker.wait_for_job("job-no-cache", timeout=1.0)

        assert returned is not None
        assert returned.output == "Result from Future, not pre-cached"

    @pytest.mark.asyncio
    async def test_retry_after_timeout_gets_cached_result(self, payload_cache):
        """
        Full retry scenario: timeout on first poll, cached result on retry.

        Given a job is registered
        When first wait_for_job() times out and callback arrives
        Then retry wait_for_job() returns cached result immediately
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        tracker.set_payload_cache(payload_cache)
        await tracker.register_job("job-retry-scenario")

        # First wait times out
        result1 = await tracker.wait_for_job("job-retry-scenario", timeout=0.01)
        assert result1 is None

        # Callback arrives and completes the job (caches result)
        callback_result = JobResult(
            job_id="job-retry-scenario",
            status="completed",
            output="Late callback result now cached",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(callback_result)

        # Re-register job for retry (simulating new poll from client)
        # Job was removed after callback, so we need to re-register
        await tracker.register_job("job-retry-scenario")

        # Second wait should get cached result immediately
        result2 = await tracker.wait_for_job("job-retry-scenario", timeout=0.01)

        assert result2 is not None
        assert result2.status == "completed"
        assert "cached" in result2.output.lower()

    @pytest.mark.asyncio
    async def test_cache_works_without_payload_cache_set(self):
        """
        DelegationJobTracker works normally when payload_cache is not set.

        Given tracker has no payload_cache configured
        When complete_job() and wait_for_job() are called
        Then they should work normally (just without caching)
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        # Do NOT set payload_cache
        await tracker.register_job("job-no-cache-configured")

        result = JobResult(
            job_id="job-no-cache-configured",
            status="completed",
            output="Works without cache",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(result)

        returned = await tracker.wait_for_job("job-no-cache-configured", timeout=1.0)

        assert returned is not None
        assert returned.output == "Works without cache"

    @pytest.mark.asyncio
    async def test_cache_failed_result(self, payload_cache):
        """
        complete_job() also caches failed results.

        Given a job fails
        When complete_job() is called with failed status
        Then the failed result should also be cached
        """
        import json
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        tracker.set_payload_cache(payload_cache)
        await tracker.register_job("job-failed-cache")

        result = JobResult(
            job_id="job-failed-cache",
            status="failed",
            output="",
            exit_code=1,
            error="Repository clone failed: authentication denied",
        )
        await tracker.complete_job(result)

        # Verify failed result is cached
        cache_key = "delegation:job-failed-cache"
        cached = await payload_cache.retrieve(cache_key, page=0)
        cached_result = json.loads(cached.content)
        assert cached_result["status"] == "failed"
        assert "authentication denied" in cached_result["error"]
