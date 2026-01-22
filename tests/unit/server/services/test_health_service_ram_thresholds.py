"""
Tests for Story #727 AC3: Updated RAM Thresholds.

RAM 80% usage = DEGRADED (yellow)
RAM 90% usage = UNHEALTHY (red) - updated from 95%
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


class TestRAMThresholds:
    """AC3: Updated RAM Thresholds."""

    def test_memory_critical_threshold_is_90_percent(self):
        """Verify MEMORY_CRITICAL_THRESHOLD is set to 90%."""
        from code_indexer.server.services.health_service import (
            MEMORY_CRITICAL_THRESHOLD,
        )

        assert MEMORY_CRITICAL_THRESHOLD == 90.0

    def test_ram_at_80_percent_returns_degraded(self, mock_db_health):
        """RAM >= 80% usage should return DEGRADED (yellow)."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
        ):
            mock_mem.return_value = MagicMock(percent=80.0)  # Warning threshold
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
            response = service.get_system_health()

            assert response.status == HealthStatus.DEGRADED
            assert any(
                "RAM" in reason or "Memory" in reason
                for reason in response.failure_reasons
            )

    def test_ram_at_90_percent_returns_unhealthy(self, mock_db_health):
        """RAM >= 90% usage should return UNHEALTHY (red)."""
        from code_indexer.server.services.health_service import HealthCheckService

        with (
            patch("psutil.virtual_memory") as mock_mem,
            patch("psutil.cpu_percent") as mock_cpu,
            patch("psutil.disk_usage") as mock_disk,
            patch("psutil.disk_partitions") as mock_parts,
            patch("psutil.disk_io_counters") as mock_disk_io,
            patch("psutil.net_io_counters") as mock_net_io,
        ):
            mock_mem.return_value = MagicMock(percent=90.0)  # Critical threshold
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
            response = service.get_system_health()

            assert response.status == HealthStatus.UNHEALTHY
            assert any(
                "RAM" in reason or "Memory" in reason
                for reason in response.failure_reasons
            )
