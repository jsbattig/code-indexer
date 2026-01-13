"""
Health Check Service.

Provides real system health monitoring following CLAUDE.md Foundation #1: No mocks.
All operations use real system checks, database connections, and service monitoring.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import psutil
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timezone

from ..models.api_models import (
    HealthCheckResponse,
    ServiceHealthInfo,
    SystemHealthInfo,
    HealthStatus,
    VolumeInfo,
)
from ...config import ConfigManager

logger = logging.getLogger(__name__)

# Health thresholds
MEMORY_WARNING_THRESHOLD = 80.0  # 80% memory usage
MEMORY_CRITICAL_THRESHOLD = 95.0  # 95% memory usage
DISK_WARNING_THRESHOLD = 5.0  # 5GB free space
DISK_CRITICAL_THRESHOLD = 1.0  # 1GB free space
RESPONSE_TIME_WARNING = 1000  # 1 second
RESPONSE_TIME_CRITICAL = 5000  # 5 seconds


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

        # Determine overall health status
        overall_status = self._calculate_overall_status(services, system_info)

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
            # Check disk space
            disk_usage = psutil.disk_usage("/")
            free_space_gb = disk_usage.free / (1024**3)

            # Check memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            response_time = int((time.time() - start_time) * 1000)

            # Determine status based on resource availability
            if (
                free_space_gb >= DISK_WARNING_THRESHOLD
                and memory_percent <= MEMORY_WARNING_THRESHOLD
            ):
                status = HealthStatus.HEALTHY
            elif (
                free_space_gb >= DISK_CRITICAL_THRESHOLD
                and memory_percent <= MEMORY_CRITICAL_THRESHOLD
            ):
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            error_message = None
            if free_space_gb < DISK_WARNING_THRESHOLD:
                error_message = f"Low disk space: {free_space_gb:.1f}GB free"
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

    def _calculate_overall_status(
        self, services: Dict[str, ServiceHealthInfo], system_info: SystemHealthInfo
    ) -> HealthStatus:
        """
        Calculate overall system health based on individual services and system metrics.

        Args:
            services: Dictionary of service health information
            system_info: System resource information

        Returns:
            Overall health status
        """
        service_statuses = [service.status for service in services.values()]

        # If any service is unhealthy, overall is unhealthy
        if any(status == HealthStatus.UNHEALTHY for status in service_statuses):
            return HealthStatus.UNHEALTHY

        # Check system resource limits
        if (
            system_info.memory_usage_percent > MEMORY_CRITICAL_THRESHOLD
            or system_info.disk_free_space_gb < DISK_CRITICAL_THRESHOLD
        ):
            return HealthStatus.UNHEALTHY

        # If any service is degraded or system resources are strained
        if (
            any(status == HealthStatus.DEGRADED for status in service_statuses)
            or system_info.memory_usage_percent > MEMORY_WARNING_THRESHOLD
            or system_info.disk_free_space_gb < DISK_WARNING_THRESHOLD
        ):
            return HealthStatus.DEGRADED

        # All services healthy and system resources good
        return HealthStatus.HEALTHY

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
