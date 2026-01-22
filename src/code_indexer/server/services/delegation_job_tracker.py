"""
Delegation Job Tracker Service.

Story #720: Callback-Based Delegation Job Completion

Singleton service for tracking pending delegation jobs with asyncio Futures.
Enables callback-based completion where Claude Server POSTs results back to CIDX.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from code_indexer.server.cache.payload_cache import PayloadCache

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """
    Result from callback payload.

    Contains the data sent by Claude Server when a delegation job completes.
    """

    job_id: str
    status: str  # completed, failed
    output: str  # The Output field from callback - main result content
    exit_code: Optional[int]
    error: Optional[str]


class DelegationJobTracker:
    """
    Singleton service for tracking pending delegation jobs.

    Uses asyncio Futures to enable blocking wait for job completion via callback.

    Flow:
    1. execute_delegation_function calls register_job() after starting a job
    2. poll_delegation_job calls wait_for_job() to block until callback arrives
    3. Callback endpoint calls complete_job() when Claude Server POSTs result
    4. wait_for_job() unblocks and returns the JobResult
    """

    _instance: Optional["DelegationJobTracker"] = None

    @classmethod
    def get_instance(cls) -> "DelegationJobTracker":
        """
        Get the singleton instance.

        Returns:
            The singleton DelegationJobTracker instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        """Initialize the tracker with empty pending jobs dict."""
        self._pending_jobs: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._payload_cache: Optional["PayloadCache"] = None

    def set_payload_cache(self, cache: "PayloadCache") -> None:
        """
        Set the PayloadCache instance for result caching.

        Story #720: Delegation Result Caching

        Args:
            cache: PayloadCache instance for caching delegation results
        """
        self._payload_cache = cache

    async def register_job(self, job_id: str) -> None:
        """
        Register a pending job and create its Future.

        This method is idempotent - calling it multiple times with the same
        job_id will not overwrite an existing Future.

        Args:
            job_id: The unique job identifier from Claude Server
        """
        async with self._lock:
            if job_id not in self._pending_jobs:
                loop = asyncio.get_event_loop()
                self._pending_jobs[job_id] = loop.create_future()
                logger.debug(f"Registered pending job: {job_id}")

    async def has_job(self, job_id: str) -> bool:
        """
        Check if a job is registered in the tracker.

        Args:
            job_id: The job identifier to check

        Returns:
            True if the job is registered (pending completion), False otherwise
        """
        async with self._lock:
            return job_id in self._pending_jobs

    async def complete_job(self, result: JobResult) -> bool:
        """
        Complete a pending job with the callback result.

        Resolves the Future associated with the job_id, allowing any
        wait_for_job() calls to unblock and receive the result.

        Story #720: Also caches the result in PayloadCache for retry scenarios.

        Args:
            result: The JobResult from the callback payload

        Returns:
            True if the job was found and completed, False otherwise
        """
        async with self._lock:
            future = self._pending_jobs.get(result.job_id)
            if future is None:
                logger.warning(f"complete_job called for unknown job: {result.job_id}")
                return False

            if future.done():
                logger.warning(
                    f"complete_job called for already completed job: {result.job_id}"
                )
                return False

            future.set_result(result)
            logger.debug(f"Completed job: {result.job_id} with status: {result.status}")

        # Cache result for retry scenarios (outside lock to avoid blocking)
        if self._payload_cache is not None:
            try:
                cache_key = f"delegation:{result.job_id}"
                serialized = json.dumps(asdict(result))
                await self._payload_cache.store_with_key(cache_key, serialized)
                logger.debug(f"Cached result for job: {result.job_id}")
            except Exception as e:
                # Log but don't fail - caching is optional optimization
                logger.warning(f"Failed to cache result for job {result.job_id}: {e}")

        return True

    async def wait_for_job(
        self, job_id: str, timeout: float = 600.0
    ) -> Optional[JobResult]:
        """
        Wait for job completion via callback.

        Story #720: Checks cache FIRST for retry scenarios. If result is cached
        (from previous callback), returns immediately without waiting on Future.

        Blocks until complete_job() is called for this job_id, or timeout expires.

        On cache hit: Returns cached JobResult immediately.
        On timeout: Returns None but KEEPS the job in pending (caller can retry).
        On callback: Returns JobResult and REMOVES the job from pending.

        Args:
            job_id: The job identifier to wait for
            timeout: Maximum time to wait in seconds (default: 600s / 10 minutes)

        Returns:
            JobResult if callback arrived or cached, None if job not found or timeout
        """
        # Story #720: Check cache FIRST for retry scenarios
        if self._payload_cache is not None:
            try:
                cache_key = f"delegation:{job_id}"
                if await self._payload_cache.has_key(cache_key):
                    cached = await self._payload_cache.retrieve(cache_key, page=0)
                    cached_dict = json.loads(cached.content)
                    result = JobResult(**cached_dict)
                    logger.debug(f"Returning cached result for job: {job_id}")
                    # Remove job from pending since we're returning cached result
                    async with self._lock:
                        self._pending_jobs.pop(job_id, None)
                    return result
            except Exception as e:
                # Log but continue to wait on Future if cache fails
                logger.debug(f"Cache lookup failed for job {job_id}: {e}")

        async with self._lock:
            future = self._pending_jobs.get(job_id)

        if future is None:
            logger.warning(f"wait_for_job called for unknown job: {job_id}")
            return None

        try:
            # Use asyncio.shield() to prevent wait_for from cancelling the Future
            # This allows retry after timeout - the Future stays intact
            result = await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            # Only remove on successful callback receipt
            async with self._lock:
                self._pending_jobs.pop(job_id, None)
            logger.debug(f"wait_for_job returned result for job: {job_id}")
            return result
        except asyncio.TimeoutError:
            # DO NOT remove on timeout - job is still valid, caller can retry
            logger.debug(
                f"wait_for_job timed out for job: {job_id}, keeping in tracker"
            )
            return None
        except asyncio.CancelledError:
            # Shield was cancelled but Future may still be valid - propagate
            raise

    async def cancel_job(self, job_id: str) -> bool:
        """
        Explicitly remove a job from tracking (caller gave up).

        Use this method when the caller decides to stop waiting for a job
        and wants to clean up the tracker. This cancels the Future and
        removes the job from pending.

        Args:
            job_id: The job identifier to cancel

        Returns:
            True if the job was found and cancelled, False otherwise
        """
        async with self._lock:
            future = self._pending_jobs.pop(job_id, None)
            if future is None:
                return False

            if not future.done():
                future.cancel()
            logger.debug(f"Cancelled job: {job_id}")
            return True
