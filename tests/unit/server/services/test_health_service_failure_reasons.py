"""
Tests for Story #727 AC5: Display Failure Reasons.

When Server Status is DEGRADED or UNHEALTHY, show reason below status indicator.
Format: List of failing indicators (e.g., "RAM: 85%", "OAuth DB: locked")
Limit to first 3 failure reasons if more exist, with "+N more" indicator.
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
def mock_db_health_factory():
    """Factory fixture for creating mocked DatabaseHealthService."""

    def _create_mock(db_results):
        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_cls:
            mock_instance = MagicMock()
            mock_instance.get_all_database_health.return_value = db_results
            mock_cls.return_value = mock_instance
            yield mock_instance

    return _create_mock


class TestFailureReasonsField:
    """AC5: failure_reasons field existence tests."""

    def test_failure_reasons_field_exists_in_response(self):
        """HealthCheckResponse should have failure_reasons field."""
        from code_indexer.server.models.api_models import HealthCheckResponse

        assert hasattr(HealthCheckResponse, "model_fields")
        field_names = list(HealthCheckResponse.model_fields.keys())
        assert "failure_reasons" in field_names

    def test_failure_reasons_defaults_to_empty_list(self):
        """failure_reasons should default to empty list."""
        from code_indexer.server.models.api_models import HealthCheckResponse

        field_info = HealthCheckResponse.model_fields.get("failure_reasons")
        assert field_info is not None
        assert field_info.default_factory is not None or field_info.default == []


class TestFailureReasonsContent:
    """AC5: failure_reasons content tests."""

    def test_healthy_status_has_empty_failure_reasons(self):
        """When status is HEALTHY, failure_reasons should be empty."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            mock_db.get_all_database_health.return_value = [
                DatabaseHealthResult(
                    file_name="db.db",
                    display_name="DB",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path="/path/db.db",
                )
            ]
            mock_db_cls.return_value = mock_db

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
                response = service.get_system_health()

                assert response.status == HealthStatus.HEALTHY
                assert response.failure_reasons == []

    def test_failure_reasons_lists_failing_indicators(self):
        """failure_reasons should list all failing indicators."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            mock_db.get_all_database_health.return_value = [
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
            ]
            mock_db_cls.return_value = mock_db

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
                response = service.get_system_health()

                assert len(response.failure_reasons) >= 1
                assert any("OAuth" in reason for reason in response.failure_reasons)


class TestFailureReasonsLimit:
    """AC5: failure_reasons limiting tests."""

    def test_failure_reasons_limited_to_3_with_more_indicator(self):
        """failure_reasons should be limited to 3, with '+N more' indicator."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            # Create 5 databases with warnings
            db_results = [
                DatabaseHealthResult(
                    file_name=f"db{i}.db",
                    display_name=f"Database {i}",
                    status=DatabaseHealthStatus.WARNING,
                    checks={
                        "connect": CheckResult(passed=True),
                        "not_locked": CheckResult(
                            passed=False, error_message="Database locked"
                        ),
                    },
                    db_path=f"/path/db{i}.db",
                )
                for i in range(5)
            ]
            mock_db.get_all_database_health.return_value = db_results
            mock_db_cls.return_value = mock_db

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
                response = service.get_system_health()

                # Should have at most 4 entries: 3 reasons + "+N more"
                assert len(response.failure_reasons) <= 4
                # Last entry should be "+N more" if more than 3 failures
                if len(response.failure_reasons) == 4:
                    assert "+" in response.failure_reasons[-1]
                    assert "more" in response.failure_reasons[-1]


class TestServiceErrorMessagesInFailureReasons:
    """Issue #3: Service status (database, storage) errors should contribute to failure_reasons."""

    def test_storage_service_error_appears_in_failure_reasons(self):
        """When storage service reports an error, it should appear in failure_reasons."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            mock_db.get_all_database_health.return_value = [
                DatabaseHealthResult(
                    file_name="db.db",
                    display_name="DB",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path="/path/db.db",
                )
            ]
            mock_db_cls.return_value = mock_db

            with (
                patch("psutil.virtual_memory") as mock_mem,
                patch("psutil.cpu_percent") as mock_cpu,
                patch("psutil.disk_usage") as mock_disk,
                patch("psutil.disk_partitions") as mock_parts,
                patch("psutil.disk_io_counters") as mock_disk_io,
                patch("psutil.net_io_counters") as mock_net_io,
            ):
                # Set low memory to trigger healthy system metrics
                mock_mem.return_value = MagicMock(percent=50.0)
                mock_cpu.return_value = 30.0
                # Set VERY low disk space to trigger storage service error
                mock_disk.return_value = MagicMock(
                    free=0.5 * 1024**3,  # 0.5GB - below DISK_CRITICAL_THRESHOLD
                    used=199.5 * 1024**3,
                    total=200 * 1024**3,
                    percent=99.75,
                )
                mock_parts.return_value = []  # No volumes to avoid volume failures
                mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
                mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

                service = HealthCheckService()
                response = service.get_system_health()

                # Storage service should be unhealthy due to low disk space
                assert response.services["storage"].status == HealthStatus.UNHEALTHY
                assert response.services["storage"].error_message is not None

                # The storage error message should appear in failure_reasons
                storage_error = response.services["storage"].error_message
                assert any(
                    "Storage" in reason and storage_error in reason
                    for reason in response.failure_reasons
                ), f"Storage error '{storage_error}' not found in failure_reasons: {response.failure_reasons}"

    def test_database_service_error_appears_in_failure_reasons(self):
        """When database service reports an error, it should appear in failure_reasons."""
        from code_indexer.server.services.health_service import HealthCheckService

        # Mock database check to fail by having SQLAlchemy unavailable and SQLite fail
        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            mock_db.get_all_database_health.return_value = [
                DatabaseHealthResult(
                    file_name="db.db",
                    display_name="DB",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path="/path/db.db",
                )
            ]
            mock_db_cls.return_value = mock_db

            with (
                patch("psutil.virtual_memory") as mock_mem,
                patch("psutil.cpu_percent") as mock_cpu,
                patch("psutil.disk_usage") as mock_disk,
                patch("psutil.disk_partitions") as mock_parts,
                patch("psutil.disk_io_counters") as mock_disk_io,
                patch("psutil.net_io_counters") as mock_net_io,
                patch("sqlite3.connect") as mock_sqlite,
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
                # Make SQLite connection fail to trigger database service error
                mock_sqlite.side_effect = Exception("Database connection failed")

                service = HealthCheckService()
                response = service.get_system_health()

                # Database service should be unhealthy
                assert response.services["database"].status == HealthStatus.UNHEALTHY
                assert response.services["database"].error_message is not None

                # The database error message should appear in failure_reasons
                db_error = response.services["database"].error_message
                assert any(
                    "Database" in reason and db_error in reason
                    for reason in response.failure_reasons
                ), f"Database error '{db_error}' not found in failure_reasons: {response.failure_reasons}"

    def test_degraded_service_error_appears_in_failure_reasons(self):
        """When a service is degraded with an error message, it should appear in failure_reasons."""
        from code_indexer.server.services.health_service import HealthCheckService

        with patch(
            "code_indexer.server.services.health_service.DatabaseHealthService"
        ) as mock_db_cls:
            mock_db = MagicMock()
            mock_db.get_all_database_health.return_value = [
                DatabaseHealthResult(
                    file_name="db.db",
                    display_name="DB",
                    status=DatabaseHealthStatus.HEALTHY,
                    checks={"connect": CheckResult(passed=True)},
                    db_path="/path/db.db",
                )
            ]
            mock_db_cls.return_value = mock_db

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
                # Set disk space in warning range (80-90% used = DEGRADED)
                mock_disk.return_value = MagicMock(
                    free=30 * 1024**3,  # 30GB free
                    used=170 * 1024**3,  # 170GB used
                    total=200 * 1024**3,
                    percent=85.0,  # 85% used (between 80% warning and 90% critical)
                )
                mock_parts.return_value = []
                mock_disk_io.return_value = MagicMock(read_bytes=0, write_bytes=0)
                mock_net_io.return_value = MagicMock(bytes_recv=0, bytes_sent=0)

                service = HealthCheckService()
                response = service.get_system_health()

                # Storage service should be degraded due to low disk space
                assert response.services["storage"].status == HealthStatus.DEGRADED
                assert response.services["storage"].error_message is not None

                # The storage warning message should appear in failure_reasons
                storage_error = response.services["storage"].error_message
                assert any(
                    "Storage" in reason and storage_error in reason
                    for reason in response.failure_reasons
                ), f"Storage warning '{storage_error}' not found in failure_reasons: {response.failure_reasons}"
