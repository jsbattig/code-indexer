"""
Tests for Story #727 AC4: CPU Time-Window Thresholds.

CPU >95% sustained for 30 seconds = DEGRADED (yellow)
CPU >95% sustained for 60 seconds = UNHEALTHY (red)
Single CPU spike should NOT trigger warning.
"""

import pytest
from unittest.mock import MagicMock, patch

from code_indexer.server.models.api_models import HealthStatus
from code_indexer.server.services.database_health_service import (
    DatabaseHealthResult,
    DatabaseHealthStatus,
    CheckResult,
)


@pytest.fixture
def healthy_db_result():
    """Single healthy database result."""
    return [
        DatabaseHealthResult(
            file_name="db.db",
            display_name="DB",
            status=DatabaseHealthStatus.HEALTHY,
            checks={"connect": CheckResult(passed=True)},
            db_path="/path/db.db",
        )
    ]


@pytest.fixture
def mock_db_health(healthy_db_result):
    """Fixture providing mocked DatabaseHealthService."""
    with patch(
        "code_indexer.server.services.health_service.DatabaseHealthService"
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_instance.get_all_database_health.return_value = healthy_db_result
        mock_cls.return_value = mock_instance
        yield mock_instance


class TestCPUTimeWindowThresholds:
    """AC4: CPU Time-Window Thresholds."""

    def test_single_cpu_spike_does_not_trigger_warning(self, mock_db_health):
        """A single CPU spike >95% should NOT trigger warning."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
        ):
            mock_mem.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 98.0  # High CPU spike
            mock_disk.return_value = MagicMock(
                free=100 * 1024**3,
                used=100 * 1024**3,
                total=200 * 1024**3,
                percent=50.0,
            )
            mock_parts.return_value = []
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.HEALTHY
            assert not any("CPU" in reason for reason in response.failure_reasons)

    def test_cpu_sustained_30_seconds_returns_degraded(self, mock_db_health):
        """CPU >95% sustained for 30 seconds should return DEGRADED."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
            patch("time.time") as mock_time,
        ):
            mock_mem.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 98.0  # High CPU
            mock_disk.return_value = MagicMock(
                free=100 * 1024**3,
                used=100 * 1024**3,
                total=200 * 1024**3,
                percent=50.0,
            )
            mock_parts.return_value = []
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()

            # Simulate time progression over 30+ seconds with high CPU
            base_time = 1000000.0
            for i in range(4):  # 4 readings at 10s intervals
                mock_time.return_value = base_time + (i * 10)
                response = service.get_system_health()

            # After 30 seconds of sustained high CPU, should be degraded
            assert response.status == HealthStatus.DEGRADED
            assert any("CPU" in reason for reason in response.failure_reasons)

    def test_cpu_sustained_60_seconds_returns_unhealthy(self, mock_db_health):
        """CPU >95% sustained for 60 seconds should return UNHEALTHY."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
            patch("time.time") as mock_time,
        ):
            mock_mem.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 98.0  # High CPU
            mock_disk.return_value = MagicMock(
                free=100 * 1024**3,
                used=100 * 1024**3,
                total=200 * 1024**3,
                percent=50.0,
            )
            mock_parts.return_value = []
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()

            # Simulate time progression over 60+ seconds with high CPU
            base_time = 1000000.0
            for i in range(7):  # 7 readings at 10s intervals = 60s
                mock_time.return_value = base_time + (i * 10)
                response = service.get_system_health()

            # After 60 seconds of sustained high CPU, should be unhealthy
            assert response.status == HealthStatus.UNHEALTHY
            assert any("CPU" in reason for reason in response.failure_reasons)

    def test_cpu_history_has_attribute(self, mock_db_health):
        """HealthCheckService should have _cpu_history attribute."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
        ):
            mock_mem.return_value = MagicMock(percent=50.0)
            mock_cpu.return_value = 30.0
            mock_disk.return_value = MagicMock(
                free=100 * 1024**3,
                used=100 * 1024**3,
                total=200 * 1024**3,
                percent=50.0,
            )
            mock_parts.return_value = []
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()
            assert hasattr(service, "_cpu_history")
            assert isinstance(service._cpu_history, list)
