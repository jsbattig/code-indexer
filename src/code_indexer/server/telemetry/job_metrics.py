"""
Job and Repository Metrics Instrumentation for OTEL (Story #699).

This module provides gauges and counters for job lifecycle and repository
state metrics. Metrics are exported to OTEL when telemetry is enabled.

Metrics exported:
- cidx.jobs.active (Observable Gauge) - Active running jobs count
- cidx.jobs.queued (Observable Gauge) - Queued jobs count
- cidx.jobs.completed (Counter) - Completed jobs count
- cidx.jobs.failed (Counter) - Failed jobs count with error_type attribute
- cidx.jobs.duration (Histogram) - Job execution duration in seconds
- cidx.repos.total (Observable Gauge) - Total repositories count
- cidx.repos.indexed (Observable Gauge) - Indexed repositories count
- cidx.repos.refresh.duration (Histogram) - Repository refresh duration

Usage:
    from src.code_indexer.server.telemetry.job_metrics import (
        get_job_metrics,
    )

    metrics = get_job_metrics(telemetry_manager)

    # Set callbacks for observable gauges
    metrics.set_job_counts_callback(lambda: {"active": 3, "queued": 5})
    metrics.set_repository_counts_callback(lambda: {"total": 10, "indexed": 8})

    # Record job completion
    metrics.record_job_completed(job_type="repository_sync", duration_seconds=120.5)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from src.code_indexer.server.telemetry.manager import TelemetryManager

logger = logging.getLogger(__name__)

# Singleton instance
_job_metrics: Optional["JobMetrics"] = None


class JobMetrics:
    """
    Job and repository metrics instrumentation for CIDX operations.

    Provides counters, histograms, and observable gauges for job lifecycle
    and repository state tracking. No-op when telemetry is disabled.
    """

    def __init__(
        self,
        telemetry_manager: "TelemetryManager",
    ) -> None:
        """
        Initialize JobMetrics.

        Args:
            telemetry_manager: TelemetryManager instance for getting meter
        """
        self._telemetry_manager = telemetry_manager
        self._is_active = False

        # Job counters and histograms
        self._jobs_completed_counter: Optional[Any] = None
        self._jobs_failed_counter: Optional[Any] = None
        self._jobs_duration_histogram: Optional[Any] = None

        # Job observable gauges
        self._jobs_active_gauge: Optional[Any] = None
        self._jobs_queued_gauge: Optional[Any] = None

        # Repository gauges and histograms
        self._repos_total_gauge: Optional[Any] = None
        self._repos_indexed_gauge: Optional[Any] = None
        self._repos_refresh_duration_histogram: Optional[Any] = None

        # Callbacks for observable gauges
        self._job_counts_callback: Optional[Callable[[], Dict[str, int]]] = None
        self._repo_counts_callback: Optional[Callable[[], Dict[str, int]]] = None

        if (
            telemetry_manager.is_initialized
            and telemetry_manager._config.export_metrics
        ):
            self._register_metrics()

    def _register_metrics(self) -> None:
        """Register all metrics with the meter."""
        try:
            meter = self._telemetry_manager.get_meter("cidx.jobs")

            # Job counters
            self._jobs_completed_counter = meter.create_counter(
                name="cidx.jobs.completed",
                description="Number of completed jobs",
                unit="1",
            )
            self._jobs_failed_counter = meter.create_counter(
                name="cidx.jobs.failed",
                description="Number of failed jobs",
                unit="1",
            )

            # Job duration histogram
            self._jobs_duration_histogram = meter.create_histogram(
                name="cidx.jobs.duration",
                description="Job execution duration",
                unit="s",
            )

            # Job observable gauges
            self._jobs_active_gauge = meter.create_observable_gauge(
                name="cidx.jobs.active",
                description="Number of currently active (running) jobs",
                unit="1",
                callbacks=[self._observe_active_jobs],
            )
            self._jobs_queued_gauge = meter.create_observable_gauge(
                name="cidx.jobs.queued",
                description="Number of queued jobs waiting to run",
                unit="1",
                callbacks=[self._observe_queued_jobs],
            )

            # Repository gauges
            self._repos_total_gauge = meter.create_observable_gauge(
                name="cidx.repos.total",
                description="Total number of repositories",
                unit="1",
                callbacks=[self._observe_total_repos],
            )
            self._repos_indexed_gauge = meter.create_observable_gauge(
                name="cidx.repos.indexed",
                description="Number of indexed repositories",
                unit="1",
                callbacks=[self._observe_indexed_repos],
            )

            # Repository refresh duration histogram
            self._repos_refresh_duration_histogram = meter.create_histogram(
                name="cidx.repos.refresh.duration",
                description="Repository refresh duration",
                unit="s",
            )

            self._is_active = True
            logger.info("JobMetrics initialized: 9 metrics registered")

        except Exception as e:
            logger.warning(f"Failed to register job metrics: {e}")
            self._is_active = False

    def _observe_active_jobs(self, options: Any) -> Any:
        """Observable callback for active jobs gauge."""
        try:
            if self._job_counts_callback:
                counts = self._job_counts_callback()
                yield self._create_observation(counts.get("active", 0))
            else:
                yield self._create_observation(0)
        except Exception as e:
            logger.debug(f"Failed to observe active jobs: {e}")
            yield self._create_observation(0)

    def _observe_queued_jobs(self, options: Any) -> Any:
        """Observable callback for queued jobs gauge."""
        try:
            if self._job_counts_callback:
                counts = self._job_counts_callback()
                yield self._create_observation(counts.get("queued", 0))
            else:
                yield self._create_observation(0)
        except Exception as e:
            logger.debug(f"Failed to observe queued jobs: {e}")
            yield self._create_observation(0)

    def _observe_total_repos(self, options: Any) -> Any:
        """Observable callback for total repositories gauge."""
        try:
            if self._repo_counts_callback:
                counts = self._repo_counts_callback()
                yield self._create_observation(counts.get("total", 0))
            else:
                yield self._create_observation(0)
        except Exception as e:
            logger.debug(f"Failed to observe total repos: {e}")
            yield self._create_observation(0)

    def _observe_indexed_repos(self, options: Any) -> Any:
        """Observable callback for indexed repositories gauge."""
        try:
            if self._repo_counts_callback:
                counts = self._repo_counts_callback()
                yield self._create_observation(counts.get("indexed", 0))
            else:
                yield self._create_observation(0)
        except Exception as e:
            logger.debug(f"Failed to observe indexed repos: {e}")
            yield self._create_observation(0)

    def _create_observation(self, value: int) -> Any:
        """Create an Observation object for observable gauges."""
        from opentelemetry.metrics import Observation

        return Observation(value)

    def set_job_counts_callback(
        self,
        callback: Callable[[], Dict[str, int]],
    ) -> None:
        """
        Set callback function for job counts (active, queued).

        The callback should return a dict with keys 'active' and 'queued'.

        Args:
            callback: Function returning {"active": int, "queued": int}
        """
        self._job_counts_callback = callback

    def set_repository_counts_callback(
        self,
        callback: Callable[[], Dict[str, int]],
    ) -> None:
        """
        Set callback function for repository counts (total, indexed).

        The callback should return a dict with keys 'total' and 'indexed'.

        Args:
            callback: Function returning {"total": int, "indexed": int}
        """
        self._repo_counts_callback = callback

    def record_job_completed(
        self,
        job_type: str,
        duration_seconds: float,
    ) -> None:
        """
        Record a job completion metric.

        Args:
            job_type: Type of job (repository_sync, repository_activation, etc.)
            duration_seconds: Job execution duration in seconds
        """
        if not self._is_active:
            return

        attributes = {
            "job_type": job_type,
            "status": "completed",
        }

        try:
            assert self._jobs_completed_counter is not None
            assert self._jobs_duration_histogram is not None
            self._jobs_completed_counter.add(1, attributes)
            self._jobs_duration_histogram.record(duration_seconds, attributes)
        except Exception as e:
            logger.debug(f"Failed to record job completion metrics: {e}")

    def record_job_failed(
        self,
        job_type: str,
        error_type: str,
        duration_seconds: float,
    ) -> None:
        """
        Record a job failure metric.

        Args:
            job_type: Type of job (repository_sync, repository_activation, etc.)
            error_type: Type of error that caused the failure
            duration_seconds: Job execution duration in seconds
        """
        if not self._is_active:
            return

        attributes = {
            "job_type": job_type,
            "error_type": error_type,
            "status": "failed",
        }

        try:
            assert self._jobs_failed_counter is not None
            assert self._jobs_duration_histogram is not None
            self._jobs_failed_counter.add(1, attributes)
            self._jobs_duration_histogram.record(duration_seconds, attributes)
        except Exception as e:
            logger.debug(f"Failed to record job failure metrics: {e}")

    def record_repository_refresh(
        self,
        repository: str,
        duration_seconds: float,
        status: str,
    ) -> None:
        """
        Record a repository refresh metric.

        Args:
            repository: Repository name/ID
            duration_seconds: Refresh duration in seconds
            status: Refresh status (success, error)
        """
        if not self._is_active:
            return

        attributes = {
            "repository": repository,
            "status": status,
        }

        try:
            assert self._repos_refresh_duration_histogram is not None
            self._repos_refresh_duration_histogram.record(duration_seconds, attributes)
        except Exception as e:
            logger.debug(f"Failed to record repository refresh metrics: {e}")

    @property
    def is_active(self) -> bool:
        """Return whether metrics are actively being recorded."""
        return self._is_active


def get_job_metrics(
    telemetry_manager: "TelemetryManager",
) -> JobMetrics:
    """
    Get or create the JobMetrics singleton.

    Args:
        telemetry_manager: TelemetryManager instance

    Returns:
        JobMetrics instance
    """
    global _job_metrics

    if _job_metrics is None:
        _job_metrics = JobMetrics(telemetry_manager)

    return _job_metrics


def reset_job_metrics() -> None:
    """Reset the JobMetrics singleton (for testing)."""
    global _job_metrics
    _job_metrics = None
