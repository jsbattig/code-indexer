"""Job Polling Engine for CIDX Repository Sync - Story 11: Polling Loop Engine.

Implements intelligent polling loop that monitors job status and provides real-time
progress updates with familiar CIDX UX patterns (single-line progress bar).
"""

import asyncio
import logging
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, cast, Protocol

from ..api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
)

logger = logging.getLogger(__name__)


class ProgressCallback(Protocol):
    """Protocol for progress callback with flexible info parameter."""

    def __call__(
        self, current: int, total: int, file_path: Path, info: str = ""
    ) -> None:
        """Call progress callback with flexible info parameter.

        Args:
            current: Current progress count
            total: Total count (0 for setup messages)
            file_path: Current file path
            info: Progress information message (can be positional or keyword)
        """
        ...


@dataclass
class JobStatus:
    """Job status information from server."""

    job_id: str
    status: str  # queued, running, completed, failed, cancelled
    phase: str  # setup, git_pull, indexing, validation, completed
    progress: float  # 0.0 to 1.0
    message: str
    current_operation: Optional[str] = None
    files_processed: Optional[int] = None
    total_files: Optional[int] = None
    processing_speed: Optional[float] = (
        None  # files per second or embeddings per second
    )
    elapsed_time: Optional[float] = None
    estimated_remaining: Optional[float] = None
    error_details: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class PollingConfig:
    """Configuration for job polling behavior."""

    base_interval: float = 1.0  # Base polling interval in seconds
    max_interval: float = 10.0  # Maximum polling interval in seconds
    max_backoff_multiplier: float = 8.0  # Maximum backoff multiplier
    timeout: float = 300.0  # Total polling timeout in seconds
    network_retry_attempts: int = 3  # Number of retry attempts for network errors

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_interval < self.base_interval:
            raise ValueError("max_interval must be >= base_interval")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.network_retry_attempts < 0:
            raise ValueError("network_retry_attempts must be non-negative")


class JobPollingError(Exception):
    """Base exception for job polling errors."""

    pass


class JobTimeoutError(JobPollingError):
    """Exception raised when job polling times out."""

    pass


class NetworkConnectionError(JobPollingError):
    """Exception raised when network connection fails after retries."""

    pass


class InterruptedPollingError(JobPollingError):
    """Exception raised when polling is interrupted by user."""

    pass


class JobPollingEngine:
    """Intelligent job polling engine with network resilience and progress display."""

    def __init__(
        self,
        api_client: CIDXRemoteAPIClient,
        progress_callback: ProgressCallback,
        config: Optional[PollingConfig] = None,
    ):
        """Initialize job polling engine.

        Args:
            api_client: CIDX API client for job status requests
            progress_callback: Callback for progress updates (current, total, path, info)
            config: Polling configuration (uses defaults if None)
        """
        self.api_client = api_client
        self.progress_callback = progress_callback
        self.config = config or PollingConfig()

        # Polling state
        self.is_polling = False
        self.current_job_id: Optional[str] = None
        self._polling_task: Optional[asyncio.Task] = None
        self._interrupted = False

        # Setup interrupt handler
        self._setup_interrupt_handler()

    def _setup_interrupt_handler(self):
        """Setup signal handler for graceful interruption."""
        try:
            # Only setup if running in main thread
            if hasattr(signal, "SIGINT"):
                signal.signal(signal.SIGINT, self._handle_interrupt)
        except ValueError:
            # Not in main thread or signal not supported
            pass

    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signal (Ctrl+C)."""
        logger.info("Interrupt signal received, stopping polling...")
        self._interrupted = True
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()

    async def start_polling(
        self, job_id: str, timeout_seconds: Optional[int] = None
    ) -> JobStatus:
        """Start polling for job status updates.

        Args:
            job_id: Job ID to poll for status
            timeout_seconds: Override timeout (uses config timeout if None)

        Returns:
            Final job status when completed

        Raises:
            JobPollingError: If job fails or polling encounters error
            JobTimeoutError: If polling times out
            NetworkConnectionError: If network errors persist after retries
            InterruptedPollingError: If polling is interrupted
        """
        if self.is_polling:
            raise JobPollingError(f"Already polling job {self.current_job_id}")

        self.is_polling = True
        self.current_job_id = job_id
        self._interrupted = False

        start_time = time.time()
        consecutive_errors = 0
        effective_timeout = (
            timeout_seconds if timeout_seconds is not None else self.config.timeout
        )

        try:
            self._polling_task = asyncio.current_task()

            while True:
                # Check for timeout
                elapsed = time.time() - start_time
                remaining_time = effective_timeout - elapsed

                if elapsed >= effective_timeout:
                    # Try to cancel job on timeout
                    try:
                        await self._cancel_job_on_timeout(job_id)
                    except Exception as cancel_error:
                        logger.warning(
                            f"Failed to cancel job {job_id} on timeout: {cancel_error}"
                        )

                    raise JobTimeoutError(
                        f"Job {job_id} polling timed out after {effective_timeout} seconds. "
                        f"You can try increasing timeout with --timeout flag or check server status."
                    )

                # Check for interruption
                if self._interrupted:
                    raise InterruptedPollingError("Polling was interrupted by user")

                try:
                    # Get job status with retry logic
                    status = await self._get_job_status_with_retry(
                        job_id, consecutive_errors
                    )
                    consecutive_errors = 0  # Reset error count on success

                    # Display progress update with timeout information
                    self._display_progress(status, elapsed, remaining_time)

                    # Check if job is complete
                    if status.status in ["completed", "failed", "cancelled"]:
                        if status.status == "failed":
                            error_msg = f"Job failed: {status.message}"
                            if status.error_details:
                                error_msg += f"\nDetails: {status.error_details}"
                            raise JobPollingError(error_msg)
                        elif status.status == "cancelled":
                            raise JobPollingError(
                                f"Job was cancelled: {status.message}"
                            )

                        # Job completed successfully
                        return status

                    # Calculate next polling interval
                    interval = self._calculate_polling_interval(status, elapsed)
                    await asyncio.sleep(interval)

                except (NetworkError, APIClientError) as e:
                    consecutive_errors += 1

                    # Don't retry authentication errors
                    if isinstance(e, AuthenticationError):
                        raise

                    # Check if we've exhausted retries
                    if consecutive_errors > self.config.network_retry_attempts:
                        raise NetworkConnectionError(
                            f"Network error after {self.config.network_retry_attempts} retry attempts: {e}"
                        )

                    # Use exponential backoff for retries
                    backoff_interval = self._calculate_backoff_interval(
                        consecutive_errors, self.config.base_interval
                    )
                    logger.warning(
                        f"Network error (attempt {consecutive_errors}): {e}. Retrying in {backoff_interval}s"
                    )
                    await asyncio.sleep(backoff_interval)

        except asyncio.CancelledError:
            raise InterruptedPollingError("Polling was interrupted")
        finally:
            self._cleanup_polling()

    async def stop_polling(self) -> None:
        """Stop current polling operation."""
        if not self.is_polling:
            return

        self._interrupted = True

        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        if self._interrupted:
            raise InterruptedPollingError("Polling was interrupted")

    async def _get_job_status_with_retry(self, job_id: str, attempt: int) -> JobStatus:
        """Get job status from server with proper error handling.

        Args:
            job_id: Job ID to get status for
            attempt: Current attempt number (for logging)

        Returns:
            Job status from server

        Raises:
            APIClientError: If server returns error response
            NetworkError: If network request fails
            AuthenticationError: If authentication fails
        """
        try:
            # Call API client to get job status
            response = await self.api_client.get_job_status(job_id)

            # Convert response to JobStatus
            if isinstance(response, dict):
                return JobStatus(
                    job_id=response.get("job_id", job_id),
                    status=response.get("status", "unknown"),
                    phase=response.get("phase", "unknown"),
                    progress=response.get("progress", 0.0),
                    message=response.get("message", ""),
                    current_operation=response.get("current_operation"),
                    files_processed=response.get("files_processed"),
                    total_files=response.get("total_files"),
                    processing_speed=response.get("processing_speed"),
                    elapsed_time=response.get("elapsed_time"),
                    estimated_remaining=response.get("estimated_remaining"),
                    error_details=response.get("error_details"),
                    details=response.get("details"),
                )
            elif isinstance(response, JobStatus):
                return response
            else:
                raise JobPollingError(
                    f"Invalid job status response type: {type(response)}"
                )

        except (NetworkError, AuthenticationError):
            # Let network and auth errors propagate for retry handling
            raise
        except APIClientError as e:
            if e.status_code == 404:
                raise JobPollingError(f"Job not found: {job_id}")
            else:
                raise JobPollingError(f"Failed to get job status: {e}")
        except Exception as e:
            raise JobPollingError(f"Unexpected error getting job status: {e}")

    def _display_progress(
        self,
        status: JobStatus,
        elapsed_time: Optional[float] = None,
        remaining_time: Optional[float] = None,
    ) -> None:
        """Display progress update using CIDX progress callback format.

        Args:
            status: Current job status to display
            elapsed_time: Time elapsed since polling started
            remaining_time: Time remaining until timeout
        """
        try:
            # Determine if this is a setup message or progress bar
            if (
                status.files_processed is None
                or status.total_files is None
                or status.total_files == 0
            ):
                # Setup message (total=0 triggers info display)
                info_message = f"{status.phase}: {status.message}"

                # Add timeout information to setup messages
                if remaining_time is not None and remaining_time > 0:
                    if remaining_time < 60:
                        info_message += f" (timeout: {int(remaining_time)}s)"
                    else:
                        info_message += f" (timeout: {int(remaining_time/60)}m)"

                self.progress_callback(0, 0, Path(""), info=info_message)
            else:
                # Progress bar (total > 0 triggers progress bar display)
                current = status.files_processed
                total = status.total_files
                percentage = int(status.progress * 100)

                # Build info string in CIDX format: "files (%) | emb/s | threads | filename"
                info_parts = [f"{current}/{total} files ({percentage}%)"]

                if status.processing_speed:
                    info_parts.append(f"{status.processing_speed:.1f} emb/s")

                # Add phase info
                info_parts.append(status.phase)

                # Add current operation if available
                if status.current_operation:
                    info_parts.append(status.current_operation)

                # Add timeout information if available
                if remaining_time is not None and remaining_time > 0:
                    if remaining_time < 60:
                        info_parts.append(f"timeout: {int(remaining_time)}s")
                    else:
                        info_parts.append(f"timeout: {int(remaining_time/60)}m")

                info_message = " | ".join(info_parts)

                # Use filename from current operation if available
                path = (
                    Path(status.current_operation)
                    if status.current_operation
                    else Path("")
                )

                self.progress_callback(current, total, path, info=info_message)

        except Exception as e:
            # Don't let progress display errors break polling
            logger.warning(f"Error displaying progress: {e}")

    def _calculate_polling_interval(
        self, status: JobStatus, elapsed_time: float
    ) -> float:
        """Calculate optimal polling interval based on job status and elapsed time.

        Args:
            status: Current job status
            elapsed_time: Time elapsed since polling started

        Returns:
            Polling interval in seconds
        """
        # Base interval
        interval = self.config.base_interval

        # Adjust based on job phase
        if status.phase == "queued":
            # Poll less frequently for queued jobs
            interval = min(interval * 2.0, self.config.max_interval)
        elif status.phase in ["git_pull", "validation"]:
            # These phases are usually quick, poll more frequently
            interval = max(interval * 0.5, 0.5)
        elif status.phase == "indexing":
            # Indexing can be long, use adaptive polling
            if elapsed_time > 60:  # After 1 minute
                interval = min(interval * 1.5, self.config.max_interval)

        return interval

    def _calculate_backoff_interval(self, attempt: int, base_interval: float) -> float:
        """Calculate exponential backoff interval for retries.

        Args:
            attempt: Current retry attempt number (1-based)
            base_interval: Base interval for calculation

        Returns:
            Backoff interval in seconds
        """
        # Exponential backoff: base * 2^(attempt-1)
        # For attempt=1: 2^0 = 1, attempt=2: 2^1 = 2, attempt=3: 2^2 = 4, etc.
        exponent = attempt - 1
        multiplier = min(2**exponent, self.config.max_backoff_multiplier)
        interval = base_interval * multiplier

        # Cap at maximum interval
        return cast(float, min(interval, self.config.max_interval))

    async def _cancel_job_on_timeout(self, job_id: str) -> None:
        """Cancel job when timeout occurs.

        Args:
            job_id: Job ID to cancel
        """
        try:
            # Check if API client supports job cancellation
            if hasattr(self.api_client, "cancel_job"):
                await self.api_client.cancel_job(
                    job_id, reason="Polling timeout exceeded"
                )
                logger.info(f"Job {job_id} cancelled due to polling timeout")
            else:
                logger.warning(
                    f"Cannot cancel job {job_id}: API client does not support cancellation"
                )
        except Exception as e:
            logger.error(f"Error cancelling job {job_id} on timeout: {e}")
            # Don't re-raise - we still want to report the timeout error

    def _cleanup_polling(self) -> None:
        """Clean up polling state."""
        self.is_polling = False
        self.current_job_id = None
        self._polling_task = None
