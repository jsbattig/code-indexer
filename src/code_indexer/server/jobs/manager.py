"""
Sync Job Manager for CIDX Server repository synchronization.

Manages sync job creation, retrieval, persistence, and lifecycle operations
with thread safety, error handling, and data integrity guarantees.
"""

import fcntl
import hashlib
import json
import logging
import os
import platform
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, cast
from urllib.parse import urlparse
import re

# System resource monitoring
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - resource monitoring disabled")

# Windows file locking support
if platform.system() == "Windows":
    import msvcrt

from .config import SyncJobConfig
from .exceptions import (
    DuplicateJobIdError,
    JobNotFoundError,
    InvalidJobParametersError,
    JobPersistenceError,
    DuplicateRepositorySyncError,
    ResourceLimitExceededError,
    InvalidJobStateTransitionError,
)
from .models import SyncJob, JobType, JobStatus, PhaseStatus


class SyncJobManager:
    """
    Manages sync jobs with persistence, thread safety, and data integrity.

    Provides comprehensive job lifecycle management including creation,
    retrieval, persistence, and concurrent operation support for
    repository synchronization operations.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        backup_dir: Optional[str] = None,
        backup_retention_count: int = 5,
        file_lock_timeout: float = 10.0,
        max_concurrent_jobs_per_user: int = 3,
        max_total_concurrent_jobs: int = 10,
        max_cpu_percent: float = 80.0,
        max_memory_percent: float = 85.0,
        degraded_mode_cpu_threshold: float = 70.0,
        degraded_mode_memory_threshold: float = 75.0,
        degraded_max_concurrent_jobs_per_user: int = 1,
        degraded_max_total_concurrent_jobs: int = 3,
        average_job_duration_minutes: int = 15,
        queue_check_interval_seconds: float = 5.0,
        resource_check_interval_seconds: float = 10.0,
    ):
        """
        Initialize sync job manager with resilient persistence and concurrency control.

        Args:
            storage_path: Path for persistent job storage (optional)
                         If None, jobs are kept in memory only
            backup_dir: Custom backup directory (optional)
                       If None, uses storage_path parent + 'backups'
            backup_retention_count: Number of backup files to maintain
            file_lock_timeout: Timeout for file lock acquisition in seconds
            max_concurrent_jobs_per_user: Maximum concurrent jobs per user
            max_total_concurrent_jobs: Maximum total concurrent jobs system-wide
            max_cpu_percent: CPU usage limit before blocking new jobs
            max_memory_percent: Memory usage limit before blocking new jobs
            degraded_mode_cpu_threshold: CPU threshold for degraded mode
            degraded_mode_memory_threshold: Memory threshold for degraded mode
            degraded_max_concurrent_jobs_per_user: Per-user limit in degraded mode
            degraded_max_total_concurrent_jobs: Total limit in degraded mode
            average_job_duration_minutes: Average job duration for wait time estimates
            queue_check_interval_seconds: Queue processing check interval
            resource_check_interval_seconds: Resource monitoring check interval
        """
        self._jobs: Dict[str, SyncJob] = {}
        self._lock = threading.Lock()
        self.storage_path = storage_path
        self.backup_retention_count = backup_retention_count
        self.file_lock_timeout = file_lock_timeout

        # Concurrency control configuration
        self.max_concurrent_jobs_per_user = max_concurrent_jobs_per_user
        self.max_total_concurrent_jobs = max_total_concurrent_jobs
        self.max_cpu_percent = max_cpu_percent
        self.max_memory_percent = max_memory_percent
        self.degraded_mode_cpu_threshold = degraded_mode_cpu_threshold
        self.degraded_mode_memory_threshold = degraded_mode_memory_threshold
        self.degraded_max_concurrent_jobs_per_user = (
            degraded_max_concurrent_jobs_per_user
        )
        self.degraded_max_total_concurrent_jobs = degraded_max_total_concurrent_jobs
        self.average_job_duration_minutes = average_job_duration_minutes
        self.queue_check_interval_seconds = queue_check_interval_seconds
        self.resource_check_interval_seconds = resource_check_interval_seconds

        # Queue management state
        self._job_queue: List[str] = []  # Job IDs in queue order
        self._repository_locks: Dict[str, str] = (
            {}
        )  # repo_url -> job_id mapping for active syncs
        self._last_resource_check = 0.0
        self._cached_resource_metrics: Optional[Dict[str, Any]] = None
        self.backup_dir: Optional[Path] = None

        # Configure backup directory
        if self.storage_path:
            if backup_dir:
                self.backup_dir = Path(backup_dir)
            else:
                self.backup_dir = Path(self.storage_path).parent / "backups"
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.backup_dir = None

        # Load existing jobs if storage path provided
        if self.storage_path:
            self._cleanup_stale_temp_files()
            self._load_jobs()

        logging.info(
            f"SyncJobManager initialized (storage: {storage_path}, backups: {self.backup_dir})"
        )

    def _acquire_file_lock(self, file_handle) -> bool:
        """
        Acquire exclusive file lock with timeout.

        Args:
            file_handle: Open file handle to lock

        Returns:
            True if lock acquired successfully, False otherwise
        """
        start_time = time.time()

        while time.time() - start_time < self.file_lock_timeout:
            try:
                if platform.system() == "Windows" and "msvcrt" in globals():
                    # Windows file locking
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore
                else:
                    # Unix file locking
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                logging.debug(
                    f"File lock acquired for {getattr(file_handle, 'name', 'unknown file')}"
                )
                return True

            except (IOError, OSError):
                time.sleep(0.1)  # Wait before retry
                continue

        logging.warning(
            f"File lock timeout after {self.file_lock_timeout}s for {getattr(file_handle, 'name', 'unknown file')}"
        )
        return False

    def _release_file_lock(self, file_handle) -> None:
        """
        Release file lock.

        Args:
            file_handle: Open file handle to unlock
        """
        try:
            if platform.system() == "Windows" and "msvcrt" in globals():
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore
            else:
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)

            logging.debug(
                f"File lock released for {getattr(file_handle, 'name', 'unknown file')}"
            )

        except (IOError, OSError) as e:
            logging.warning(f"Failed to release file lock: {e}")

    def _create_backup(self) -> None:
        """
        Create backup of current storage file with rotation.

        Maintains backup_retention_count number of backup files.
        """
        if not self.storage_path or not self.backup_dir:
            return

        storage_file = Path(self.storage_path)
        if not storage_file.exists():
            return

        try:
            # Generate timestamped backup filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:-3]
            backup_filename = f"sync_jobs_{timestamp}.json"
            backup_path = self.backup_dir / backup_filename

            # Copy current storage to backup
            with open(storage_file, "r") as src:
                backup_content = src.read()

            with open(backup_path, "w") as backup:
                backup.write(backup_content)

            logging.debug(f"Created backup: {backup_path}")

            # Rotate old backups
            self._rotate_backups()

        except Exception as e:
            logging.warning(f"Failed to create backup: {e}")

    def _rotate_backups(self) -> None:
        """
        Rotate backup files, keeping only the most recent backup_retention_count files.
        """
        if not self.backup_dir:
            return

        try:
            # Get all backup files
            backup_files = list(self.backup_dir.glob("sync_jobs_*.json"))

            # Sort by modification time (newest first)
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

            # Remove excess backups
            if len(backup_files) > self.backup_retention_count:
                files_to_remove = backup_files[self.backup_retention_count :]
                for backup_file in files_to_remove:
                    try:
                        backup_file.unlink()
                        logging.debug(f"Removed old backup: {backup_file}")
                    except Exception as e:
                        logging.warning(
                            f"Failed to remove old backup {backup_file}: {e}"
                        )

        except Exception as e:
            logging.warning(f"Failed to rotate backups: {e}")

    def _calculate_data_checksum(self, data: Dict[str, Any]) -> str:
        """
        Calculate checksum for data integrity validation.

        Args:
            data: Job data dictionary

        Returns:
            Hex checksum string
        """
        # Create deterministic JSON representation
        json_str = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()

    def _cleanup_stale_temp_files(self) -> None:
        """
        Clean up stale temporary files on initialization.

        Removes temp files older than 1 hour to prevent accumulation
        from interrupted operations.
        """
        if not self.storage_path:
            return

        storage_dir = Path(self.storage_path).parent
        temp_patterns = [
            f"{Path(self.storage_path).name}.tmp",
            f"{Path(self.storage_path).name}.backup",
            f"{Path(self.storage_path).name}.recovery",
            f"{Path(self.storage_path).name}.lock",
        ]

        current_time = time.time()
        stale_threshold = 3600  # 1 hour

        for pattern in temp_patterns:
            temp_files = list(storage_dir.glob(pattern))
            for temp_file in temp_files:
                try:
                    file_age = current_time - temp_file.stat().st_mtime
                    if file_age > stale_threshold:
                        temp_file.unlink()
                        logging.debug(f"Cleaned up stale temp file: {temp_file}")
                except Exception as e:
                    logging.warning(
                        f"Failed to clean up stale temp file {temp_file}: {e}"
                    )

    def create_job(
        self,
        username: str,
        user_alias: str,
        job_type: JobType,
        repository_url: Optional[str] = None,
    ) -> str:
        """
        Create a new sync job with unique job ID and concurrency control.

        Args:
            username: Username of the job creator
            user_alias: Display name of the job creator
            job_type: Type of sync job to create
            repository_url: Repository URL for sync operations (optional)

        Returns:
            Unique job ID for the created job

        Raises:
            InvalidJobParametersError: If parameters are invalid
            DuplicateJobIdError: If generated job ID already exists (very unlikely)
            ConcurrencyLimitExceededError: If user concurrency limits exceeded
            DuplicateRepositorySyncError: If repository is already being synced
            ResourceLimitExceededError: If system resource limits exceeded
        """
        # Validate parameters
        if not username or not username.strip():
            raise InvalidJobParametersError("Username cannot be empty")

        if not user_alias or not user_alias.strip():
            raise InvalidJobParametersError("User alias cannot be empty")

        if not isinstance(job_type, JobType):
            raise InvalidJobParametersError(f"Invalid job type: {job_type}")

        username = username.strip()
        user_alias = user_alias.strip()

        with self._lock:
            # Check resource limits first
            self._check_resource_limits()

            # Check for repository conflict if repository URL provided
            if repository_url:
                conflict_job_id = self._check_repository_conflict(repository_url)
                if conflict_job_id:
                    raise DuplicateRepositorySyncError(repository_url, conflict_job_id)

            # Get effective concurrency limits
            limits = self._get_effective_concurrency_limits()

            # Count current running jobs
            user_running_count = self._count_user_running_jobs(username)
            total_running_count = self._count_total_running_jobs()

            # Generate unique job ID
            job_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc)

            # Determine initial job status
            can_run_immediately = (
                user_running_count < limits["max_concurrent_jobs_per_user"]
                and total_running_count < limits["max_total_concurrent_jobs"]
            )

            if can_run_immediately:
                initial_status = JobStatus.RUNNING
                started_at = created_at
                queued_at = None
                queue_position = None
                estimated_wait_minutes = None

                # Acquire repository lock if needed
                if repository_url:
                    self._acquire_repository_lock(repository_url, job_id)

            else:
                initial_status = JobStatus.QUEUED
                started_at = None
                queued_at = created_at
                queue_position = len(self._job_queue) + 1
                estimated_wait_minutes = (
                    queue_position * self.average_job_duration_minutes
                )

            # Create sync job instance
            sync_job = SyncJob(
                job_id=job_id,
                username=username,
                user_alias=user_alias,
                job_type=job_type,
                status=initial_status,
                created_at=created_at,
                started_at=started_at,
                queued_at=queued_at,
                repository_url=repository_url,
                queue_position=queue_position,
                estimated_wait_minutes=estimated_wait_minutes,
            )

            # Check for duplicate job ID (extremely unlikely with UUID4)
            if job_id in self._jobs:
                raise DuplicateJobIdError(job_id)

            # Store job
            self._jobs[job_id] = sync_job

            # Add to queue if necessary
            if initial_status == JobStatus.QUEUED:
                self._job_queue.append(job_id)
                self._update_queue_positions()

            # Persist jobs
            self._persist_jobs()

        if initial_status == JobStatus.RUNNING:
            logging.info(f"Created and started sync job {job_id} for user {username}")
        else:
            logging.info(
                f"Created queued sync job {job_id} for user {username} (position {queue_position})"
            )

        return job_id

    def get_job(self, job_id: str) -> Dict[str, Any]:
        """
        Retrieve job details by job ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Job details as dictionary

        Raises:
            JobNotFoundError: If job ID doesn't exist
        """
        if not job_id or not job_id.strip():
            raise JobNotFoundError(job_id)

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)

            # Return serialized job data
            job_dict: Dict[str, Any] = job.model_dump()
            return job_dict

    def list_all_jobs(self) -> List[Dict[str, Any]]:
        """
        List all jobs in the system.

        Returns:
            List of job dictionaries sorted by creation time (newest first)
        """
        with self._lock:
            jobs = list(self._jobs.values())

        # Sort by creation time (newest first)
        jobs.sort(key=lambda job: job.created_at, reverse=True)

        # Return serialized job data
        return [job.model_dump() for job in jobs]

    def mark_job_completed(
        self, job_id: str, error_message: Optional[str] = None
    ) -> None:
        """
        Mark a job as completed or failed and advance the queue.

        Args:
            job_id: Job ID to mark as completed
            error_message: Error message if job failed (optional)

        Raises:
            JobNotFoundError: If job ID doesn't exist
            InvalidJobStateTransitionError: If job is not in running state
        """
        if not job_id or not job_id.strip():
            raise JobNotFoundError(job_id)

        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            # Validate state transition
            if job.status != JobStatus.RUNNING:
                raise InvalidJobStateTransitionError(
                    job_id, job.status.value, "completed/failed"
                )

            # Update job status
            completed_at = datetime.now(timezone.utc)
            if error_message:
                job.status = JobStatus.FAILED
                job.error_message = error_message
                logging.info(f"Job {job_id} failed: {error_message}")
            else:
                job.status = JobStatus.COMPLETED
                job.progress = 100
                logging.info(f"Job {job_id} completed successfully")

            job.completed_at = completed_at

            # Release repository lock if held
            if job.repository_url:
                self._release_repository_lock(job.repository_url)

            # Advance queue to start next jobs
            self._advance_queue()

            # Persist changes
            self._persist_jobs()

    def cancel_job(self, job_id: str) -> None:
        """
        Cancel a job (running or queued).

        Args:
            job_id: Job ID to cancel

        Raises:
            JobNotFoundError: If job ID doesn't exist
            InvalidJobStateTransitionError: If job cannot be cancelled
        """
        if not job_id or not job_id.strip():
            raise JobNotFoundError(job_id)

        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            # Check if job can be cancelled
            if job.status in [
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ]:
                raise InvalidJobStateTransitionError(
                    job_id, job.status.value, "cancelled"
                )

            # Cancel the job
            old_status = job.status
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)

            # Release repository lock if held
            if job.repository_url and old_status == JobStatus.RUNNING:
                self._release_repository_lock(job.repository_url)

            # Remove from queue if queued
            if old_status == JobStatus.QUEUED and job_id in self._job_queue:
                self._job_queue.remove(job_id)
                self._update_queue_positions()

            # Advance queue if this was a running job
            if old_status == JobStatus.RUNNING:
                self._advance_queue()

            # Persist changes
            self._persist_jobs()

            logging.info(f"Job {job_id} cancelled by user request")

    def cancel_queued_job(self, job_id: str) -> None:
        """
        Cancel a specifically queued job (not running jobs).

        Args:
            job_id: Job ID to cancel (must be queued)

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If job is not queued
        """
        if not job_id or not job_id.strip():
            raise JobNotFoundError(job_id)

        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if job.status != JobStatus.QUEUED:
                raise ValueError(
                    f"Cannot cancel running job {job_id} through queue operations"
                )

            # Cancel the queued job
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now(timezone.utc)

            # Remove from queue
            if job_id in self._job_queue:
                self._job_queue.remove(job_id)
                self._update_queue_positions()

            # Persist changes
            self._persist_jobs()

            logging.info(f"Queued job {job_id} cancelled")

    def get_user_queue_status(self, username: str) -> Dict[str, Any]:
        """
        Get queue status for a specific user.

        Args:
            username: Username to get queue status for

        Returns:
            Dictionary with user's queue status
        """
        with self._lock:
            running_jobs = []
            queued_jobs = []

            for job in self._jobs.values():
                if job.username == username:
                    job_dict = job.model_dump()
                    if job.status == JobStatus.RUNNING:
                        running_jobs.append(job_dict)
                    elif job.status == JobStatus.QUEUED:
                        queued_jobs.append(job_dict)

            # Sort queued jobs by queue position
            queued_jobs.sort(key=lambda x: x.get("queue_position", 0))

            return {
                "username": username,
                "running_jobs": running_jobs,
                "queued_jobs": queued_jobs,
                "total_running": len(running_jobs),
                "total_queued": len(queued_jobs),
                "next_queue_position": (
                    queued_jobs[0].get("queue_position") if queued_jobs else None
                ),
                "estimated_next_start_minutes": (
                    queued_jobs[0].get("estimated_wait_minutes")
                    if queued_jobs
                    else None
                ),
            }

    def get_global_queue_status(self) -> Dict[str, Any]:
        """
        Get global queue status across all users.

        Returns:
            Dictionary with global queue status
        """
        with self._lock:
            total_running = 0
            total_queued = 0
            queue_by_user = {}

            for job in self._jobs.values():
                username = job.username
                if username not in queue_by_user:
                    queue_by_user[username] = {"running": 0, "queued": 0}

                if job.status == JobStatus.RUNNING:
                    total_running += 1
                    queue_by_user[username]["running"] += 1
                elif job.status == JobStatus.QUEUED:
                    total_queued += 1
                    queue_by_user[username]["queued"] += 1

            # Calculate average wait time
            if total_queued > 0:
                average_position = (total_queued + 1) / 2  # Average queue position
                average_wait_time = average_position * self.average_job_duration_minutes
            else:
                average_wait_time = 0

            return {
                "total_running": total_running,
                "total_queued": total_queued,
                "queue_by_user": queue_by_user,
                "average_wait_time_minutes": int(average_wait_time),
                "system_in_degraded_mode": self.is_in_degraded_mode(),
                "effective_limits": self._get_effective_concurrency_limits(),
            }

    def cancel_all_queued_jobs_for_user(self, username: str) -> int:
        """
        Cancel all queued jobs for a specific user.

        Args:
            username: Username whose queued jobs to cancel

        Returns:
            Number of jobs cancelled
        """
        with self._lock:
            jobs_to_cancel = []

            # Find all queued jobs for the user
            for job_id, job in self._jobs.items():
                if job.username == username and job.status == JobStatus.QUEUED:
                    jobs_to_cancel.append(job_id)

            # Cancel each job
            for job_id in jobs_to_cancel:
                job = self._jobs[job_id]
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)

                # Remove from queue
                if job_id in self._job_queue:
                    self._job_queue.remove(job_id)

            # Update queue positions for remaining jobs
            if jobs_to_cancel:
                self._update_queue_positions()
                self._persist_jobs()

                logging.info(
                    f"Cancelled {len(jobs_to_cancel)} queued jobs for user {username}"
                )

            return len(jobs_to_cancel)

    def _persist_jobs(self) -> None:
        """
        Persist jobs to storage file with resilient features.

        Includes file locking, backup creation, and data integrity validation.
        Note: This method should be called within a lock.

        Raises:
            JobPersistenceError: If persistence fails
        """
        if not self.storage_path:
            return

        storage_file = Path(self.storage_path)
        temp_file = Path(f"{self.storage_path}.tmp")

        try:
            storage_file.parent.mkdir(parents=True, exist_ok=True)

            # Create backup of current file before modifications (only if file exists)
            if storage_file.exists():
                self._create_backup()

            # Convert jobs to serializable format
            serializable_jobs = {}
            for job_id, job in self._jobs.items():
                job_dict = job.model_dump()
                serializable_jobs[job_id] = job_dict

            # Add metadata for integrity validation
            metadata = {
                "_metadata": {
                    "version": "1.0",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "job_count": len(serializable_jobs),
                    "checksum": self._calculate_data_checksum(serializable_jobs),
                }
            }

            # Combine job data with metadata
            complete_data = {**serializable_jobs, **metadata}

            # Use a lock file for process coordination
            lock_file = Path(f"{self.storage_path}.lock")
            lock_acquired = False

            try:
                # Try to acquire process lock
                start_time = time.time()
                while time.time() - start_time < self.file_lock_timeout:
                    try:
                        # Create lock file with exclusive creation
                        with open(lock_file, "x") as lock_f:
                            lock_f.write(str(os.getpid()))
                        lock_acquired = True
                        logging.debug(f"Acquired process lock {lock_file}")
                        break
                    except FileExistsError:
                        time.sleep(0.1)
                        continue

                if not lock_acquired:
                    raise JobPersistenceError(
                        f"Failed to acquire process lock after {self.file_lock_timeout}s"
                    )

                # Write to temporary file
                with open(temp_file, "w") as f:
                    json.dump(complete_data, f, indent=2)
                    f.flush()  # Ensure data is written
                    os.fsync(f.fileno())  # Force write to disk
                    logging.debug(
                        f"Wrote {len(serializable_jobs)} jobs to temp file with checksum: {cast(Dict[str, Any], metadata['_metadata'])['checksum'][:8]}..."
                    )

                # Atomic rename only after successful write
                temp_file.rename(storage_file)

            finally:
                # Always clean up lock file
                if lock_acquired:
                    try:
                        lock_file.unlink()
                        logging.debug(f"Released process lock {lock_file}")
                    except FileNotFoundError:
                        pass

            logging.debug(
                f"Persisted {len(serializable_jobs)} jobs to {storage_file} with backup and integrity validation"
            )

        except Exception as e:
            # Clean up temp file on error
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

            error_msg = f"Failed to persist jobs to {self.storage_path}: {e}"
            logging.error(error_msg)
            raise JobPersistenceError(error_msg, e)

    def _load_jobs(self) -> None:
        """
        Load jobs from storage file with resilient recovery mechanisms.

        Includes data integrity validation, corruption recovery, and incomplete
        operation detection. Handles missing files and corrupted data gracefully.
        """
        if not self.storage_path:
            return

        # Check for incomplete operations and attempt recovery
        recovery_attempted = self._attempt_recovery_from_incomplete_operations()

        try:
            storage_file = Path(self.storage_path)
            if not storage_file.exists():
                if recovery_attempted:
                    logging.info(
                        "Recovery operation completed, but no valid storage file found"
                    )
                else:
                    logging.debug(
                        f"Storage file {storage_file} does not exist - starting with empty jobs"
                    )
                return

            # Load and validate data
            with open(storage_file, "r") as f:
                stored_data = json.load(f)

            # Validate data integrity
            self._validate_data_integrity(stored_data, storage_file)

            # Extract job data (excluding metadata)
            job_data = {k: v for k, v in stored_data.items() if not k.startswith("_")}

            loaded_count = 0
            corrupted_count = 0

            for job_id, job_dict in job_data.items():
                try:
                    # Validate job data structure
                    if not self._validate_job_data_structure(job_dict):
                        logging.warning(
                            f"Job {job_id} has invalid data structure, skipping"
                        )
                        corrupted_count += 1
                        continue

                    # Convert string dates back to datetime objects
                    for field in ["created_at", "started_at", "completed_at"]:
                        if job_dict.get(field):
                            job_dict[field] = datetime.fromisoformat(job_dict[field])

                    # Create job object from loaded data
                    job = SyncJob(**job_dict)
                    self._jobs[job_id] = job
                    loaded_count += 1

                except Exception as job_error:
                    logging.warning(f"Failed to load job {job_id}: {job_error}")
                    corrupted_count += 1
                    continue

            if corrupted_count > 0:
                logging.warning(f"Skipped {corrupted_count} corrupted jobs during load")

            logging.info(
                f"Loaded {loaded_count} jobs from storage (skipped {corrupted_count} corrupted)"
            )

        except json.JSONDecodeError as e:
            logging.warning(
                f"Storage file {self.storage_path} contains invalid JSON: {e}"
            )

            # Attempt recovery from backup
            if self._attempt_recovery_from_backup():
                logging.info("Successfully recovered from backup after JSON corruption")
                # Recursive call after recovery
                self._load_jobs()
                return
            else:
                logging.info(
                    "No backup available for recovery, starting with empty jobs"
                )

        except Exception as e:
            logging.error(f"Failed to load jobs from storage: {e}")
            logging.info("Starting with empty jobs")

    def _validate_data_integrity(
        self, stored_data: Dict[str, Any], storage_file: Path
    ) -> None:
        """
        Validate data integrity using checksum verification.

        Args:
            stored_data: Loaded data from storage file
            storage_file: Path to storage file for logging
        """
        if "_metadata" not in stored_data:
            logging.debug(
                f"No metadata found in {storage_file}, skipping integrity validation"
            )
            return

        metadata = stored_data["_metadata"]
        if "checksum" not in metadata:
            logging.debug(
                "No checksum found in metadata, skipping integrity validation"
            )
            return

        # Extract job data for checksum calculation
        job_data = {k: v for k, v in stored_data.items() if not k.startswith("_")}
        calculated_checksum = self._calculate_data_checksum(job_data)
        stored_checksum = metadata["checksum"]

        if calculated_checksum != stored_checksum:
            logging.warning(
                f"Data integrity validation failed for {storage_file}. "
                f"Expected checksum: {stored_checksum[:8]}..., "
                f"Calculated checksum: {calculated_checksum[:8]}..."
            )
        else:
            logging.debug(f"Data integrity validation passed for {storage_file}")

    def _validate_job_data_structure(self, job_dict: Dict[str, Any]) -> bool:
        """
        Validate that job data contains required fields.

        Args:
            job_dict: Job data dictionary

        Returns:
            True if job data is valid, False otherwise
        """
        required_fields = [
            "job_id",
            "username",
            "user_alias",
            "job_type",
            "status",
            "created_at",
        ]

        for field in required_fields:
            if field not in job_dict:
                return False

        return True

    def _attempt_recovery_from_incomplete_operations(self) -> bool:
        """
        Attempt recovery from incomplete write operations.

        Looks for temp files that might contain more recent data than main file.
        Only attempts recovery if temp file is significantly older than current time
        to avoid interfering with concurrent operations.

        Returns:
            True if recovery was attempted, False otherwise
        """
        if not self.storage_path:
            return False

        storage_file = Path(self.storage_path)
        temp_file = Path(f"{self.storage_path}.tmp")

        # Check if temp file exists
        if temp_file.exists():
            try:
                temp_mtime = temp_file.stat().st_mtime
                current_time = time.time()
                main_mtime = (
                    storage_file.stat().st_mtime if storage_file.exists() else 0
                )

                # Only attempt recovery if temp file is at least 5 seconds old
                # This prevents interference with concurrent operations
                age_threshold = 5.0  # seconds
                temp_age = current_time - temp_mtime

                if temp_age > age_threshold and temp_mtime > main_mtime:
                    logging.info(
                        f"Found old temp file {temp_file} ({temp_age:.1f}s old), attempting recovery"
                    )

                    # Validate temp file before using it
                    with open(temp_file, "r") as f:
                        json.load(f)

                    # If valid, use it as the main file
                    temp_file.rename(storage_file)
                    logging.info(
                        f"Successfully recovered from incomplete operation using {temp_file}"
                    )
                    return True
                elif temp_age > age_threshold:
                    # Temp file is old but not newer than main file, remove it
                    temp_file.unlink()
                    logging.debug(f"Removed old temp file {temp_file}")
                else:
                    # Temp file is recent, leave it alone (concurrent operation in progress)
                    logging.debug(
                        f"Found recent temp file {temp_file} ({temp_age:.1f}s old), leaving it for concurrent operation"
                    )

            except Exception as e:
                logging.warning(f"Failed to recover from temp file {temp_file}: {e}")
                # Only remove if file is old enough to be considered stale
                try:
                    temp_mtime = temp_file.stat().st_mtime
                    temp_age = time.time() - temp_mtime
                    if temp_age > 60:  # Only remove files older than 1 minute on error
                        temp_file.unlink()
                        logging.debug(f"Removed problematic temp file {temp_file}")
                except Exception:
                    pass

        return False

    def _attempt_recovery_from_backup(self) -> bool:
        """
        Attempt recovery from the most recent backup file.

        Returns:
            True if recovery was successful, False otherwise
        """
        if not self.backup_dir:
            return False

        try:
            # Find the most recent backup file
            backup_files = list(self.backup_dir.glob("sync_jobs_*.json"))
            if not backup_files:
                logging.debug("No backup files found for recovery")
                return False

            # Sort by modification time (newest first)
            backup_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            latest_backup = backup_files[0]

            logging.info(f"Attempting recovery from backup: {latest_backup}")

            # Validate backup file
            with open(latest_backup, "r") as f:
                json.load(f)

            # Copy backup to main storage file
            storage_file = Path(self.storage_path) if self.storage_path else Path()
            with open(latest_backup, "r") as src, open(storage_file, "w") as dst:
                dst.write(src.read())

            logging.info(f"Successfully recovered from backup {latest_backup}")
            return True

        except Exception as e:
            logging.error(f"Failed to recover from backup: {e}")
            return False

    def _normalize_repository_url(self, repo_url: str) -> str:
        """
        Normalize repository URL for duplicate detection.

        Args:
            repo_url: Repository URL to normalize

        Returns:
            Normalized URL string
        """
        if not repo_url:
            return repo_url

        # Convert SSH to HTTPS format for normalization
        if repo_url.startswith("git@"):
            # Convert git@github.com:user/repo.git to https://github.com/user/repo.git
            ssh_match = re.match(r"git@([^:]+):(.+)", repo_url)
            if ssh_match:
                host, path = ssh_match.groups()
                repo_url = f"https://{host}/{path}"

        # Parse URL and normalize
        parsed = urlparse(repo_url.lower())

        # Remove .git suffix if present
        path = parsed.path
        if path.endswith(".git"):
            path = path[:-4]

        # Normalize path separators
        path = path.strip("/").replace("//", "/")

        return f"{parsed.scheme}://{parsed.netloc}/{path}"

    def _get_resource_metrics(self) -> Dict[str, Any]:
        """
        Get current system resource metrics.

        Returns:
            Dictionary with resource usage metrics
        """
        current_time = time.time()

        # Use cached metrics if recent enough
        if (
            self._cached_resource_metrics
            and current_time - self._last_resource_check
            < self.resource_check_interval_seconds
        ):
            return self._cached_resource_metrics

        metrics = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "active_jobs_count": 0,
            "queued_jobs_count": 0,
            "system_load_average": 0.0,
            "timestamp": current_time,
        }

        if PSUTIL_AVAILABLE:
            try:
                # Get CPU and memory usage (non-blocking)
                metrics["cpu_percent"] = psutil.cpu_percent(
                    interval=None
                )  # Use non-blocking call
                metrics["memory_percent"] = psutil.virtual_memory().percent

                # Get system load average (Unix only)
                if hasattr(os, "getloadavg"):
                    metrics["system_load_average"] = os.getloadavg()[0]

            except Exception as e:
                logging.warning(f"Failed to get resource metrics: {e}")

        # Count active and queued jobs
        # Note: Don't acquire lock here as this method might be called from within a lock
        # Use thread-safe iteration
        jobs_snapshot = dict(self._jobs)  # Shallow copy for safe iteration
        for job in jobs_snapshot.values():
            if job.status == JobStatus.RUNNING:
                metrics["active_jobs_count"] += 1
            elif job.status == JobStatus.QUEUED:
                metrics["queued_jobs_count"] += 1

        # Cache the metrics
        self._cached_resource_metrics = metrics
        self._last_resource_check = current_time

        return metrics

    def get_resource_metrics(self) -> Dict[str, Any]:
        """
        Public method to get resource metrics.

        Returns:
            Dictionary with current resource usage metrics
        """
        return self._get_resource_metrics()

    def _check_resource_limits(self) -> None:
        """
        Check if current resource usage exceeds limits.

        Raises:
            ResourceLimitExceededError: If resource limits are exceeded
        """
        metrics = self._get_resource_metrics()

        if metrics["cpu_percent"] > self.max_cpu_percent:
            raise ResourceLimitExceededError(
                "CPU usage", metrics["cpu_percent"], self.max_cpu_percent
            )

        if metrics["memory_percent"] > self.max_memory_percent:
            raise ResourceLimitExceededError(
                "Memory usage", metrics["memory_percent"], self.max_memory_percent
            )

    def is_in_degraded_mode(self) -> bool:
        """
        Check if system is in degraded mode due to resource usage.

        Returns:
            True if system is in degraded mode
        """
        metrics = self._get_resource_metrics()

        return bool(
            metrics["cpu_percent"] > self.degraded_mode_cpu_threshold
            or metrics["memory_percent"] > self.degraded_mode_memory_threshold
        )

    def _get_effective_concurrency_limits(self) -> Dict[str, int]:
        """
        Get effective concurrency limits (normal or degraded mode).

        Returns:
            Dictionary with effective concurrency limits
        """
        if self.is_in_degraded_mode():
            return {
                "max_concurrent_jobs_per_user": self.degraded_max_concurrent_jobs_per_user,
                "max_total_concurrent_jobs": self.degraded_max_total_concurrent_jobs,
            }
        else:
            return {
                "max_concurrent_jobs_per_user": self.max_concurrent_jobs_per_user,
                "max_total_concurrent_jobs": self.max_total_concurrent_jobs,
            }

    def _count_user_running_jobs(self, username: str) -> int:
        """
        Count running jobs for a specific user.

        Args:
            username: Username to count jobs for

        Returns:
            Number of running jobs for the user
        """
        count = 0
        for job in self._jobs.values():
            if job.username == username and job.status == JobStatus.RUNNING:
                count += 1
        return count

    def _count_total_running_jobs(self) -> int:
        """
        Count total running jobs across all users.

        Returns:
            Total number of running jobs
        """
        count = 0
        for job in self._jobs.values():
            if job.status == JobStatus.RUNNING:
                count += 1
        return count

    def _check_repository_conflict(self, repository_url: str) -> Optional[str]:
        """
        Check if repository is already being synced.

        Args:
            repository_url: Repository URL to check

        Returns:
            Job ID of existing sync operation, or None if no conflict
        """
        normalized_url = self._normalize_repository_url(repository_url)
        return self._repository_locks.get(normalized_url)

    def _acquire_repository_lock(self, repository_url: str, job_id: str) -> None:
        """
        Acquire lock for repository sync operation.

        Args:
            repository_url: Repository URL to lock
            job_id: Job ID acquiring the lock
        """
        normalized_url = self._normalize_repository_url(repository_url)
        self._repository_locks[normalized_url] = job_id

    def _release_repository_lock(self, repository_url: str) -> None:
        """
        Release lock for repository sync operation.

        Args:
            repository_url: Repository URL to unlock
        """
        normalized_url = self._normalize_repository_url(repository_url)
        self._repository_locks.pop(normalized_url, None)

    def _update_queue_positions(self) -> None:
        """
        Update queue positions and estimated wait times for queued jobs.

        This method should be called whenever the queue changes.
        """
        position = 1
        for job_id in self._job_queue:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                if job.status == JobStatus.QUEUED:
                    # Update queue position
                    job.queue_position = position

                    # Calculate estimated wait time
                    job.estimated_wait_minutes = (
                        position * self.average_job_duration_minutes
                    )

                    position += 1

    def _advance_queue(self) -> None:
        """
        Advance queued jobs to running status when slots become available.

        This method processes the queue and starts jobs that can run.
        """
        limits = self._get_effective_concurrency_limits()

        # Process queue in FIFO order and start jobs one by one
        jobs_started = 0

        for job_id in list(
            self._job_queue
        ):  # Copy list to avoid modification during iteration
            if job_id not in self._jobs:
                # Job was removed, clean up queue
                self._job_queue.remove(job_id)
                continue

            job = self._jobs[job_id]
            if job.status != JobStatus.QUEUED:
                # Job is no longer queued, remove from queue
                self._job_queue.remove(job_id)
                continue

            # Check if job can start running (recalculate for each job)
            user_running_count = self._count_user_running_jobs(job.username)
            total_running_count = self._count_total_running_jobs()

            can_start = (
                user_running_count < limits["max_concurrent_jobs_per_user"]
                and total_running_count < limits["max_total_concurrent_jobs"]
            )

            if can_start:
                # Check repository conflict
                if job.repository_url:
                    conflict_job_id = self._check_repository_conflict(
                        job.repository_url
                    )
                    if conflict_job_id and conflict_job_id != job_id:
                        # Repository is still locked by another job, skip this job
                        continue

                # Start this job
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc)
                job.queue_position = None
                job.estimated_wait_minutes = None

                # Acquire repository lock if needed
                if job.repository_url:
                    self._acquire_repository_lock(job.repository_url, job_id)

                # Remove from queue
                self._job_queue.remove(job_id)

                logging.info(f"Started queued job {job_id} for user {job.username}")
                jobs_started += 1

                # Continue to next job in queue to see if more can start
            else:
                # Can't start this job due to limits, stop processing queue
                break

        # Update positions for remaining queued jobs
        self._update_queue_positions()

    # Multi-phase job support methods

    def create_job_with_phases(
        self,
        username: str,
        user_alias: str,
        job_type: JobType,
        phases: List[str],
        repository_url: Optional[str] = None,
        phase_weights: Optional[Dict[str, float]] = None,
    ) -> str:
        """
        Create a new sync job with multi-phase tracking support.

        Args:
            username: Username of the job creator
            user_alias: Display name of the job creator
            job_type: Type of sync job to create
            phases: List of phase names for this job
            repository_url: Repository URL for sync operations (optional)
            phase_weights: Weight of each phase for progress calculation

        Returns:
            Unique job ID for the created job

        Raises:
            InvalidJobParametersError: If parameters are invalid
            DuplicateJobIdError: If generated job ID already exists (very unlikely)
            ConcurrencyLimitExceededError: If user concurrency limits exceeded
            DuplicateRepositorySyncError: If repository is already being synced
            ResourceLimitExceededError: If system resource limits exceeded
        """
        # Use standard job creation first
        job_id = self.create_job(
            username=username,
            user_alias=user_alias,
            job_type=job_type,
            repository_url=repository_url,
        )

        # Enhance job with phase information
        with self._lock:
            job = self._jobs[job_id]

            # Initialize phases
            from .models import JobPhase, PhaseStatus

            job_phases = {}
            for phase_name in phases:
                job_phases[phase_name] = JobPhase(
                    phase_name=phase_name, status=PhaseStatus.PENDING
                )

            # Set phase information
            job.phases = job_phases
            job.current_phase = phases[0] if phases else None
            job.phase_weights = phase_weights or {
                phase: 1.0 / len(phases) for phase in phases
            }

            # Persist changes
            self._persist_jobs()

        logging.info(f"Created multi-phase job {job_id} with phases: {phases}")
        return job_id

    def start_phase(self, job_id: str, phase_name: str) -> None:
        """
        Start a specific phase of a job.

        Args:
            job_id: Job ID
            phase_name: Name of phase to start

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If phase doesn't exist
            InvalidJobStateTransitionError: If phase cannot be started
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if not job.phases or phase_name not in job.phases:
                raise ValueError(f"Phase '{phase_name}' not found in job {job_id}")

            phase = job.phases[phase_name]

            if phase.status != "pending":
                raise InvalidJobStateTransitionError(job_id, phase.status, "running")

            # Start phase
            from .models import PhaseStatus

            phase.status = PhaseStatus.RUNNING
            phase.started_at = datetime.now(timezone.utc)
            job.current_phase = phase_name

            # Persist changes
            self._persist_jobs()

        logging.debug(f"Started phase '{phase_name}' for job {job_id}")

    def update_phase_progress(
        self,
        job_id: str,
        phase: str,
        progress: Optional[int] = None,
        status: Optional[str] = None,
        info: Optional[str] = None,
        current_file: Optional[str] = None,
        files_processed: Optional[int] = None,
        total_files: Optional[int] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Update progress for a specific phase.

        Args:
            job_id: Job ID
            phase: Phase name
            progress: Progress percentage (0-100)
            status: Phase status
            info: Progress information
            current_file: Current file being processed
            files_processed: Number of files processed
            total_files: Total number of files
            metrics: Additional metrics

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If phase doesn't exist
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if not job.phases or phase not in job.phases:
                raise ValueError(f"Unknown phase '{phase}' for job {job_id}")

            job_phase = job.phases[phase]

            # Update phase information
            if progress is not None:
                job_phase.progress = max(0, min(100, progress))
            if status is not None:
                job_phase.status = PhaseStatus(status)
            if info is not None:
                job_phase.info = info
            if current_file is not None:
                job_phase.current_file = current_file
            if files_processed is not None:
                job_phase.files_processed = files_processed
            if total_files is not None:
                job_phase.total_files = total_files
            if metrics is not None:
                job_phase.metrics = metrics

            # Update overall job progress based on phase weights
            self._calculate_overall_progress(job)

            # Persist changes
            self._persist_jobs()

    def complete_phase(
        self,
        job_id: str,
        phase: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark a phase as completed.

        Args:
            job_id: Job ID
            phase: Phase name
            result: Phase result data

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If phase doesn't exist
            InvalidJobStateTransitionError: If phase is already completed
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if not job.phases or phase not in job.phases:
                raise ValueError(f"Unknown phase '{phase}' for job {job_id}")

            job_phase = job.phases[phase]

            if job_phase.status == "completed":
                raise InvalidJobStateTransitionError(
                    job_id, job_phase.status, "completed"
                )

            # Complete phase
            from .models import PhaseStatus

            completed_at = datetime.now(timezone.utc)
            job_phase.status = PhaseStatus.COMPLETED
            job_phase.completed_at = completed_at
            job_phase.progress = 100
            job_phase.result = result

            # Calculate duration if phase was started
            if job_phase.started_at:
                duration = (completed_at - job_phase.started_at).total_seconds()
                job_phase.duration_seconds = duration

            # Move to next phase or mark job complete
            self._advance_to_next_phase(job)

            # Update overall progress
            self._calculate_overall_progress(job)

            # Persist changes
            self._persist_jobs()

        logging.debug(f"Completed phase '{phase}' for job {job_id}")

    def fail_phase(
        self,
        job_id: str,
        phase: str,
        error_message: str,
        error_code: Optional[str] = None,
    ) -> None:
        """
        Mark a phase as failed.

        Args:
            job_id: Job ID
            phase: Phase name
            error_message: Error message
            error_code: Error code

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If phase doesn't exist
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if not job.phases or phase not in job.phases:
                raise ValueError(f"Unknown phase '{phase}' for job {job_id}")

            job_phase = job.phases[phase]

            # Fail phase
            from .models import PhaseStatus

            completed_at = datetime.now(timezone.utc)
            job_phase.status = PhaseStatus.FAILED
            job_phase.completed_at = completed_at
            job_phase.error_message = error_message
            job_phase.error_code = error_code

            # Calculate duration if phase was started
            if job_phase.started_at:
                duration = (completed_at - job_phase.started_at).total_seconds()
                job_phase.duration_seconds = duration

            # Mark entire job as failed
            job.status = JobStatus.FAILED
            job.error_message = f"Phase '{phase}' failed: {error_message}"
            job.completed_at = completed_at

            # Persist changes
            self._persist_jobs()

        logging.warning(f"Failed phase '{phase}' for job {job_id}: {error_message}")

    def skip_phase(
        self,
        job_id: str,
        phase: str,
        reason: str,
    ) -> None:
        """
        Skip a phase.

        Args:
            job_id: Job ID
            phase: Phase name
            reason: Reason for skipping

        Raises:
            JobNotFoundError: If job ID doesn't exist
            ValueError: If phase doesn't exist
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            if not job.phases or phase not in job.phases:
                raise ValueError(f"Unknown phase '{phase}' for job {job_id}")

            job_phase = job.phases[phase]

            # Skip phase
            from .models import PhaseStatus

            job_phase.status = PhaseStatus.SKIPPED
            job_phase.skip_reason = reason
            job_phase.progress = 100  # Consider skipped phases as complete for progress

            # Move to next phase or mark job complete
            self._advance_to_next_phase(job)

            # Update overall progress
            self._calculate_overall_progress(job)

            # Persist changes
            self._persist_jobs()

        logging.debug(f"Skipped phase '{phase}' for job {job_id}: {reason}")

    def _calculate_overall_progress(self, job: "SyncJob") -> None:
        """Calculate overall job progress from individual phases."""
        if not job.phases or not job.phase_weights:
            return

        total_progress = 0.0
        for phase_name, weight in job.phase_weights.items():
            if phase_name in job.phases:
                phase_progress = job.phases[phase_name].progress
                total_progress += weight * phase_progress

        job.progress = int(total_progress)

    def _advance_to_next_phase(self, job: "SyncJob") -> None:
        """Advance job to next phase or mark as complete."""
        if not job.phases:
            return

        # Find next pending phase
        phase_names = list(job.phases.keys())
        current_index = (
            phase_names.index(job.current_phase) if job.current_phase else -1
        )

        for i in range(current_index + 1, len(phase_names)):
            phase_name = phase_names[i]
            if job.phases[phase_name].status == "pending":
                job.current_phase = phase_name
                return

        # No more pending phases - check if job is complete
        all_phases_done = all(
            phase.status in ["completed", "skipped", "failed"]
            for phase in job.phases.values()
        )

        if all_phases_done:
            # Check if any phase failed
            any_failed = any(phase.status == "failed" for phase in job.phases.values())

            if not any_failed:
                job.status = JobStatus.COMPLETED
                job.current_phase = None
                if not job.completed_at:  # Don't overwrite if already set
                    job.completed_at = datetime.now(timezone.utc)

    # Progress State Persistence Methods - Story 15

    def update_job_progress(
        self,
        job_id: str,
        overall_progress: float,
        current_phase: Optional[str] = None,
        phase_progress: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> None:
        """
        Update job progress state with persistence.

        Args:
            job_id: Job ID to update
            overall_progress: Overall progress percentage (0-100)
            current_phase: Current phase name
            phase_progress: Progress by phase
            **kwargs: Additional progress metadata
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            job.overall_progress = overall_progress

            if current_phase is not None:
                job.current_phase = current_phase

            # Create progress history entry
            if job.progress_history is None:
                job.progress_history = []

            from .models import ProgressHistoryEntry

            history_entry = ProgressHistoryEntry(
                timestamp=datetime.now(timezone.utc),
                phase=current_phase or job.current_phase or "unknown",
                progress=overall_progress,
                files_processed=kwargs.get("files_processed"),
                total_files=kwargs.get("total_files"),
                info=kwargs.get("info"),
                processing_speed=kwargs.get("processing_speed"),
            )

            job.progress_history.append(history_entry)
            self._persist_jobs()

    def store_progress_state(self, job_id: str, progress_state: Dict[str, Any]) -> None:
        """
        Store comprehensive progress state for job.

        Args:
            job_id: Job ID to store state for
            progress_state: Complete progress state data
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]

            # Update fields from progress state
            if "overall_progress" in progress_state:
                job.overall_progress = progress_state["overall_progress"]
            if "current_phase" in progress_state:
                job.current_phase = progress_state["current_phase"]
            if "start_time" in progress_state:
                job.start_time = progress_state["start_time"]
            if "estimated_completion" in progress_state:
                job.estimated_completion = progress_state["estimated_completion"]

            self._persist_jobs()

    def append_progress_history(
        self, job_id: str, progress_update: Dict[str, Any]
    ) -> None:
        """
        Append progress update to job history.

        Args:
            job_id: Job ID to update
            progress_update: Progress update data
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            if job.progress_history is None:
                job.progress_history = []

            from .models import ProgressHistoryEntry

            history_entry = ProgressHistoryEntry(
                timestamp=progress_update.get("timestamp", datetime.now(timezone.utc)),
                phase=progress_update.get("phase", "unknown"),
                progress=progress_update.get("progress", 0.0),
                files_processed=progress_update.get("files_processed"),
                total_files=progress_update.get("total_files"),
                info=progress_update.get("info"),
                processing_speed=progress_update.get("processing_speed"),
            )

            job.progress_history.append(history_entry)
            self._persist_jobs()

    def create_recovery_checkpoint(
        self, job_id: str, checkpoint_data: Dict[str, Any]
    ) -> None:
        """
        Create recovery checkpoint for job.

        Args:
            job_id: Job ID to create checkpoint for
            checkpoint_data: Checkpoint data
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]

            from .models import RecoveryCheckpoint

            job.recovery_checkpoint = RecoveryCheckpoint(
                phase=checkpoint_data.get("phase", job.current_phase or "unknown"),
                progress=checkpoint_data.get("progress", job.overall_progress),
                last_file=checkpoint_data.get("last_file"),
                checkpoint_time=checkpoint_data.get(
                    "checkpoint_time", datetime.now(timezone.utc)
                ),
                metadata=checkpoint_data.get("metadata"),
            )

            self._persist_jobs()

    def get_recovery_checkpoint(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get recovery checkpoint for job.

        Args:
            job_id: Job ID to get checkpoint for

        Returns:
            Recovery checkpoint data or None if not found
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            if job.recovery_checkpoint is None:
                return None

            checkpoint = job.recovery_checkpoint
            return {
                "phase": checkpoint.phase,
                "progress": checkpoint.progress,
                "last_file": checkpoint.last_file,
                "checkpoint_time": checkpoint.checkpoint_time.isoformat(),
                "metadata": checkpoint.metadata,
            }

    def mark_job_interrupted(
        self, job_id: str, interruption_data: Dict[str, Any]
    ) -> None:
        """
        Mark job as interrupted with interruption data.

        Args:
            job_id: Job ID to mark as interrupted
            interruption_data: Interruption details
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]

            # Handle interrupted_at field which could be string or datetime
            interrupted_at_value = interruption_data.get(
                "interrupted_at", datetime.now(timezone.utc)
            )
            if isinstance(interrupted_at_value, str):
                # Parse ISO format string to datetime
                job.interrupted_at = datetime.fromisoformat(
                    interrupted_at_value.replace("Z", "+00:00")
                )
            else:
                job.interrupted_at = interrupted_at_value

            job.status = JobStatus.FAILED
            job.error_message = interruption_data.get(
                "error_message", "System interruption detected"
            )

            self._persist_jobs()

    def store_analytics_data(self, job_id: str, analytics_data: Dict[str, Any]) -> None:
        """
        Store analytics data for job.

        Args:
            job_id: Job ID to store analytics for
            analytics_data: Analytics data
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]

            from .models import AnalyticsData

            job.analytics_data = AnalyticsData(
                performance_metrics=analytics_data.get("performance_metrics"),
                resource_utilization=analytics_data.get("resource_utilization"),
                progress_patterns=analytics_data.get("progress_patterns"),
                collected_at=analytics_data.get(
                    "collected_at", datetime.now(timezone.utc)
                ),
            )

            self._persist_jobs()

    def get_analytics_data(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get analytics data for job.

        Args:
            job_id: Job ID to get analytics for

        Returns:
            Analytics data or None if not found
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            if job.analytics_data is None:
                return None

            analytics = job.analytics_data
            return {
                "performance_metrics": analytics.performance_metrics,
                "resource_utilization": analytics.resource_utilization,
                "progress_patterns": analytics.progress_patterns,
                "collected_at": analytics.collected_at.isoformat(),
            }

    def cleanup_old_progress_history(
        self, job_id: str, max_entries: int = 100, max_age_hours: int = 24
    ) -> None:
        """
        Clean up old progress history entries to prevent storage bloat.

        Args:
            job_id: Job ID to clean up
            max_entries: Maximum number of entries to keep
            max_age_hours: Maximum age in hours for entries
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(f"Job not found: {job_id}")

            job = self._jobs[job_id]
            if job.progress_history is None or len(job.progress_history) <= max_entries:
                return

            # Sort by timestamp (most recent first)
            job.progress_history.sort(key=lambda x: x.timestamp, reverse=True)

            # Keep only recent entries
            cutoff_time = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(hours=max_age_hours)

            filtered_history = []
            for entry in job.progress_history[:max_entries]:
                if entry.timestamp >= cutoff_time:
                    filtered_history.append(entry)

            job.progress_history = filtered_history
            self._persist_jobs()

    def serialize_progress_state(self, progress_state: Dict[str, Any]) -> str:
        """
        Serialize progress state to JSON string.

        Args:
            progress_state: Progress state data

        Returns:
            JSON string representation
        """

        def datetime_handler(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        return json.dumps(progress_state, default=datetime_handler, indent=2)

    def deserialize_progress_state(self, serialized_state: str) -> Dict[str, Any]:
        """
        Deserialize progress state from JSON string.

        Args:
            serialized_state: JSON string representation

        Returns:
            Deserialized progress state data
        """

        def datetime_parser(dct):
            for key, value in dct.items():
                if key.endswith("_time") or key.endswith("_at") or key == "timestamp":
                    if isinstance(value, str) and "T" in value:
                        try:
                            dct[key] = datetime.fromisoformat(
                                value.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass  # Keep original value if parsing fails
            return dct

        return cast(
            Dict[str, Any], json.loads(serialized_state, object_hook=datetime_parser)
        )

    def backup_progress_state(
        self,
        job_id: str,
        progress_state: Dict[str, Any],
        backup_type: str = "checkpoint",
    ) -> str:
        """
        Create backup of progress state.

        Args:
            job_id: Job ID to backup
            progress_state: Progress state to backup
            backup_type: Type of backup (checkpoint, critical, etc.)

        Returns:
            Backup ID
        """
        backup_id = f"backup_{job_id}_{int(time.time())}_{backup_type}"
        if not self.storage_path:
            raise ValueError("Storage path is required for backup operations")
        storage_path_obj = Path(self.storage_path)
        backup_path = storage_path_obj.parent / "progress_backups"
        backup_path.mkdir(exist_ok=True)

        backup_file = backup_path / f"{backup_id}.json"
        serialized_state = self.serialize_progress_state(progress_state)

        with open(backup_file, "w") as f:
            f.write(serialized_state)

        return backup_id

    def restore_progress_state(self, job_id: str, backup_id: str) -> Dict[str, Any]:
        """
        Restore progress state from backup.

        Args:
            job_id: Job ID to restore for
            backup_id: Backup ID to restore from

        Returns:
            Restored progress state

        Raises:
            JobNotFoundError: If backup doesn't exist
        """
        if not self.storage_path:
            raise ValueError("Storage path is required for backup operations")
        storage_path_obj = Path(self.storage_path)
        backup_path = storage_path_obj.parent / "progress_backups" / f"{backup_id}.json"

        if not backup_path.exists():
            raise JobNotFoundError(f"Backup not found: {backup_id}")

        with open(backup_path, "r") as f:
            serialized_state = f.read()

        return self.deserialize_progress_state(serialized_state)

    def mark_job_failed(self, job_id: str, error_message: str) -> None:
        """
        Mark a job as failed with an error message.

        Args:
            job_id: Job ID to mark as failed
            error_message: Error message describing the failure

        Raises:
            JobNotFoundError: If job ID doesn't exist
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]
            job.status = JobStatus.FAILED
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)

            # Release repository lock if held
            if job.repository_url:
                self._release_repository_lock(job.repository_url)

            # Advance queue to start next jobs
            self._advance_queue()

            # Persist changes
            self._persist_jobs()

    def update_phase_details(
        self, job_id: str, phase_details: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Update phase details for a job.

        Args:
            job_id: Job ID to update
            phase_details: Dictionary of phase name to phase details

        Raises:
            JobNotFoundError: If job ID doesn't exist
        """
        with self._lock:
            if job_id not in self._jobs:
                raise JobNotFoundError(job_id)

            job = self._jobs[job_id]

            # Convert datetime objects to strings for serialization
            serializable_phase_details = {}
            for phase_name, details in phase_details.items():
                serializable_details = {}
                for key, value in details.items():
                    if isinstance(value, datetime):
                        serializable_details[key] = value.isoformat()
                    else:
                        serializable_details[key] = value
                serializable_phase_details[phase_name] = serializable_details

            job.phase_details = serializable_phase_details
            self._persist_jobs()


def create_sync_job_manager(server_dir_path: Optional[str] = None) -> SyncJobManager:
    """
    Create a properly configured SyncJobManager.

    Factory function that creates a SyncJobManager with appropriate
    storage configuration based on CIDX server settings.

    Args:
        server_dir_path: Path to server directory (defaults to ~/.cidx-server)

    Returns:
        Configured SyncJobManager instance
    """
    config = SyncJobConfig(server_dir_path)
    config.setup_job_directories()

    storage_path = config.get_jobs_storage_path()
    concurrency_config = config.get_concurrency_limits()

    return SyncJobManager(storage_path=storage_path, **concurrency_config)
