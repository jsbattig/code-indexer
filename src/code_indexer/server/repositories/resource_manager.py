"""
Comprehensive Resource Management for CIDX Server Operations.

This module provides ResourceManager for tracking and cleaning up all types of resources
during repository operations, including file handles, database connections, temporary files,
background tasks, and memory management with graceful shutdown capabilities.

Following CLAUDE.md anti-mock principles - all resource operations are real:
- Real file handle management and cleanup
- Real database connection tracking and closing
- Real temporary file deletion
- Real background task cancellation
- Real memory monitoring with psutil
- Real signal handling for graceful shutdown

Usage:
    async with ResourceManager() as rm:
        # Track resources created during operations
        rm.track_file_handle(file_handle)
        rm.track_database_connection(conn, "conn_name")
        rm.track_temp_file(temp_path)
        rm.track_background_task(task, "task_name")

        # Perform repository operations...

    # All resources automatically cleaned up on context exit
"""

import asyncio
import gc
import logging
import shutil
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Set, List, Any, Optional, Callable, Union, TextIO, BinaryIO
import psutil


# Configure logging
logger = logging.getLogger(__name__)


class ResourceCleanupError(Exception):
    """Exception raised when resource cleanup fails."""

    pass


@dataclass
class MemoryLeakWarning:
    """Data structure for memory leak warnings."""

    growth_mb: float
    current_mb: float
    baseline_mb: float
    threshold_mb: float
    message: str

    def get_severity(self) -> str:
        """Determine warning severity based on memory growth."""
        if self.growth_mb > self.threshold_mb * 3:
            return "severe"
        elif self.growth_mb > self.threshold_mb * 1.5:
            return "high"
        else:
            return "moderate"

    def get_recommendations(self) -> List[str]:
        """Get recommendations for addressing memory leak."""
        recommendations = [
            "Force garbage collection with gc.collect()",
            "Review resource cleanup in finally blocks",
            "Check for unclosed file handles and database connections",
            "Verify background tasks are properly cancelled",
        ]

        if self.get_severity() == "severe":
            recommendations.extend(
                [
                    "Consider restarting affected services",
                    "Review memory-intensive operations for optimization",
                ]
            )

        return recommendations

    def __str__(self) -> str:
        """String representation of memory leak warning."""
        return (
            f"MemoryLeak [{self.get_severity().upper()}]: "
            f"Memory grew by {self.growth_mb:.1f}MB "
            f"(current: {self.current_mb:.1f}MB, baseline: {self.baseline_mb:.1f}MB, "
            f"threshold: {self.threshold_mb:.1f}MB) - {self.message}"
        )


class ResourceTracker:
    """
    Resource manager for specialized resource management.

    Provides specialized tracking and cleanup for different resource types
    with proper error handling and resource state validation.
    """

    def __init__(self) -> None:
        """Initialize resource tracker with empty resource collections."""
        self.file_handles: Set[Union[TextIO, BinaryIO]] = set()
        self.database_connections: Dict[str, Any] = {}
        self.temp_files: Set[Path] = set()
        self.background_tasks: Dict[str, asyncio.Task] = {}
        self._lock = threading.Lock()

    def track_file_handle(self, file_handle: Union[TextIO, BinaryIO]) -> None:
        """Track a file handle for cleanup."""
        with self._lock:
            self.file_handles.add(file_handle)
            logger.debug(
                f"Tracking file handle: {getattr(file_handle, 'name', 'unknown')}"
            )

    def track_database_connection(self, connection: Any, connection_name: str) -> None:
        """Track a database connection for cleanup."""
        with self._lock:
            self.database_connections[connection_name] = connection
            logger.debug(f"Tracking database connection: {connection_name}")

    def track_temp_file(self, temp_path: Path) -> None:
        """Track a temporary file for cleanup."""
        with self._lock:
            self.temp_files.add(temp_path)
            logger.debug(f"Tracking temp file: {temp_path}")

    def track_background_task(self, task: asyncio.Task, task_name: str) -> None:
        """Track a background task for cleanup."""
        with self._lock:
            self.background_tasks[task_name] = task
            logger.debug(f"Tracking background task: {task_name}")

    def cleanup_file_handles(self) -> List[str]:
        """Clean up all tracked file handles."""
        cleanup_errors = []

        with self._lock:
            for file_handle in list(self.file_handles):
                try:
                    if not file_handle.closed:
                        file_handle.close()
                        logger.debug(
                            f"Closed file handle: {getattr(file_handle, 'name', 'unknown')}"
                        )
                except Exception as e:
                    error_msg = f"Failed to close file handle: {e}"
                    cleanup_errors.append(error_msg)
                    logger.warning(error_msg)

            self.file_handles.clear()

        return cleanup_errors

    def cleanup_database_connections(self) -> List[str]:
        """Clean up all tracked database connections."""
        cleanup_errors = []

        with self._lock:
            for conn_name, connection in list(self.database_connections.items()):
                try:
                    if hasattr(connection, "close"):
                        connection.close()
                        logger.debug(f"Closed database connection: {conn_name}")
                except Exception as e:
                    error_msg = f"Failed to close database connection {conn_name}: {e}"
                    cleanup_errors.append(error_msg)
                    logger.warning(error_msg)

            self.database_connections.clear()

        return cleanup_errors

    def cleanup_temp_files(self) -> List[str]:
        """Clean up all tracked temporary files."""
        cleanup_errors = []

        with self._lock:
            for temp_path in list(self.temp_files):
                try:
                    if temp_path.exists():
                        if temp_path.is_dir():
                            shutil.rmtree(temp_path)
                            logger.debug(f"Removed temp directory: {temp_path}")
                        else:
                            temp_path.unlink()
                            logger.debug(f"Removed temp file: {temp_path}")
                except Exception as e:
                    error_msg = f"Failed to remove temp file {temp_path}: {e}"
                    cleanup_errors.append(error_msg)
                    logger.warning(error_msg)

            self.temp_files.clear()

        return cleanup_errors

    async def cleanup_background_tasks(self) -> List[str]:
        """Clean up all tracked background tasks."""
        cleanup_errors = []

        with self._lock:
            tasks_to_cancel = list(self.background_tasks.items())

        # Cancel tasks without lock to avoid blocking
        for task_name, task in tasks_to_cancel:
            try:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, timeout=2.0)
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Task {task_name} did not cancel within timeout"
                        )
                    except asyncio.CancelledError:
                        pass  # Expected for cancelled tasks

                    logger.debug(f"Cancelled background task: {task_name}")
            except Exception as e:
                error_msg = f"Failed to cancel background task {task_name}: {e}"
                cleanup_errors.append(error_msg)
                logger.warning(error_msg)

        with self._lock:
            self.background_tasks.clear()

        return cleanup_errors


class MemoryMonitor:
    """
    Memory monitoring for detecting resource leaks and memory growth.

    Provides baseline memory capture, growth tracking, leak detection,
    and garbage collection capabilities using psutil for accurate measurement.
    """

    def __init__(self, leak_threshold_mb: float = 50.0):
        """
        Initialize memory monitor with baseline capture.

        Args:
            leak_threshold_mb: Memory growth threshold for leak detection (MB)
        """
        self.leak_threshold_mb = leak_threshold_mb
        self.baseline_memory_mb = self._capture_current_memory()
        logger.info(f"Memory baseline captured: {self.baseline_memory_mb:.1f}MB")

    def _capture_current_memory(self) -> float:
        """Capture current memory usage in MB."""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return float(memory_info.rss / (1024 * 1024))  # Convert to MB
        except Exception as e:
            logger.warning(f"Failed to capture memory usage: {e}")
            return 0.0

    def get_current_memory_mb(self) -> float:
        """Get current memory usage in MB."""
        return self._capture_current_memory()

    def get_memory_growth_mb(self) -> float:
        """Calculate memory growth from baseline."""
        current_memory = self.get_current_memory_mb()
        return current_memory - self.baseline_memory_mb

    def get_process_memory_percent(self) -> float:
        """Get process memory usage as percentage of system memory."""
        try:
            process = psutil.Process()
            return float(process.memory_percent())
        except Exception as e:
            logger.warning(f"Failed to get memory percentage: {e}")
            return 0.0

    def check_for_memory_leaks(self) -> List[MemoryLeakWarning]:
        """Check for potential memory leaks and return warnings."""
        warnings = []

        current_memory = self.get_current_memory_mb()
        memory_growth = self.get_memory_growth_mb()

        if memory_growth > self.leak_threshold_mb:
            warning = MemoryLeakWarning(
                growth_mb=memory_growth,
                current_mb=current_memory,
                baseline_mb=self.baseline_memory_mb,
                threshold_mb=self.leak_threshold_mb,
                message=f"Memory usage increased by {memory_growth:.1f}MB, exceeding threshold of {self.leak_threshold_mb:.1f}MB",
            )
            warnings.append(warning)
            logger.warning(str(warning))

        return warnings

    def force_garbage_collection(self) -> int:
        """Force garbage collection and return number of objects collected."""
        try:
            collected_objects = gc.collect()
            logger.debug(f"Garbage collection freed {collected_objects} objects")
            return collected_objects
        except Exception as e:
            logger.warning(f"Garbage collection failed: {e}")
            return 0

    def reset_baseline(self) -> None:
        """Reset memory baseline to current usage."""
        old_baseline = self.baseline_memory_mb
        self.baseline_memory_mb = self.get_current_memory_mb()
        logger.info(
            f"Memory baseline reset from {old_baseline:.1f}MB to {self.baseline_memory_mb:.1f}MB"
        )

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        current_memory = self.get_current_memory_mb()
        memory_growth = self.get_memory_growth_mb()
        process_percent = self.get_process_memory_percent()

        stats: Dict[str, Any] = {
            "current_memory_mb": current_memory,
            "baseline_memory_mb": self.baseline_memory_mb,
            "memory_growth_mb": memory_growth,
            "process_memory_percent": process_percent,
        }

        # Include leak warnings if present
        leak_warnings = self.check_for_memory_leaks()
        stats["leak_warnings"] = [str(warning) for warning in leak_warnings]

        return stats


class GracefulShutdownHandler:
    """
    Graceful shutdown signal handler for CIDX server operations.

    Handles SIGTERM and SIGINT signals, executes cleanup callbacks,
    and manages graceful termination with timeout handling.
    """

    def __init__(self, shutdown_timeout: float = 30.0):
        """
        Initialize graceful shutdown handler.

        Args:
            shutdown_timeout: Maximum time to wait for cleanup completion (seconds)
        """
        self.shutdown_timeout = shutdown_timeout
        self.shutdown_requested = False
        self.cleanup_callbacks: List[Callable[[], None]] = []
        self.async_cleanup_callbacks: List[Callable[[], Any]] = []
        self._cleanup_executed = False
        self._lock = threading.Lock()

    def register_handlers(self) -> None:
        """Register signal handlers for SIGTERM and SIGINT."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        logger.info("Graceful shutdown handlers registered for SIGTERM and SIGINT")

    def register_cleanup_callback(self, callback: Callable[[], None]) -> None:
        """Register synchronous cleanup callback."""
        with self._lock:
            self.cleanup_callbacks.append(callback)
            logger.debug(f"Registered cleanup callback: {callback.__name__}")

    def register_async_cleanup_callback(self, callback: Callable[[], Any]) -> None:
        """Register asynchronous cleanup callback."""
        with self._lock:
            self.async_cleanup_callbacks.append(callback)
            logger.debug(f"Registered async cleanup callback: {callback.__name__}")

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals and execute cleanup."""
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name} signal, initiating graceful shutdown")

        with self._lock:
            if self._cleanup_executed:
                logger.info("Cleanup already executed, ignoring additional signals")
                return

            self.shutdown_requested = True
            self._cleanup_executed = True

        # Execute cleanup with timeout
        self._execute_cleanup_with_timeout()

    def _execute_cleanup_with_timeout(self) -> None:
        """Execute all cleanup callbacks with timeout handling."""
        start_time = time.time()

        # Execute synchronous cleanup callbacks
        for callback in self.cleanup_callbacks:
            # Check timeout before starting each callback
            elapsed = time.time() - start_time
            if elapsed >= self.shutdown_timeout:
                logger.warning(
                    f"Cleanup timeout ({self.shutdown_timeout}s) exceeded after {elapsed:.2f}s, skipping remaining callbacks"
                )
                break

            # Calculate remaining time for this callback
            remaining_time = self.shutdown_timeout - elapsed

            try:
                import threading

                callback_start = time.time()
                callback_completed = threading.Event()
                callback_exception = []

                def timeout_handler():
                    if not callback_completed.wait(timeout=remaining_time):
                        logger.warning(
                            f"Cleanup callback {callback.__name__} exceeded timeout of {remaining_time:.2f}s, continuing to next callback"
                        )
                        return

                def run_callback():
                    try:
                        callback()
                    except Exception as e:
                        callback_exception.append(e)
                    finally:
                        callback_completed.set()

                # Run callback in thread with timeout
                callback_thread = threading.Thread(target=run_callback)
                callback_thread.daemon = True
                callback_thread.start()

                # Wait for callback or timeout
                callback_completed.wait(timeout=remaining_time)
                callback_duration = time.time() - callback_start

                if callback_exception:
                    raise callback_exception[0]

                if callback_duration <= remaining_time:
                    logger.debug(
                        f"Cleanup callback {callback.__name__} completed in {callback_duration:.2f}s"
                    )

            except Exception as e:
                logger.error(f"Cleanup callback {callback.__name__} failed: {e}")

        # Execute asynchronous cleanup callbacks
        elapsed = time.time() - start_time
        if self.async_cleanup_callbacks and elapsed < self.shutdown_timeout:
            remaining_timeout = self.shutdown_timeout - elapsed
            self._execute_async_cleanup(remaining_timeout)

    def _execute_async_cleanup(self, timeout: float) -> None:
        """Execute asynchronous cleanup callbacks with timeout."""
        if not self.async_cleanup_callbacks:
            return

        try:
            # Check if we're already in an event loop
            try:
                current_loop = asyncio.get_running_loop()
                # If we're in a running loop, schedule the cleanup for later
                logger.warning(
                    "Cannot run async cleanup in existing event loop, scheduling for thread"
                )
                # Schedule async cleanup in the current event loop
                # We can't await in a signal handler, but we can schedule tasks

                def schedule_async_cleanup():
                    try:
                        for callback in self.async_cleanup_callbacks:
                            try:
                                # Schedule the coroutine as a task in the current loop
                                current_loop.create_task(callback())
                                logger.debug(
                                    f"Scheduled async cleanup callback: {callback.__name__}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to schedule async cleanup callback {callback.__name__}: {e}"
                                )
                    except Exception as e:
                        logger.error(f"Failed to schedule async cleanup: {e}")

                # Schedule the async cleanup to run in the next event loop iteration
                current_loop.call_soon(schedule_async_cleanup)
                return
            except RuntimeError:
                # No running loop, we can create our own
                pass

            # Create new event loop for cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Execute async callbacks with timeout
                async def run_async_cleanup():
                    tasks = []
                    for callback in self.async_cleanup_callbacks:
                        try:
                            task = asyncio.create_task(callback())
                            tasks.append(task)
                        except Exception as e:
                            logger.error(
                                f"Failed to create async cleanup task for {callback.__name__}: {e}"
                            )

                    if tasks:
                        try:
                            await asyncio.wait_for(
                                asyncio.gather(*tasks, return_exceptions=True),
                                timeout=timeout,
                            )
                        except asyncio.TimeoutError:
                            logger.warning("Async cleanup timeout exceeded")
                            for task in tasks:
                                if not task.done():
                                    task.cancel()

                loop.run_until_complete(run_async_cleanup())
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Async cleanup execution failed: {e}")


class ResourceManager:
    """
    Comprehensive async context manager for CIDX server resource management.

    Tracks and automatically cleans up all types of resources including:
    - File handles (real file I/O operations)
    - Database connections (real connection pool management)
    - Temporary files and directories (real filesystem operations)
    - Background tasks (real asyncio task cancellation)
    - Memory monitoring (real psutil-based measurement)

    Integrates with existing CIDX server operations for seamless resource management
    during repository operations, background jobs, and server lifecycle.

    Usage:
        async with ResourceManager() as rm:
            # All tracked resources automatically cleaned up on exit
            file_handle = open("temp.txt", "w")
            rm.track_file_handle(file_handle)

            conn = database.get_connection()
            rm.track_database_connection(conn, "main_db")

            temp_dir = Path("/tmp/operation")
            temp_dir.mkdir()
            rm.track_temp_file(temp_dir)

            task = asyncio.create_task(background_operation())
            rm.track_background_task(task, "bg_op")
    """

    def __init__(
        self,
        enable_memory_monitoring: bool = True,
        memory_leak_threshold_mb: float = 100.0,
    ):
        """
        Initialize ResourceManager with optional memory monitoring.

        Args:
            enable_memory_monitoring: Whether to enable memory leak detection
            memory_leak_threshold_mb: Memory growth threshold for leak warnings
        """
        self.tracker = ResourceTracker()

        # Memory monitoring setup
        self.enable_memory_monitoring = enable_memory_monitoring
        self.memory_monitor: Optional[MemoryMonitor] = None
        self.memory_baseline_mb: Optional[float] = None

        if enable_memory_monitoring:
            self.memory_monitor = MemoryMonitor(
                leak_threshold_mb=memory_leak_threshold_mb
            )
            self.memory_baseline_mb = self.memory_monitor.baseline_memory_mb

        logger.debug("ResourceManager initialized")

    async def __aenter__(self):
        """Async context manager entry."""
        logger.debug("ResourceManager context entered")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with comprehensive cleanup."""
        logger.debug("ResourceManager context exiting, starting cleanup")

        try:
            await self.cleanup_all()
        except Exception as e:
            logger.error(f"ResourceManager cleanup failed: {e}")
            # Don't suppress exceptions from the context

        logger.debug("ResourceManager context exited")

    # Resource tracking methods
    def track_file_handle(self, file_handle: Union[TextIO, BinaryIO]) -> None:
        """Track file handle for automatic cleanup."""
        self.tracker.track_file_handle(file_handle)

    def track_database_connection(self, connection: Any, connection_name: str) -> None:
        """Track database connection for automatic cleanup."""
        self.tracker.track_database_connection(connection, connection_name)

    def track_temp_file(self, temp_path: Path) -> None:
        """Track temporary file for automatic cleanup."""
        self.tracker.track_temp_file(temp_path)

    def track_background_task(self, task: asyncio.Task, task_name: str) -> None:
        """Track background task for automatic cleanup."""
        self.tracker.track_background_task(task, task_name)

    # Resource access properties (for testing and monitoring)
    @property
    def tracked_files(self) -> Set[Union[TextIO, BinaryIO]]:
        """Get currently tracked file handles."""
        return self.tracker.file_handles.copy()

    @property
    def tracked_connections(self) -> Dict[str, Any]:
        """Get currently tracked database connections."""
        return self.tracker.database_connections.copy()

    @property
    def tracked_temp_files(self) -> Set[Path]:
        """Get currently tracked temporary files."""
        return self.tracker.temp_files.copy()

    @property
    def tracked_tasks(self) -> Dict[str, asyncio.Task]:
        """Get currently tracked background tasks."""
        return self.tracker.background_tasks.copy()

    # Memory monitoring methods
    def get_current_memory_mb(self) -> Optional[float]:
        """Get current memory usage in MB."""
        if self.memory_monitor:
            return self.memory_monitor.get_current_memory_mb()
        return None

    def check_for_memory_leaks(self) -> List[MemoryLeakWarning]:
        """Check for memory leaks and return warnings."""
        if self.memory_monitor:
            return self.memory_monitor.check_for_memory_leaks()
        return []

    def force_garbage_collection(self) -> int:
        """Force garbage collection and return objects collected."""
        if self.memory_monitor:
            return self.memory_monitor.force_garbage_collection()
        return gc.collect()

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        if self.memory_monitor:
            return self.memory_monitor.get_memory_statistics()
        return {
            "memory_monitoring": "disabled",
            "current_memory_mb": 0,
            "baseline_memory_mb": 0,
            "memory_growth_mb": 0,
        }

    # Comprehensive cleanup
    async def cleanup_all(self) -> None:
        """
        Perform comprehensive cleanup of all tracked resources.

        Continues cleanup even if individual operations fail, logging errors
        but ensuring maximum resource cleanup completion.
        """
        cleanup_errors = []

        logger.info("Starting comprehensive resource cleanup")

        # 1. Cancel background tasks first (they may be using other resources)
        try:
            task_errors = await self.tracker.cleanup_background_tasks()
            cleanup_errors.extend(task_errors)
            logger.debug(
                f"Background tasks cleanup completed with {len(task_errors)} errors"
            )
        except Exception as e:
            error_msg = f"Background task cleanup failed: {e}"
            cleanup_errors.append(error_msg)
            logger.error(error_msg)

        # 2. Close file handles
        try:
            file_errors = self.tracker.cleanup_file_handles()
            cleanup_errors.extend(file_errors)
            logger.debug(
                f"File handles cleanup completed with {len(file_errors)} errors"
            )
        except Exception as e:
            error_msg = f"File handle cleanup failed: {e}"
            cleanup_errors.append(error_msg)
            logger.error(error_msg)

        # 3. Close database connections
        try:
            db_errors = self.tracker.cleanup_database_connections()
            cleanup_errors.extend(db_errors)
            logger.debug(
                f"Database connections cleanup completed with {len(db_errors)} errors"
            )
        except Exception as e:
            error_msg = f"Database connection cleanup failed: {e}"
            cleanup_errors.append(error_msg)
            logger.error(error_msg)

        # 4. Remove temporary files
        try:
            temp_errors = self.tracker.cleanup_temp_files()
            cleanup_errors.extend(temp_errors)
            logger.debug(
                f"Temporary files cleanup completed with {len(temp_errors)} errors"
            )
        except Exception as e:
            error_msg = f"Temporary file cleanup failed: {e}"
            cleanup_errors.append(error_msg)
            logger.error(error_msg)

        # 5. Force garbage collection if memory monitoring enabled
        if self.memory_monitor:
            try:
                collected = self.force_garbage_collection()
                logger.debug(f"Garbage collection freed {collected} objects")
            except Exception as e:
                error_msg = f"Garbage collection failed: {e}"
                cleanup_errors.append(error_msg)
                logger.error(error_msg)

        # Log cleanup summary
        total_errors = len(cleanup_errors)
        if total_errors == 0:
            logger.info("Resource cleanup completed successfully")
        else:
            logger.warning(f"Resource cleanup completed with {total_errors} errors")
            for error in cleanup_errors:
                logger.warning(f"  - {error}")

        # Check for memory leaks after cleanup
        if self.memory_monitor:
            try:
                leak_warnings = self.check_for_memory_leaks()
                if leak_warnings:
                    for warning in leak_warnings:
                        logger.warning(f"Memory leak detected after cleanup: {warning}")
            except Exception as e:
                logger.error(f"Memory leak check failed: {e}")


# Convenience function for server integration
def create_server_resource_manager(
    memory_monitoring: bool = True, leak_threshold_mb: float = 100.0
) -> ResourceManager:
    """
    Create ResourceManager configured for CIDX server operations.

    Args:
        memory_monitoring: Enable memory leak detection
        leak_threshold_mb: Memory growth threshold for warnings

    Returns:
        Configured ResourceManager instance
    """
    return ResourceManager(
        enable_memory_monitoring=memory_monitoring,
        memory_leak_threshold_mb=leak_threshold_mb,
    )


# Server lifecycle integration functions
def setup_graceful_shutdown(
    resource_manager: ResourceManager,
) -> GracefulShutdownHandler:
    """
    Set up graceful shutdown handling integrated with ResourceManager.

    Args:
        resource_manager: ResourceManager instance to cleanup on shutdown

    Returns:
        Configured GracefulShutdownHandler
    """
    shutdown_handler = GracefulShutdownHandler()

    # Register ResourceManager cleanup on shutdown
    def cleanup_resources():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule cleanup task
                asyncio.create_task(resource_manager.cleanup_all())
            else:
                # Run cleanup in new event loop
                asyncio.run(resource_manager.cleanup_all())
        except Exception as e:
            logger.error(f"Resource cleanup during shutdown failed: {e}")

    shutdown_handler.register_cleanup_callback(cleanup_resources)
    shutdown_handler.register_handlers()

    logger.info("Graceful shutdown configured with resource cleanup")
    return shutdown_handler
