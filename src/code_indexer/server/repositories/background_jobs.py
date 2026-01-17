"""
Background Job System for CIDX Server.

Manages asynchronous operations for golden repositories and other long-running tasks.
Provides persistence, user isolation, job management, and comprehensive tracking.
"""

import json
import logging
import queue
import threading
import uuid
import inspect
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, Callable, TYPE_CHECKING, List
from dataclasses import dataclass, asdict

if TYPE_CHECKING:
    from code_indexer.server.utils.config_manager import ServerResourceConfig
    from code_indexer.server.storage.sqlite_backends import BackgroundJobsSqliteBackend


class JobStatus(str, Enum):
    """Job status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RESOLVING_PREREQUISITES = "resolving_prerequisites"  # AC2: SCIP self-healing state


@dataclass
class BackgroundJob:
    """Background job data structure with SCIP self-healing support."""

    job_id: str
    operation_type: str
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    progress: int  # 0-100
    username: str  # User who submitted the job
    is_admin: bool = False  # Admin priority flag
    cancelled: bool = False  # Cancellation flag

    # SCIP Self-Healing Fields (AC1: Extended BackgroundJob Model)
    repo_alias: Optional[str] = None  # Repository being processed
    resolution_attempts: int = 0  # Total Claude Code invocations across all projects
    claude_actions: Optional[List[str]] = None  # Aggregated actions from all projects
    failure_reason: Optional[str] = None  # Human-readable failure explanation
    extended_error: Optional[Dict[str, Any]] = None  # Structured error context
    language_resolution_status: Optional[Dict[str, Dict[str, Any]]] = (
        None  # Per-project tracking
    )


class BackgroundJobManager:
    """
    Enhanced background job manager for long-running operations.

    Provides job queuing, execution, status tracking, persistence,
    user isolation, and comprehensive job management functionality.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        resource_config: Optional["ServerResourceConfig"] = None,
        use_sqlite: bool = False,
        db_path: Optional[str] = None,
    ):
        """Initialize enhanced background job manager.

        Args:
            storage_path: Path for persistent job storage (JSON file, optional)
            resource_config: Resource configuration (limits, timeouts)
            use_sqlite: Whether to use SQLite backend instead of JSON file
            db_path: Path to SQLite database file (required if use_sqlite=True)
        """
        self.jobs: Dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()
        self._executor = None
        self._running_jobs: Dict[str, threading.Thread] = {}
        self._job_queue: queue.PriorityQueue = queue.PriorityQueue()

        # Persistence settings
        self.storage_path = storage_path
        self.use_sqlite = use_sqlite
        self.db_path = db_path
        self._sqlite_backend: Optional["BackgroundJobsSqliteBackend"] = None

        # Initialize SQLite backend if enabled
        if self.use_sqlite and self.db_path:
            from code_indexer.server.storage.sqlite_backends import (
                BackgroundJobsSqliteBackend,
            )

            self._sqlite_backend = BackgroundJobsSqliteBackend(self.db_path)
            logging.info("BackgroundJobManager using SQLite backend")

        # Resource configuration (import here to avoid circular dependency)
        if resource_config is None:
            from code_indexer.server.utils.config_manager import ServerResourceConfig

            resource_config = ServerResourceConfig()
        self.resource_config = resource_config

        # Load persisted jobs
        self._load_jobs()

        # Background job manager initialized silently

    def submit_job(
        self,
        operation_type: str,
        func: Callable[[], Dict[str, Any]],
        *args,
        submitter_username: str,
        is_admin: bool = False,
        repo_alias: Optional[str] = None,  # AC5: Fix unknown repo bug
        **kwargs,
    ) -> str:
        """
        Submit a job for background execution.

        Args:
            operation_type: Type of operation (e.g., 'add_golden_repo')
            func: Function to execute
            *args: Function arguments
            submitter_username: Username of the job submitter
            is_admin: Whether this is an admin job (higher priority)
            repo_alias: Repository alias being processed (AC5: Fix unknown repo bug)
            **kwargs: Function keyword arguments

        Returns:
            Job ID for tracking

        Raises:
            Exception: If user has exceeded max jobs limit (if configured)
        """
        # Check maintenance mode first (Story #734)
        from code_indexer.server.services.maintenance_service import (
            get_maintenance_state,
        )
        from code_indexer.server.jobs.exceptions import MaintenanceModeError

        if get_maintenance_state().is_maintenance_mode():
            raise MaintenanceModeError()

        # NOTE: max_jobs_per_user limit has been removed as an artificial constraint
        # Jobs are no longer limited per user

        # AC5: Validate repo_alias to prevent "unknown" values
        if repo_alias is None:
            logging.warning(
                f"Job submitted without repo_alias for operation '{operation_type}' "
                f"by user '{submitter_username}'. Consider providing repo_alias."
            )
        elif repo_alias.lower() == "unknown":
            logging.warning(
                f"Job submitted with repo_alias='unknown' for operation '{operation_type}' "
                f"by user '{submitter_username}'. This may indicate missing repository context."
            )

        job_id = str(uuid.uuid4())

        job = BackgroundJob(
            job_id=job_id,
            operation_type=operation_type,
            status=JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
            progress=0,
            username=submitter_username,
            is_admin=is_admin,
            repo_alias=repo_alias,  # AC5: Store repo_alias
        )

        with self._lock:
            self.jobs[job_id] = job
            self._persist_jobs()

        # Execute job in background thread
        thread = threading.Thread(
            target=self._execute_job, args=(job_id, func, args, kwargs)
        )
        # Thread is not daemon to ensure proper shutdown
        thread.start()

        # Track running thread
        with self._lock:
            self._running_jobs[job_id] = thread

        logging.info(
            f"Background job {job_id} submitted by {submitter_username}: {operation_type}"
        )
        return job_id

    def get_job_status(self, job_id: str, username: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a background job with user isolation.

        Args:
            job_id: Job ID to check
            username: Username requesting the status (for authorization)

        Returns:
            Job status dictionary or None if job not found or not authorized
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if not job or job.username != username:
                return None

            return {
                "job_id": job.job_id,
                "operation_type": job.operation_type,
                "status": job.status.value,
                "created_at": job.created_at.isoformat(),
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": (
                    job.completed_at.isoformat() if job.completed_at else None
                ),
                "progress": job.progress,
                "result": job.result,
                "error": job.error,
                "username": job.username,
                "repo_alias": job.repo_alias,  # AC5: Include repo_alias in response
                # AC6: Extended self-healing fields
                "resolution_attempts": job.resolution_attempts,
                "claude_actions": job.claude_actions,
                "failure_reason": job.failure_reason,
                "extended_error": job.extended_error,
                "language_resolution_status": job.language_resolution_status,
            }

    def list_jobs(
        self,
        username: str,
        status_filter: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        List jobs for a user with filtering and pagination.

        Args:
            username: Username to filter jobs for
            status_filter: Optional status filter
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip

        Returns:
            Dictionary with jobs list and total count
        """
        with self._lock:
            # Filter jobs by user
            user_jobs = [job for job in self.jobs.values() if job.username == username]

            # Apply status filter if provided
            if status_filter:
                user_jobs = [
                    job for job in user_jobs if job.status.value == status_filter
                ]

            # Sort by creation time (newest first)
            user_jobs.sort(key=lambda x: x.created_at, reverse=True)

            total_count = len(user_jobs)

            # Apply pagination
            paginated_jobs = user_jobs[offset : offset + limit]

            # Convert to dictionary format
            job_dicts = []
            for job in paginated_jobs:
                job_dicts.append(
                    {
                        "job_id": job.job_id,
                        "operation_type": job.operation_type,
                        "status": job.status.value,
                        "created_at": job.created_at.isoformat(),
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "progress": job.progress,
                        "result": job.result,
                        "error": job.error,
                        "username": job.username,
                        "repo_alias": job.repo_alias,  # AC5: Include repo_alias in list
                        # AC6: Extended self-healing fields
                        "resolution_attempts": job.resolution_attempts,
                        "claude_actions": job.claude_actions,
                        "failure_reason": job.failure_reason,
                        "extended_error": job.extended_error,
                        "language_resolution_status": job.language_resolution_status,
                    }
                )

            return {
                "jobs": job_dicts,
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }

    def cancel_job(self, job_id: str, username: str) -> Dict[str, Any]:
        """
        Cancel a running or pending job.

        Args:
            job_id: Job ID to cancel
            username: Username requesting cancellation (for authorization)

        Returns:
            Cancellation result dictionary
        """
        with self._lock:
            job = self.jobs.get(job_id)
            if not job or job.username != username:
                return {"success": False, "message": "Job not found or not authorized"}

            if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
                return {
                    "success": False,
                    "message": f"Cannot cancel job in {job.status.value} status",
                }

            # Mark job as cancelled
            job.cancelled = True

            if job.status == JobStatus.PENDING:
                # If pending, immediately mark as cancelled
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
            elif job.status == JobStatus.RUNNING:
                # For running jobs, the job execution will detect cancellation
                # and update status accordingly
                pass

            self._persist_jobs()

        logging.info(f"Job {job_id} cancelled by user {username}")
        return {"success": True, "message": "Job cancelled successfully"}

    def _execute_job(
        self, job_id: str, func: Callable[[], Dict[str, Any]], args: tuple, kwargs: dict
    ) -> None:
        """
        Execute a background job with cancellation support.

        Args:
            job_id: Job ID
            func: Function to execute
            args: Function arguments
            kwargs: Function keyword arguments
        """
        with self._lock:
            job = self.jobs[job_id]
            if job.cancelled:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
                self._persist_jobs()
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.progress = 10
            self._persist_jobs()

        logging.info(f"Starting background job {job_id}")

        try:
            # Create progress callback function
            def progress_callback(progress: int):
                with self._lock:
                    if job_id in self.jobs and not self.jobs[job_id].cancelled:
                        self.jobs[job_id].progress = progress
                        self._persist_jobs()

            # Check if function accepts progress callback
            func_signature = inspect.signature(func)

            # Update progress during execution
            progress_callback(25)

            # Check for cancellation before execution
            with self._lock:
                if self.jobs[job_id].cancelled:
                    self.jobs[job_id].status = JobStatus.CANCELLED
                    self.jobs[job_id].completed_at = datetime.now(timezone.utc)
                    self._persist_jobs()
                    return

            # Execute the actual operation with frequent cancellation checks
            if "progress_callback" in func_signature.parameters:
                # Add progress_callback to kwargs
                enhanced_kwargs = kwargs.copy()
                enhanced_kwargs["progress_callback"] = progress_callback
                result = func(*args, **enhanced_kwargs)
            else:
                # For functions without progress callback, we need to wrap execution
                # to check for cancellation periodically
                result = self._execute_with_cancellation_check(
                    job_id, func, args, kwargs
                )

            # Job completed successfully
            with self._lock:
                job = self.jobs[job_id]
                if not job.cancelled:
                    job.status = JobStatus.COMPLETED
                    job.completed_at = datetime.now(timezone.utc)
                    job.result = result
                    job.progress = 100
                else:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now(timezone.utc)
                self._persist_jobs()

            logging.info(f"Background job {job_id} completed successfully")

        except InterruptedError as e:
            # Job was cancelled
            logging.info(f"Background job {job_id} was cancelled: {e}")
            with self._lock:
                job = self.jobs[job_id]
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
                job.error = str(e)
                job.progress = 0
                self._persist_jobs()
        except Exception as e:
            # Job failed
            error_msg = str(e)
            logging.error(f"Background job {job_id} failed: {error_msg}")

            with self._lock:
                job = self.jobs[job_id]
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                job.error = error_msg
                job.progress = 0
                self._persist_jobs()

        finally:
            # Clean up running job reference
            with self._lock:
                self._running_jobs.pop(job_id, None)

    def _execute_with_cancellation_check(
        self, job_id: str, func: Callable, args: tuple, kwargs: dict
    ) -> Any:
        """
        Execute a function with periodic cancellation checks.

        For long-running functions that don't support progress callbacks,
        this method runs them in a separate thread and checks for cancellation.
        """
        import threading
        import queue
        from typing import Any

        result_queue: queue.Queue[Any] = queue.Queue()
        exception_queue: queue.Queue[Exception] = queue.Queue()

        def worker():
            try:
                result = func(*args, **kwargs)
                result_queue.put(result)
            except Exception as e:
                exception_queue.put(e)

        # Start function in separate thread
        worker_thread = threading.Thread(target=worker)
        # Worker thread is not daemon to ensure proper shutdown
        worker_thread.start()

        # Poll for completion or cancellation
        while worker_thread.is_alive():
            # Check for cancellation
            with self._lock:
                if self.jobs[job_id].cancelled:
                    # Function is still running, but we mark as cancelled
                    # The thread will continue but we ignore its result
                    raise InterruptedError("Job cancelled during execution")

            # Wait a bit before next check
            worker_thread.join(timeout=0.1)

        # Check if there was an exception
        if not exception_queue.empty():
            raise exception_queue.get()

        # Return result if available
        if not result_queue.empty():
            return result_queue.get()

        # Should not reach here normally
        return {"status": "completed"}

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """
        Clean up old completed/failed jobs.

        Args:
            max_age_hours: Maximum age of jobs to keep in hours

        Returns:
            Number of jobs cleaned up
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cleaned_count = 0

        with self._lock:
            job_ids_to_remove = []

            for job_id, job in self.jobs.items():
                if (
                    job.status
                    in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
                    and job.completed_at
                    and job.completed_at < cutoff_time
                ):
                    job_ids_to_remove.append(job_id)

            for job_id in job_ids_to_remove:
                del self.jobs[job_id]
                cleaned_count += 1

            if cleaned_count > 0:
                self._persist_jobs()

        if cleaned_count > 0:
            logging.info(f"Cleaned up {cleaned_count} old background jobs")

        return cleaned_count

    def get_active_job_count(self) -> int:
        """
        Get count of currently active/running jobs.

        Returns:
            Number of active jobs
        """
        with self._lock:
            return sum(
                1 for job in self.jobs.values() if job.status == JobStatus.RUNNING
            )

    def get_pending_job_count(self) -> int:
        """
        Get count of pending jobs waiting to be executed.

        Returns:
            Number of pending jobs
        """
        with self._lock:
            return sum(
                1 for job in self.jobs.values() if job.status == JobStatus.PENDING
            )

    def get_failed_job_count(self) -> int:
        """
        Get count of failed jobs.

        Returns:
            Number of failed jobs
        """
        with self._lock:
            return sum(
                1 for job in self.jobs.values() if job.status == JobStatus.FAILED
            )

    def shutdown(self) -> None:
        """
        Graceful shutdown of all running jobs.

        Cancels all running jobs and waits for threads to complete.
        This method should be called during application shutdown.
        """
        with self._lock:
            # Cancel all running jobs
            running_job_ids = list(self._running_jobs.keys())
            for job_id in running_job_ids:
                job = self.jobs.get(job_id)
                if job and job.status == JobStatus.RUNNING:
                    job.cancelled = True
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now(timezone.utc)
                    logging.info(f"Job {job_id} cancelled during shutdown")

            # Persist final job states
            self._persist_jobs()

            # Get list of threads to wait for
            threads_to_wait = list(self._running_jobs.values())

        # Wait for all threads to complete (outside of lock to avoid deadlock)
        for thread in threads_to_wait:
            if thread.is_alive():
                try:
                    thread.join(timeout=5.0)
                    if thread.is_alive():
                        logging.warning(
                            f"Thread {thread.name} did not complete gracefully within 5 seconds"
                        )
                except Exception as e:
                    logging.error(f"Error waiting for thread to complete: {e}")

        logging.info("Background job manager shutdown complete")

    def get_jobs_by_operation_and_params(
        self, operation_types: list[str], params_filter: Optional[Dict[str, Any]] = None
    ) -> list[Dict[str, Any]]:
        """
        Get jobs by operation type and optional parameter filtering.

        This is a simplified implementation for repository deletion job cancellation.
        In a real implementation, this would parse job parameters and filter accordingly.

        Args:
            operation_types: List of operation types to filter by
            params_filter: Optional dictionary of parameters to match (currently unused)

        Returns:
            List of job dictionaries matching the criteria
        """
        with self._lock:
            matching_jobs = []
            for job in self.jobs.values():
                if job.operation_type in operation_types:
                    # For now, return basic job info
                    # In a real implementation, we'd parse stored parameters and filter
                    job_dict = {
                        "job_id": job.job_id,
                        "operation_type": job.operation_type,
                        "status": job.status.value,
                        "username": job.username,
                        "created_at": job.created_at.isoformat(),
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "progress": job.progress,
                        "result": job.result,
                        "error": job.error,
                    }
                    matching_jobs.append(job_dict)

            return matching_jobs

    def _persist_jobs(self) -> None:
        """
        Persist jobs to storage (SQLite or JSON file).

        Note: This method should be called within a lock.
        """
        # Use SQLite backend if enabled
        if self._sqlite_backend:
            self._persist_jobs_sqlite()
            return

        # Fall back to JSON file storage
        if not self.storage_path:
            return

        try:
            storage_file = Path(self.storage_path)
            storage_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert jobs to serializable format
            serializable_jobs = {}
            for job_id, job in self.jobs.items():
                job_dict = asdict(job)
                # Convert datetime objects to ISO strings
                for field in ["created_at", "started_at", "completed_at"]:
                    if job_dict[field] is not None:
                        job_dict[field] = job_dict[field].isoformat()
                # Convert enum to string
                job_dict["status"] = (
                    job_dict["status"].value
                    if hasattr(job_dict["status"], "value")
                    else job_dict["status"]
                )
                serializable_jobs[job_id] = job_dict

            with open(storage_file, "w") as f:
                json.dump(serializable_jobs, f, indent=2)

        except Exception as e:
            # Log the error but don't raise - persistence failures shouldn't break the system
            # Jobs should still work in memory even if persistence fails
            logging.error(f"Failed to persist jobs: {e}")
            # TODO: Consider implementing retry logic for failed persistence attempts

    def _persist_jobs_sqlite(self) -> None:
        """
        Persist all in-memory jobs to SQLite.

        Note: This method should be called within a lock.
        """
        if not self._sqlite_backend:
            return

        try:
            for job_id, job in self.jobs.items():
                # Check if job exists in database
                existing = self._sqlite_backend.get_job(job_id)
                if existing:
                    # Update existing job
                    self._sqlite_backend.update_job(
                        job_id=job_id,
                        status=job.status.value,
                        started_at=(
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        completed_at=(
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        result=job.result,
                        error=job.error,
                        progress=job.progress,
                        cancelled=job.cancelled,
                        resolution_attempts=job.resolution_attempts,
                        claude_actions=job.claude_actions,
                        failure_reason=job.failure_reason,
                        extended_error=job.extended_error,
                        language_resolution_status=job.language_resolution_status,
                    )
                else:
                    # Insert new job
                    self._sqlite_backend.save_job(
                        job_id=job_id,
                        operation_type=job.operation_type,
                        status=job.status.value,
                        created_at=job.created_at.isoformat(),
                        started_at=(
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        completed_at=(
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        result=job.result,
                        error=job.error,
                        progress=job.progress,
                        username=job.username,
                        is_admin=job.is_admin,
                        cancelled=job.cancelled,
                        repo_alias=job.repo_alias,
                        resolution_attempts=job.resolution_attempts,
                        claude_actions=job.claude_actions,
                        failure_reason=job.failure_reason,
                        extended_error=job.extended_error,
                        language_resolution_status=job.language_resolution_status,
                    )
        except Exception as e:
            logging.error(f"Failed to persist jobs to SQLite: {e}")

    # Maximum number of jobs to load from SQLite into memory at startup
    MAX_JOBS_TO_LOAD = 10000

    def _load_jobs(self) -> None:
        """
        Load jobs from storage (SQLite or JSON file).
        """
        # Use SQLite backend if enabled
        if self._sqlite_backend:
            self._load_jobs_sqlite()
            return

        # Fall back to JSON file storage
        if not self.storage_path:
            return

        try:
            storage_file = Path(self.storage_path)
            if not storage_file.exists():
                return

            with open(storage_file, "r") as f:
                stored_jobs = json.load(f)

            for job_id, job_dict in stored_jobs.items():
                # Convert ISO strings back to datetime objects
                for field in ["created_at", "started_at", "completed_at"]:
                    if job_dict[field] is not None:
                        job_dict[field] = datetime.fromisoformat(job_dict[field])

                # Convert string status back to enum
                job_dict["status"] = JobStatus(job_dict["status"])

                # Create job object
                job = BackgroundJob(**job_dict)
                self.jobs[job_id] = job

            logging.info(f"Loaded {len(stored_jobs)} jobs from storage")

        except Exception as e:
            logging.error(f"Failed to load jobs from storage: {e}")

    def _load_jobs_sqlite(self) -> None:
        """
        Load jobs from SQLite database into memory.

        Story #723: Clean up orphaned jobs before loading.
        On server restart, any 'running' or 'pending' jobs are orphaned
        since the processes executing them no longer exist.
        """
        if not self._sqlite_backend:
            return

        try:
            # Story #723: Clean up orphaned jobs on server startup
            # This must happen BEFORE loading jobs into memory to ensure
            # the in-memory state reflects the cleaned-up database state
            orphan_count = self._sqlite_backend.cleanup_orphaned_jobs_on_startup()
            if orphan_count > 0:
                logging.info(
                    f"Cleaned up {orphan_count} orphaned jobs on server startup"
                )

            stored_jobs = self._sqlite_backend.list_jobs(limit=self.MAX_JOBS_TO_LOAD)

            for job_dict in stored_jobs:
                # Convert ISO strings back to datetime objects
                for field in ["created_at", "started_at", "completed_at"]:
                    if job_dict.get(field) is not None:
                        job_dict[field] = datetime.fromisoformat(job_dict[field])

                # Convert string status back to enum
                job_dict["status"] = JobStatus(job_dict["status"])

                # Create job object
                job = BackgroundJob(**job_dict)
                self.jobs[job_dict["job_id"]] = job

            logging.info(f"Loaded {len(stored_jobs)} jobs from SQLite")

        except Exception as e:
            logging.error(f"Failed to load jobs from SQLite: {e}")

    def _calculate_cutoff(self, time_filter: str) -> datetime:
        """
        Calculate cutoff datetime based on time filter.

        Args:
            time_filter: Time filter string ("24h", "7d", "30d")

        Returns:
            Cutoff datetime (timezone-aware UTC)
        """
        now = datetime.now(timezone.utc)

        if time_filter == "24h":
            return now - timedelta(hours=24)
        elif time_filter == "7d":
            return now - timedelta(days=7)
        elif time_filter == "30d":
            return now - timedelta(days=30)
        else:
            # Default to 24h for invalid filters
            return now - timedelta(hours=24)

    def get_job_stats_with_filter(self, time_filter: str = "24h") -> Dict[str, int]:
        """
        Get job statistics filtered by time period.

        Args:
            time_filter: Time filter string ("24h", "7d", "30d")

        Returns:
            Dictionary with "completed" and "failed" counts
        """
        cutoff_time = self._calculate_cutoff(time_filter)

        with self._lock:
            completed = 0
            failed = 0

            for job in self.jobs.values():
                # Only count jobs with completion time after cutoff
                if job.completed_at and job.completed_at >= cutoff_time:
                    if job.status == JobStatus.COMPLETED:
                        completed += 1
                    elif job.status == JobStatus.FAILED:
                        failed += 1

            return {"completed": completed, "failed": failed}

    def get_recent_jobs_with_filter(
        self, time_filter: str = "30d", limit: int = 20
    ) -> list[Dict[str, Any]]:
        """
        Get recent jobs filtered by time period.

        Args:
            time_filter: Time filter string ("24h", "7d", "30d"), default "30d"
            limit: Maximum number of jobs to return, default 20

        Returns:
            List of job dictionaries sorted by completion time (newest first)
        """
        cutoff_time = self._calculate_cutoff(time_filter)

        with self._lock:
            recent_jobs = []

            for job in self.jobs.values():
                # Only include completed or failed jobs within time range
                if (
                    job.status in [JobStatus.COMPLETED, JobStatus.FAILED]
                    and job.completed_at
                    and job.completed_at >= cutoff_time
                ):
                    job_dict = {
                        "job_id": job.job_id,
                        "operation_type": job.operation_type,
                        "status": job.status.value,
                        "created_at": job.created_at.isoformat(),
                        "started_at": (
                            job.started_at.isoformat() if job.started_at else None
                        ),
                        "completed_at": (
                            job.completed_at.isoformat() if job.completed_at else None
                        ),
                        "progress": job.progress,
                        "result": job.result,
                        "error": job.error,
                        "username": job.username,
                    }
                    recent_jobs.append(job_dict)

            # Sort by completion time (newest first)
            # Note: completed_at is an ISO format datetime string from .isoformat()
            recent_jobs.sort(
                key=lambda x: (
                    datetime.fromisoformat(x["completed_at"])
                    if isinstance(x["completed_at"], str) and x["completed_at"]
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
                reverse=True,
            )

            # Return up to limit jobs
            return recent_jobs[:limit]
