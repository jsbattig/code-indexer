"""
Health Check Service.

Provides real system health monitoring following CLAUDE.md Foundation #1: No mocks.
All operations use real system checks, database connections, and service monitoring.
"""

import psutil
import time
import logging
from pathlib import Path
from typing import Dict
from datetime import datetime, timezone

from ..models.api_models import (
    HealthCheckResponse,
    ServiceHealthInfo,
    SystemHealthInfo,
    HealthStatus,
)
from ...config import ConfigManager
from ...services.qdrant import QdrantClient

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

            # Real QdrantClient integration - not injectable, not mockable
            self.qdrant_client = QdrantClient(
                config=self.config.qdrant, project_root=Path.cwd()
            )

            # Real database URL for health checks
            # Use SQLite as the default database for CIDX Server
            data_dir = Path.home() / ".cidx-server" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.database_url = f"sqlite:///{data_dir}/cidx_server.db"

        except Exception as e:
            logger.error(f"Failed to initialize real dependencies: {e}")
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
            "qdrant": self._check_qdrant_health(),
            "storage": self._check_storage_health(),
        }

        # Get system metrics
        system_info = self._get_system_info()

        # Determine overall health status
        overall_status = self._calculate_overall_status(services, system_info)

        end_time = time.time()
        logger.info(f"Health check completed in {end_time - start_time:.3f} seconds")

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

            return ServiceHealthInfo(status=status, response_time_ms=response_time)

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.error(f"Database health check failed: {e}")

            return ServiceHealthInfo(
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )

    def _check_qdrant_health(self) -> ServiceHealthInfo:
        """
        Check Qdrant vector database connectivity and performance.

        CLAUDE.md Foundation #1: Real Qdrant integration, no simulations.

        Returns:
            Qdrant service health information
        """
        start_time = time.time()

        try:
            # Real Qdrant health check - not simulated
            health_ok = self.qdrant_client.health_check()

            response_time = int((time.time() - start_time) * 1000)

            if not health_ok:
                return ServiceHealthInfo(
                    status=HealthStatus.UNHEALTHY,
                    response_time_ms=response_time,
                    error_message="Qdrant health check failed",
                )

            # Get additional cluster information for comprehensive health
            try:
                collections = self.qdrant_client.list_collections()
                cluster_size = len(collections) if collections else 0
            except Exception:
                cluster_size = 0

            if response_time < RESPONSE_TIME_WARNING:
                status = HealthStatus.HEALTHY
            elif response_time < RESPONSE_TIME_CRITICAL:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            return ServiceHealthInfo(
                status=status,
                response_time_ms=response_time,
                metadata={
                    "cluster_size": cluster_size,
                    "collections_count": len(collections) if collections else 0,
                },
            )

        except Exception as e:
            response_time = int((time.time() - start_time) * 1000)
            logger.error(f"Qdrant health check failed: {e}")

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
            logger.error(f"Storage health check failed: {e}")

            return ServiceHealthInfo(
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )

    def _get_system_info(self) -> SystemHealthInfo:
        """
        Get current system resource information.

        Returns:
            System health information
        """
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Get CPU usage (with short interval for responsiveness)
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Get disk space
        disk_usage = psutil.disk_usage("/")
        free_space_gb = disk_usage.free / (1024**3)

        # Get active job count (placeholder)
        active_jobs = self._get_active_jobs_count()

        return SystemHealthInfo(
            memory_usage_percent=memory_percent,
            cpu_usage_percent=cpu_percent,
            active_jobs=active_jobs,
            disk_free_space_gb=free_space_gb,
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
            logger.warning(f"Failed to get active job count: {e}")

        # Return 0 if job manager not available or failed to query
        return 0


# Global service instance
health_service = HealthCheckService()
