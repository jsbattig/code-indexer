"""
Health Check Service.

Provides real system health monitoring following CLAUDE.md Foundation #1: No mocks.
All operations use real system checks, database connections, and service monitoring.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import psutil
import time
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from ..models.api_models import (
    HealthCheckResponse,
    ServiceHealthInfo,
    SystemHealthInfo,
    HealthStatus,
    VolumeInfo,
)
from ...config import ConfigManager
from .database_health_service import (
    DatabaseHealthService,
    DatabaseHealthStatus,
    DatabaseHealthResult,
)

logger = logging.getLogger(__name__)

# Health thresholds
MEMORY_WARNING_THRESHOLD = 80.0  # 80% memory usage
MEMORY_CRITICAL_THRESHOLD = 90.0  # 90% memory usage (Story #727 AC3: updated from 95%)
DISK_WARNING_THRESHOLD = 5.0  # 5GB free space (legacy, for root volume only)
DISK_CRITICAL_THRESHOLD = 1.0  # 1GB free space (legacy, for root volume only)
# Percentage-based disk thresholds (used for multi-volume health checks)
# These work correctly regardless of volume size (fixes small boot volume false positives)
DISK_WARNING_THRESHOLD_PERCENT = 80.0  # 80% used = 20% free = warning
DISK_CRITICAL_THRESHOLD_PERCENT = 90.0  # 90% used = 10% free = critical
RESPONSE_TIME_WARNING = 1000  # 1 second
RESPONSE_TIME_CRITICAL = 5000  # 5 seconds
MAX_FAILURE_REASONS = 3  # Story #727 AC5: Limit displayed failure reasons

# CPU sustained threshold detection (Story #727 AC4)
CPU_SUSTAINED_THRESHOLD = 95.0  # CPU % threshold for sustained high load detection
MIN_CPU_READINGS_FOR_DEGRADED = 3  # Minimum readings needed for 30s assessment
MIN_CPU_READINGS_FOR_UNHEALTHY = 6  # Minimum readings needed for 60s assessment
MAX_CPU_HISTORY_SIZE = 120  # Safety limit to prevent unbounded growth


class HealthCheckService:
    """Service for system health monitoring."""

    def __init__(self):
        """Initialize the health check service with real dependencies."""
        # CLAUDE.md Foundation #1: Direct instantiation of real services only
        # NO dependency injection parameters that enable mocking
        try:
            config_manager = ConfigManager.create_with_backtrack()
            self.config = config_manager.get_config()

            # Server data directory
            self.data_dir = Path.home() / ".cidx-server" / "data"
            self.data_dir.mkdir(parents=True, exist_ok=True)

            # Real database URL for health checks
            # Use SQLite as the default database for CIDX Server
            self.database_url = f"sqlite:///{self.data_dir}/cidx_server.db"

            # State tracking for interval-averaged I/O metrics
            # These store the previous readings to calculate rates
            self._last_disk_counters: Optional[Any] = None
            self._last_disk_time: Optional[float] = None
            self._last_net_counters: Optional[Any] = None
            self._last_net_time: Optional[float] = None

            # CPU history for sustained threshold detection (Story #727 AC4)
            # List of (timestamp, cpu_percent) tuples for rolling 60s window
            self._cpu_history: List[Tuple[float, float]] = []
            self._cpu_history_lock = (
                threading.Lock()
            )  # Thread safety for concurrent requests

        except Exception as e:
            logger.error(
                f"Failed to initialize real dependencies: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            raise RuntimeError(f"Cannot initialize health check service: {e}")

    def get_system_health(self) -> HealthCheckResponse:
        """
        Get comprehensive system health status.

        Returns:
            Health check response with service and system status
        """
        start_time = time.time()

        # Check individual services
        services = {
            "database": self._check_database_health(),
            "storage": self._check_storage_health(),
        }

        # Get system metrics
        system_info = self._get_system_info()

        # Story #727 AC1: Get all database health via DatabaseHealthService
        db_health_service = DatabaseHealthService()
        database_health = db_health_service.get_all_database_health()

        # Determine overall health status with all indicators (Story #727)
        overall_status, failure_reasons = self._calculate_overall_status(
            services, system_info, database_health
        )

        end_time = time.time()
        logger.info(
            f"Health check completed in {end_time - start_time:.3f} seconds",
            extra={"correlation_id": get_correlation_id()},
        )

        return HealthCheckResponse(
            status=overall_status,
            timestamp=datetime.now(timezone.utc),
            services=services,
            system=system_info,
            failure_reasons=failure_reasons,
        )

    def _check_database_health(self) -> ServiceHealthInfo:
        """
        Check database connectivity and performance.

        Returns:
            Database service health information
        """
        start_time = time.time()

        try:
            # Real database connection check
            try:
                from sqlalchemy import create_engine, text
            except ImportError:
                # SQLAlchemy not available - fall back to basic SQLite check
                import sqlite3

                # Extract database path from SQLite URL
                db_path = self.database_url.replace("sqlite:///", "")
                with sqlite3.connect(db_path) as connection:
                    cursor = connection.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            else:
                # Use SQLAlchemy if available
                engine = create_engine(self.database_url, pool_pre_ping=True)
                with engine.connect() as connection:
                    # Execute simple query to verify database health
                    connection.execute(text("SELECT 1"))

            response_time = int((time.time() - start_time) * 1000)

            if response_time < RESPONSE_TIME_WARNING:
                status = HealthStatus.HEALTHY
            elif response_time < RESPONSE_TIME_CRITICAL:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            return ServiceHealthInfo(
                status=status, response_time_ms=response_time, error_message=None
            )

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.error(
                f"Database health check failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

            return ServiceHealthInfo(
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )

    def _check_storage_health(self) -> ServiceHealthInfo:
        """
        Check storage system health and availability.

        Returns:
            Storage service health information
        """
        start_time = time.time()

        try:
            # Check disk space (use percentage for consistency with multi-volume checks)
            disk_usage = psutil.disk_usage("/")
            free_space_gb = disk_usage.free / (1024**3)
            disk_used_percent = disk_usage.percent

            # Check memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            response_time = int((time.time() - start_time) * 1000)

            # Determine status based on resource availability (percentage-based for disk)
            if (
                disk_used_percent < DISK_WARNING_THRESHOLD_PERCENT
                and memory_percent <= MEMORY_WARNING_THRESHOLD
            ):
                status = HealthStatus.HEALTHY
            elif (
                disk_used_percent < DISK_CRITICAL_THRESHOLD_PERCENT
                and memory_percent <= MEMORY_CRITICAL_THRESHOLD
            ):
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            error_message = None
            if disk_used_percent >= DISK_WARNING_THRESHOLD_PERCENT:
                error_message = f"Low disk space: {disk_used_percent:.0f}% used ({free_space_gb:.1f}GB free)"
            elif memory_percent > MEMORY_WARNING_THRESHOLD:
                error_message = f"High memory usage: {memory_percent:.1f}%"

            return ServiceHealthInfo(
                status=status,
                response_time_ms=response_time,
                error_message=error_message,
            )

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.error(
                f"Storage health check failed: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

            return ServiceHealthInfo(
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )

    def _get_system_info(self) -> SystemHealthInfo:
        """
        Get current system resource information with interval-averaged metrics.

        CPU, disk I/O, and network I/O are calculated as interval averages
        between calls rather than spot readings, providing more meaningful
        performance metrics for dashboard display.

        Returns:
            System health information with interval-averaged I/O rates
        """
        current_time = time.time()

        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Get CPU usage - interval=None for interval-averaged measurement
        # This returns the average CPU usage since the last call (or 0.0 on first call)
        cpu_percent = psutil.cpu_percent(interval=None)

        # Get disk space (AC5: Complete disk metrics with used/free and percentages)
        disk_usage = psutil.disk_usage("/")
        free_space_gb = disk_usage.free / (1024**3)
        used_space_gb = disk_usage.used / (1024**3)
        # psutil provides percent as used percentage
        disk_used_percent = disk_usage.percent
        disk_free_percent = 100.0 - disk_used_percent

        # Calculate disk I/O rates (KB/s) from counter diffs
        disk_counters = psutil.disk_io_counters()
        disk_read_kb_s = 0.0
        disk_write_kb_s = 0.0

        if (
            self._last_disk_counters is not None
            and self._last_disk_time is not None
            and disk_counters is not None
        ):
            elapsed = current_time - self._last_disk_time
            if elapsed > 0:
                bytes_read_diff = (
                    disk_counters.read_bytes - self._last_disk_counters.read_bytes
                )
                bytes_write_diff = (
                    disk_counters.write_bytes - self._last_disk_counters.write_bytes
                )
                disk_read_kb_s = (bytes_read_diff / 1024) / elapsed
                disk_write_kb_s = (bytes_write_diff / 1024) / elapsed

        # Update disk state for next call
        self._last_disk_counters = disk_counters
        self._last_disk_time = current_time

        # Calculate network I/O rates (KB/s) from counter diffs
        net_counters = psutil.net_io_counters()
        net_rx_kb_s = 0.0
        net_tx_kb_s = 0.0

        if (
            self._last_net_counters is not None
            and self._last_net_time is not None
            and net_counters is not None
        ):
            elapsed = current_time - self._last_net_time
            if elapsed > 0:
                bytes_recv_diff = (
                    net_counters.bytes_recv - self._last_net_counters.bytes_recv
                )
                bytes_sent_diff = (
                    net_counters.bytes_sent - self._last_net_counters.bytes_sent
                )
                net_rx_kb_s = (bytes_recv_diff / 1024) / elapsed
                net_tx_kb_s = (bytes_sent_diff / 1024) / elapsed

        # Update network state for next call
        self._last_net_counters = net_counters
        self._last_net_time = current_time

        # Get active job count
        active_jobs = self._get_active_jobs_count()

        # Get all mounted volumes
        volumes = self._get_mounted_volumes()

        return SystemHealthInfo(
            memory_usage_percent=memory_percent,
            cpu_usage_percent=cpu_percent,
            active_jobs=active_jobs,
            disk_free_space_gb=free_space_gb,
            disk_used_space_gb=used_space_gb,
            disk_free_percent=disk_free_percent,
            disk_used_percent=disk_used_percent,
            disk_read_kb_s=disk_read_kb_s,
            disk_write_kb_s=disk_write_kb_s,
            net_rx_kb_s=net_rx_kb_s,
            net_tx_kb_s=net_tx_kb_s,
            volumes=volumes,
        )

    def _collect_database_failures(
        self, database_health: List[DatabaseHealthResult]
    ) -> Tuple[bool, bool, List[str]]:
        """
        Check all database health and collect failures (Story #727 AC1).

        Args:
            database_health: List of DatabaseHealthResult from DatabaseHealthService

        Returns:
            Tuple of (has_warning, has_error, failure_reasons)
        """
        reasons: List[str] = []
        has_warning = False
        has_error = False

        for db_result in database_health:
            if db_result.status == DatabaseHealthStatus.ERROR:
                has_error = True
                for check_name, check in db_result.checks.items():
                    if not check.passed:
                        reasons.append(
                            f"{db_result.display_name} DB: {check.error_message or check_name}"
                        )
                        break
            elif db_result.status == DatabaseHealthStatus.WARNING:
                has_warning = True
                for check_name, check in db_result.checks.items():
                    if not check.passed:
                        reasons.append(
                            f"{db_result.display_name} DB: {check.error_message or check_name}"
                        )
                        break
            # NOT_INITIALIZED and HEALTHY statuses don't affect overall health
            # NOT_INITIALIZED databases are lazy-loaded and optional (not yet created)
            # HEALTHY databases are fully operational

        return has_warning, has_error, reasons

    def _collect_volume_failures(
        self, volumes: List[VolumeInfo]
    ) -> Tuple[bool, bool, List[str]]:
        """
        Check all volumes for low disk space (Story #727 AC2).

        Args:
            volumes: List of VolumeInfo from _get_mounted_volumes()

        Returns:
            Tuple of (has_warning, has_error, failure_reasons)
        """
        reasons: List[str] = []
        has_warning = False
        has_error = False

        for volume in volumes:
            # Use percentage-based thresholds (fixes false positives on small volumes like /boot)
            if volume.used_percent >= DISK_CRITICAL_THRESHOLD_PERCENT:
                has_error = True
                reasons.append(
                    f"Volume {volume.mount_point}: {volume.used_percent:.0f}% used ({volume.free_gb:.1f}GB free)"
                )
            elif volume.used_percent >= DISK_WARNING_THRESHOLD_PERCENT:
                has_warning = True
                reasons.append(
                    f"Volume {volume.mount_point}: {volume.used_percent:.0f}% used ({volume.free_gb:.1f}GB free)"
                )

        return has_warning, has_error, reasons

    def _collect_resource_failures(
        self, memory_percent: float, cpu_percent: float
    ) -> Tuple[bool, bool, List[str]]:
        """
        Check RAM and CPU thresholds (Story #727 AC3, AC4).

        Args:
            memory_percent: Current memory usage percentage
            cpu_percent: Current CPU usage percentage

        Returns:
            Tuple of (has_warning, has_error, failure_reasons)
        """
        reasons: List[str] = []
        has_warning = False
        has_error = False

        # AC3: RAM thresholds
        if memory_percent >= MEMORY_CRITICAL_THRESHOLD:
            has_error = True
            reasons.append(f"RAM: {memory_percent:.0f}%")
        elif memory_percent >= MEMORY_WARNING_THRESHOLD:
            has_warning = True
            reasons.append(f"RAM: {memory_percent:.0f}%")

        # AC4: CPU sustained thresholds
        cpu_degraded, cpu_unhealthy = self._check_cpu_sustained(cpu_percent)
        if cpu_unhealthy:
            has_error = True
            reasons.append(f"CPU: {cpu_percent:.0f}% sustained >60s")
        elif cpu_degraded:
            has_warning = True
            reasons.append(f"CPU: {cpu_percent:.0f}% sustained >30s")

        return has_warning, has_error, reasons

    def _check_cpu_sustained(self, current_cpu: float) -> Tuple[bool, bool]:
        """
        Check if CPU >95% for sustained periods (Story #727 AC4).

        Tracks CPU history over rolling 60-second window and checks:
        - 30+ seconds sustained >95% = degraded
        - 60+ seconds sustained >95% = unhealthy

        Thread-safe: Uses lock to protect _cpu_history from concurrent access.

        Args:
            current_cpu: Current CPU percentage reading

        Returns:
            Tuple of (is_degraded, is_unhealthy)
        """
        now = time.time()

        with self._cpu_history_lock:
            # Add current reading to history
            self._cpu_history.append((now, current_cpu))

            # Prune entries older than 60 seconds
            self._cpu_history = [(t, c) for t, c in self._cpu_history if now - t <= 60]

            # Safety limit to prevent unbounded growth
            if len(self._cpu_history) > MAX_CPU_HISTORY_SIZE:
                self._cpu_history = self._cpu_history[-MAX_CPU_HISTORY_SIZE:]

            # Take snapshot for analysis outside lock
            history_snapshot = list(self._cpu_history)

        # Analysis proceeds outside lock using snapshot
        if len(history_snapshot) < MIN_CPU_READINGS_FOR_DEGRADED:
            return False, False

        # Check readings in last 30 seconds
        readings_30s = [c for t, c in history_snapshot if now - t <= 30]
        # Check readings in last 60 seconds (already pruned to 60s max)
        readings_60s = [c for t, c in history_snapshot]

        # Degraded: CPU >95% sustained for 30+ seconds
        is_degraded = len(readings_30s) >= MIN_CPU_READINGS_FOR_DEGRADED and all(
            c > CPU_SUSTAINED_THRESHOLD for c in readings_30s
        )

        # Unhealthy: CPU >95% sustained for 60+ seconds
        is_unhealthy = len(readings_60s) >= MIN_CPU_READINGS_FOR_UNHEALTHY and all(
            c > CPU_SUSTAINED_THRESHOLD for c in readings_60s
        )

        return is_degraded, is_unhealthy

    def _calculate_overall_status(
        self,
        services: Dict[str, ServiceHealthInfo],
        system_info: SystemHealthInfo,
        database_health: List[DatabaseHealthResult],
    ) -> Tuple[HealthStatus, List[str]]:
        """
        Calculate overall system health based on all indicators (Story #727).

        Args:
            services: Dictionary of service health information
            system_info: System resource information
            database_health: List of DatabaseHealthResult from DatabaseHealthService

        Returns:
            Tuple of (overall_status, failure_reasons)
        """
        failure_reasons: List[str] = []
        has_warning = False
        has_error = False

        # AC1: Database health
        db_warn, db_err, db_reasons = self._collect_database_failures(database_health)
        has_warning = has_warning or db_warn
        has_error = has_error or db_err
        failure_reasons.extend(db_reasons)

        # AC2: Volume health
        vol_warn, vol_err, vol_reasons = self._collect_volume_failures(
            system_info.volumes
        )
        has_warning = has_warning or vol_warn
        has_error = has_error or vol_err
        failure_reasons.extend(vol_reasons)

        # AC3 & AC4: RAM and CPU thresholds
        res_warn, res_err, res_reasons = self._collect_resource_failures(
            system_info.memory_usage_percent, system_info.cpu_usage_percent
        )
        has_warning = has_warning or res_warn
        has_error = has_error or res_err
        failure_reasons.extend(res_reasons)

        # Check individual service statuses (database, storage services)
        # Issue #3: Add error messages to failure_reasons when services fail
        for name, svc in services.items():
            if svc.status == HealthStatus.UNHEALTHY:
                has_error = True
                if svc.error_message:
                    failure_reasons.append(f"{name.capitalize()}: {svc.error_message}")
            elif svc.status == HealthStatus.DEGRADED:
                has_warning = True
                if svc.error_message:
                    failure_reasons.append(f"{name.capitalize()}: {svc.error_message}")

        # Determine overall status
        if has_error:
            status = HealthStatus.UNHEALTHY
        elif has_warning:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        # AC5: Limit to MAX_FAILURE_REASONS with "+N more" indicator
        if len(failure_reasons) > MAX_FAILURE_REASONS:
            extra_count = len(failure_reasons) - MAX_FAILURE_REASONS
            failure_reasons = failure_reasons[:MAX_FAILURE_REASONS] + [
                f"+{extra_count} more"
            ]

        return status, failure_reasons

    def _get_mounted_volumes(self) -> list:
        """
        Get all mounted non-removable volumes.

        Filters out:
        - Virtual filesystems (tmpfs, devtmpfs, proc, sysfs, etc.)
        - Removable media (typically detected by mount options)
        - Network filesystems (nfs, cifs, smbfs)
        - Snap/loop mounts

        Returns:
            List of VolumeInfo for each real mounted volume
        """
        volumes = []

        # Filesystem types to exclude (virtual, network, removable)
        excluded_fstypes = {
            "tmpfs",
            "devtmpfs",
            "proc",
            "sysfs",
            "devpts",
            "securityfs",
            "cgroup",
            "cgroup2",
            "pstore",
            "debugfs",
            "hugetlbfs",
            "mqueue",
            "fusectl",
            "configfs",
            "binfmt_misc",
            "autofs",
            "tracefs",
            "nfs",
            "nfs4",
            "cifs",
            "smbfs",
            "squashfs",  # Snap packages
            "overlay",  # Docker overlays
            "fuse.snapfuse",
        }

        # Mount point prefixes to exclude
        excluded_prefixes = (
            "/snap/",
            "/sys/",
            "/proc/",
            "/dev/",
            "/run/",
        )

        try:
            partitions = psutil.disk_partitions(all=False)

            for partition in partitions:
                # Skip excluded filesystem types
                if partition.fstype.lower() in excluded_fstypes:
                    continue

                # Skip excluded mount point prefixes
                if partition.mountpoint.startswith(excluded_prefixes):
                    continue

                # Skip loop devices (snap packages, ISO mounts)
                if partition.device.startswith("/dev/loop"):
                    continue

                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total_gb = usage.total / (1024**3)
                    used_gb = usage.used / (1024**3)
                    free_gb = usage.free / (1024**3)
                    used_percent = usage.percent
                    free_percent = 100.0 - used_percent

                    volumes.append(
                        VolumeInfo(
                            mount_point=partition.mountpoint,
                            device=partition.device,
                            fstype=partition.fstype,
                            total_gb=total_gb,
                            used_gb=used_gb,
                            free_gb=free_gb,
                            used_percent=used_percent,
                            free_percent=free_percent,
                        )
                    )
                except (PermissionError, OSError) as e:
                    # Skip volumes we can't access
                    logger.debug(
                        f"Cannot access volume {partition.mountpoint}: {e}",
                        extra={"correlation_id": get_correlation_id()},
                    )
                    continue

        except Exception as e:
            logger.warning(
                f"Failed to get mounted volumes: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

        return volumes

    def _get_active_jobs_count(self) -> int:
        """
        Get count of active background jobs.

        Queries the background job management system for active jobs.

        Returns:
            Number of active jobs
        """
        try:
            # Access the global background job manager
            from ...server.app import background_job_manager

            if background_job_manager:
                return background_job_manager.get_active_job_count()
        except Exception as e:
            logger.warning(
                f"Failed to get active job count: {e}",
                extra={"correlation_id": get_correlation_id()},
            )

        # Return 0 if job manager not available or failed to query
        return 0


# Global service instance
health_service = HealthCheckService()
