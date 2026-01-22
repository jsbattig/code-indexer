"""
Tests for Story #727 AC1: Aggregate All Database Health.

Server Status should aggregate health from all 8 databases.
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
def healthy_db_results():
    """Fixture providing all-healthy database results."""
    return [
        DatabaseHealthResult(
            file_name=f"db{i}.db",
            display_name=f"Database {i}",
            status=DatabaseHealthStatus.HEALTHY,
            checks={"connect": CheckResult(passed=True)},
            db_path=f"/path/db{i}.db",
        )
        for i in range(8)
    ]


@pytest.fixture
def mock_healthy_system():
    """Fixture providing healthy system metrics mocks."""
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
        yield


class TestDatabaseHealthAggregation:
    """AC1: Aggregate All Database Health."""

    def test_all_databases_healthy_returns_healthy_status(
        self, healthy_db_results, mock_healthy_system
    ):
        """When all 8 databases are healthy, Server Status should be healthy."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_health_cls:
            mock_db_health = MagicMock()
            mock_db_health.get_all_database_health.return_value = healthy_db_results
            mock_db_health_cls.return_value = mock_db_health

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.HEALTHY
            assert response.failure_reasons == []

    def test_one_database_warning_returns_degraded_status(self, mock_healthy_system):
        """When ANY database is WARNING, Server Status should be DEGRADED."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_health_cls:
            mock_db_health = MagicMock()
            db_results = [
                DatabaseHealthResult(
                    file_name=f"db{i}.db",
                    display_name=f"Database {i}",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path=f"/path/db{i}.db",
                )
                for i in range(7)
            ]
            db_results.append(
                DatabaseHealthResult(
                    file_name="oauth.db",
                    display_name="OAuth",
                    status=DatabaseHealthStatus.WARNING,
                    checks={
                        "connect": CheckResult(passed=True),
                        "not_locked": CheckResult(
                            passed=False, error_message="Database locked"
                        ),
                    },
                    db_path="/path/oauth.db",
                )
            )
            mock_db_health.get_all_database_health.return_value = db_results
            mock_db_health_cls.return_value = mock_db_health

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.DEGRADED
            assert any("OAuth" in reason for reason in response.failure_reasons)

    def test_one_database_error_returns_unhealthy_status(self, mock_healthy_system):
        """When ANY database is ERROR, Server Status should be UNHEALTHY."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_health_cls:
            mock_db_health = MagicMock()
            db_results = [
                DatabaseHealthResult(
                    file_name=f"db{i}.db",
                    display_name=f"Database {i}",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path=f"/path/db{i}.db",
                )
                for i in range(7)
            ]
            db_results.append(
                DatabaseHealthResult(
                    file_name="oauth.db",
                    display_name="OAuth",
                    status=DatabaseHealthStatus.ERROR,
                    checks={
                        "connect": CheckResult(
                            passed=False, error_message="Connection failed"
                        )
                    },
                    db_path="/path/oauth.db",
                )
            )
            mock_db_health.get_all_database_health.return_value = db_results
            mock_db_health_cls.return_value = mock_db_health

            service = HealthCheckService()
            response = service.get_system_health()

            assert response.status == HealthStatus.UNHEALTHY
            assert any("OAuth" in reason for reason in response.failure_reasons)
