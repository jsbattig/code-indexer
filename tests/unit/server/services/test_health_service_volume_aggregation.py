"""
Tests for Story #727 AC2: Aggregate All Volume Health.

Server Status should check ALL mounted volumes.
Per-volume thresholds (percentage-based): 80% used = WARNING, 90% used = CRITICAL.
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


class TestVolumeHealthAggregation:
    """AC2: Aggregate All Volume Health."""

    def test_volume_with_warning_percent_returns_degraded(self, mock_db_health):
        """When ANY volume has 80-90% used, Server Status should be DEGRADED."""
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

            mock_partition = MagicMock()
            mock_partition.mountpoint = "/data"
            mock_partition.device = "/dev/sdb1"
            mock_partition.fstype = "ext4"
            mock_parts.return_value = [mock_partition]

            def disk_usage_side_effect(path):
                if path == "/data":
                    return MagicMock(
                        free=15 * 1024**3,  # 15GB free
                        used=85 * 1024**3,  # 85GB used
                        total=100 * 1024**3,
                        percent=85.0,  # 85% used (between 80% warning and 90% critical)
                    )
                return MagicMock(
                    free=100 * 1024**3,
                    used=100 * 1024**3,
                    total=200 * 1024**3,
                    percent=50.0,
                )

            mock_disk.side_effect = disk_usage_side_effect
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.DEGRADED
            assert any("/data" in reason for reason in response.failure_reasons)

    def test_volume_with_less_than_1gb_free_returns_unhealthy(self, mock_db_health):
        """When ANY volume has <1GB free, Server Status should be UNHEALTHY."""
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

            mock_partition = MagicMock()
            mock_partition.mountpoint = "/data"
            mock_partition.device = "/dev/sdb1"
            mock_partition.fstype = "ext4"
            mock_parts.return_value = [mock_partition]

            def disk_usage_side_effect(path):
                if path == "/data":
                    return MagicMock(
                        free=0.5 * 1024**3,  # 0.5GB free (< 1GB critical)
                        used=99.5 * 1024**3,
                        total=100 * 1024**3,
                        percent=99.5,
                    )
                return MagicMock(
                    free=100 * 1024**3,
                    used=100 * 1024**3,
                    total=200 * 1024**3,
                    percent=50.0,
                )

            mock_disk.side_effect = disk_usage_side_effect
            mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
            mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.UNHEALTHY
            assert any("/data" in reason for reason in response.failure_reasons)
