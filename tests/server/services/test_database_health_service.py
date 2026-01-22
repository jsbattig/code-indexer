"""
Tests for Database Health Service (Story #712).

TDD: Tests written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import sqlite3
import tempfile
from pathlib import Path
from typing import Generator

import pytest


# =============================================================================
# Phase 1: Core Service Tests and Data Model Tests
# =============================================================================


class TestDatabaseHealthService:
    """Tests for database health service checking all 8 central databases."""

    @pytest.fixture
    def temp_server_dir(self) -> Generator[Path, None, None]:
        """Create temporary server directory with all database files."""
        with tempfile.TemporaryDirectory(prefix="cidx_health_test_") as tmp:
            server_dir = Path(tmp)
            data_dir = server_dir / "data"
            data_dir.mkdir(parents=True)

            # Create all 8 central database files with proper schema
            databases = {
                "cidx_server.db": "CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)",
                "oauth.db": "CREATE TABLE IF NOT EXISTS oauth_providers (id INTEGER PRIMARY KEY)",
                "refresh_tokens.db": "CREATE TABLE IF NOT EXISTS tokens (id INTEGER PRIMARY KEY)",
                "logs.db": "CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY)",
                "search_config.db": "CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY)",
                "file_content_limits.db": "CREATE TABLE IF NOT EXISTS limits (id INTEGER PRIMARY KEY)",
                "groups.db": "CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY)",
                "payload_cache.db": "CREATE TABLE IF NOT EXISTS cache (id INTEGER PRIMARY KEY)",
            }

            for db_name, schema in databases.items():
                # Main server DB goes in data/, others in root
                if db_name == "cidx_server.db":
                    db_path = data_dir / db_name
                else:
                    db_path = server_dir / db_name
                with sqlite3.connect(str(db_path)) as conn:
                    conn.execute(schema)
                    conn.commit()

            yield server_dir

    def test_health_service_checks_all_8_databases(self, temp_server_dir: Path):
        """
        AC1: Health service checks all 8 central databases.

        Given the health service is initialized
        When get_all_database_health() is called
        Then it returns health status for exactly 8 databases
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        service = DatabaseHealthService(server_dir=str(temp_server_dir))
        health_results = service.get_all_database_health()

        assert (
            len(health_results) == 8
        ), f"Expected 8 databases, got {len(health_results)}"

        # Verify all expected databases are present
        expected_files = {
            "cidx_server.db",
            "oauth.db",
            "refresh_tokens.db",
            "logs.db",
            "search_config.db",
            "file_content_limits.db",
            "groups.db",
            "payload_cache.db",
        }
        actual_files = {result.file_name for result in health_results}
        assert (
            actual_files == expected_files
        ), f"Missing databases: {expected_files - actual_files}"

    def test_health_service_provides_display_names(self, temp_server_dir: Path):
        """
        AC1: Health results include human-readable display names.

        Given the health service is initialized
        When get_all_database_health() is called
        Then each result has a display_name matching the specification
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        service = DatabaseHealthService(server_dir=str(temp_server_dir))
        health_results = service.get_all_database_health()

        expected_display_names = {
            "cidx_server.db": "Main Server",
            "oauth.db": "OAuth",
            "refresh_tokens.db": "Refresh Tokens",
            "logs.db": "Logs",
            "search_config.db": "Search Config",
            "file_content_limits.db": "File Limits",
            "groups.db": "Groups",
            "payload_cache.db": "Payload Cache",
        }

        for result in health_results:
            expected_name = expected_display_names.get(result.file_name)
            assert result.display_name == expected_name, (
                f"Expected display name '{expected_name}' for {result.file_name}, "
                f"got '{result.display_name}'"
            )


class TestDatabaseHealthResult:
    """Tests for DatabaseHealthResult dataclass."""

    def test_health_result_structure(self):
        """
        DatabaseHealthResult has all required fields.

        The result dataclass should contain:
        - file_name: str
        - display_name: str
        - status: DatabaseHealthStatus
        - checks: Dict[str, CheckResult]
        - get_tooltip() method
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthResult,
            DatabaseHealthStatus,
            CheckResult,
        )

        # Verify all required fields exist and are properly typed
        result = DatabaseHealthResult(
            file_name="test.db",
            display_name="Test",
            status=DatabaseHealthStatus.HEALTHY,
            checks={
                "connect": CheckResult(passed=True, error_message=None),
                "read": CheckResult(passed=True, error_message=None),
                "write": CheckResult(passed=True, error_message=None),
                "integrity": CheckResult(passed=True, error_message=None),
                "not_locked": CheckResult(passed=True, error_message=None),
            },
        )

        assert result.file_name == "test.db"
        assert result.display_name == "Test"
        assert result.status == DatabaseHealthStatus.HEALTHY
        assert len(result.checks) == 5
        assert callable(getattr(result, "get_tooltip", None))

    def test_check_result_structure(self):
        """
        CheckResult has passed flag and optional error_message.
        """
        from code_indexer.server.services.database_health_service import CheckResult

        # Success case
        success = CheckResult(passed=True, error_message=None)
        assert success.passed is True
        assert success.error_message is None

        # Failure case
        failure = CheckResult(passed=False, error_message="database locked")
        assert failure.passed is False
        assert failure.error_message == "database locked"


# =============================================================================
# Phase 2: Individual Health Check Tests
# =============================================================================


class TestDatabaseHealthChecks:
    """Tests for the 5-point health check system per database."""

    @pytest.fixture
    def temp_db_path(self) -> Generator[Path, None, None]:
        """Create a temporary healthy database."""
        with tempfile.TemporaryDirectory(prefix="cidx_health_db_") as tmp:
            db_path = Path(tmp) / "test.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
                conn.commit()
            yield db_path

    def test_connect_check_success(self, temp_db_path: Path):
        """AC1: Connect check passes for accessible database."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        result = DatabaseHealthService.check_database_health(str(temp_db_path))

        assert result.checks["connect"].passed is True
        assert result.checks["connect"].error_message is None

    def test_connect_check_failure_missing_file(self, temp_db_path: Path):
        """AC1: Connect check fails for missing database."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        nonexistent_path = temp_db_path.parent / "nonexistent.db"
        result = DatabaseHealthService.check_database_health(str(nonexistent_path))

        assert result.checks["connect"].passed is False
        assert result.checks["connect"].error_message is not None

    def test_read_check_success(self, temp_db_path: Path):
        """AC1: Read check passes for readable database."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        result = DatabaseHealthService.check_database_health(str(temp_db_path))

        assert result.checks["read"].passed is True
        assert result.checks["read"].error_message is None

    def test_write_check_creates_health_table(self, temp_db_path: Path):
        """AC1: Write check passes and creates _health_check table."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        result = DatabaseHealthService.check_database_health(str(temp_db_path))

        assert result.checks["write"].passed is True

        # Verify _health_check table was created and updated
        with sqlite3.connect(str(temp_db_path)) as conn:
            cursor = conn.execute("SELECT last_check FROM _health_check WHERE id = 1")
            row = cursor.fetchone()
            assert row is not None, "_health_check table should have a row"

    def test_integrity_check_success(self, temp_db_path: Path):
        """AC1: PRAGMA quick_check passes for healthy database."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        result = DatabaseHealthService.check_database_health(str(temp_db_path))

        assert result.checks["integrity"].passed is True
        assert result.checks["integrity"].error_message is None

    def test_lock_check_success(self, temp_db_path: Path):
        """AC1: Not-locked check passes when database is not exclusively locked."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        result = DatabaseHealthService.check_database_health(str(temp_db_path))

        assert result.checks["not_locked"].passed is True
        assert result.checks["not_locked"].error_message is None


# =============================================================================
# Phase 3a: Status Determination Tests (green/yellow/red)
# =============================================================================


class TestDatabaseHealthStatus:
    """Tests for health status determination (green/yellow/red)."""

    @pytest.fixture
    def healthy_db_path(self) -> Generator[Path, None, None]:
        """Create a healthy database."""
        with tempfile.TemporaryDirectory(prefix="cidx_status_") as tmp:
            db_path = Path(tmp) / "healthy.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
                conn.commit()
            yield db_path

    def test_all_checks_pass_status_green(self, healthy_db_path: Path):
        """AC1: Status is GREEN when all 5 checks pass."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        result = DatabaseHealthService.check_database_health(str(healthy_db_path))

        assert result.status == DatabaseHealthStatus.HEALTHY

    def test_non_critical_fails_status_yellow(self):
        """AC1: Status is YELLOW when non-critical checks fail but critical pass."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
            CheckResult,
        )

        # Create checks where write fails but connect/read pass
        checks = {
            "connect": CheckResult(passed=True, error_message=None),
            "read": CheckResult(passed=True, error_message=None),
            "write": CheckResult(passed=False, error_message="database locked"),
            "integrity": CheckResult(passed=True, error_message=None),
            "not_locked": CheckResult(passed=True, error_message=None),
        }

        status = DatabaseHealthService._determine_status(checks)

        assert status == DatabaseHealthStatus.WARNING

    def test_critical_checks_fail_status_red(self, healthy_db_path: Path):
        """AC1: Status is RED when critical checks fail (connect/read)."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        healthy_db_path.unlink()
        result = DatabaseHealthService.check_database_health(str(healthy_db_path))

        assert result.status == DatabaseHealthStatus.ERROR


# =============================================================================
# Phase 3b: Tooltip Tests (AC2, AC3)
# =============================================================================


class TestDatabaseTooltips:
    """Tests for AC2 (healthy tooltip) and AC3 (unhealthy tooltip)."""

    @pytest.fixture
    def healthy_db_path(self) -> Generator[Path, None, None]:
        """Create a healthy database."""
        with tempfile.TemporaryDirectory(prefix="cidx_tooltip_") as tmp:
            db_path = Path(tmp) / "healthy.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY)")
                conn.commit()
            yield db_path

    def test_healthy_database_tooltip_shows_only_name(self, healthy_db_path: Path):
        """AC2: Healthy database tooltip shows database name and path."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        result = DatabaseHealthService.check_database_health(
            str(healthy_db_path), display_name="Main Server"
        )

        assert result.status == DatabaseHealthStatus.HEALTHY
        tooltip = result.get_tooltip()
        # Tooltip should contain display name and path (no error info for healthy DB)
        assert "Main Server" in tooltip
        assert str(healthy_db_path) in tooltip
        # Should not contain error information for healthy database
        assert "Connect:" not in tooltip
        assert "failed" not in tooltip

    def test_unhealthy_database_tooltip_shows_failure(self, healthy_db_path: Path):
        """AC3: Unhealthy database tooltip shows name, path, AND failed condition."""
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        healthy_db_path.unlink()
        result = DatabaseHealthService.check_database_health(
            str(healthy_db_path), display_name="OAuth"
        )

        assert result.status == DatabaseHealthStatus.ERROR
        tooltip = result.get_tooltip()
        # Tooltip should contain display name, path, and error info
        assert "OAuth" in tooltip
        assert str(healthy_db_path) in tooltip
        # Should contain error information (check name + error message)
        assert "Connect:" in tooltip or "failed" in tooltip


# =============================================================================
# AC5: Disk Metrics Enhancement Tests
# =============================================================================


class TestDiskMetricsEnhancement:
    """Tests for AC5: Disk storage complete metrics with used/free and percentages."""

    def test_system_health_info_has_disk_used_fields(self):
        """AC5: SystemHealthInfo includes disk_used_space_gb and disk_used_percent."""
        from code_indexer.server.models.api_models import SystemHealthInfo

        # Verify new fields exist by constructing with them
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=0,
            disk_free_space_gb=100.0,
            disk_used_space_gb=50.0,
            disk_free_percent=66.7,
            disk_used_percent=33.3,
        )

        assert info.disk_used_space_gb == 50.0
        assert info.disk_free_percent == 66.7
        assert info.disk_used_percent == 33.3

    def test_disk_percentages_add_to_100(self):
        """AC5: Disk free and used percentages should add up to 100%."""
        from code_indexer.server.services.health_service import HealthCheckService

        service = HealthCheckService()
        system_info = service._get_system_info()

        # Verify percentages exist and sum to approximately 100
        total_percent = system_info.disk_free_percent + system_info.disk_used_percent
        assert (
            abs(total_percent - 100.0) < 0.1
        ), f"Percentages should add to 100, got {total_percent}"


# =============================================================================
# AC6: Activated Repos Count Fix Tests
# =============================================================================


class TestActivatedReposCountFix:
    """Tests for AC6: Activated repos count should not flash/change after render."""

    def test_get_stats_partial_accepts_user_role_parameter(self):
        """AC6: get_stats_partial should accept user_role parameter."""
        from code_indexer.server.services.dashboard_service import DashboardService
        import inspect

        sig = inspect.signature(DashboardService.get_stats_partial)
        param_names = list(sig.parameters.keys())

        assert (
            "user_role" in param_names
        ), "get_stats_partial must accept user_role parameter to fix AC6"

    def test_get_stats_partial_passes_user_role_to_repo_counts(self):
        """AC6: get_stats_partial should pass user_role to _get_repo_counts."""
        from code_indexer.server.services.dashboard_service import DashboardService
        import inspect

        source = inspect.getsource(DashboardService.get_stats_partial)

        assert (
            "_get_repo_counts" in source and "user_role" in source
        ), "get_stats_partial must pass user_role to _get_repo_counts"


# =============================================================================
# Lazy-Loaded Database Tests
# =============================================================================


class TestLazyLoadedDatabases:
    """Tests for graceful handling of lazy-loaded databases."""

    def test_lazy_loaded_database_not_initialized_status(self):
        """
        Lazy-loaded database that doesn't exist yet gets NOT_INITIALIZED status.

        Given a lazy-loaded database file (search_config.db or file_content_limits.db)
        When the database file doesn't exist yet
        Then the health check returns NOT_INITIALIZED status instead of ERROR
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        with tempfile.TemporaryDirectory(prefix="cidx_lazy_test_") as tmp:
            # Create non-existent path for lazy-loaded database
            db_path = Path(tmp) / "search_config.db"

            result = DatabaseHealthService.check_database_health(
                str(db_path), display_name="Search Config"
            )

            assert result.status == DatabaseHealthStatus.NOT_INITIALIZED
            assert result.checks["connect"].passed is False
            assert (
                result.checks["connect"].error_message == "Not initialized (optional)"
            )

    def test_lazy_loaded_database_initialized_is_healthy(self):
        """
        Lazy-loaded database that exists and is healthy gets HEALTHY status.

        Given a lazy-loaded database file (search_config.db)
        When the database file exists and all checks pass
        Then the health check returns HEALTHY status
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        with tempfile.TemporaryDirectory(prefix="cidx_lazy_test_") as tmp:
            # Create lazy-loaded database
            db_path = Path(tmp) / "search_config.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("CREATE TABLE config (id INTEGER PRIMARY KEY)")
                conn.commit()

            result = DatabaseHealthService.check_database_health(
                str(db_path), display_name="Search Config"
            )

            assert result.status == DatabaseHealthStatus.HEALTHY
            assert result.checks["connect"].passed is True

    def test_non_lazy_database_missing_is_error(self):
        """
        Non-lazy-loaded database that doesn't exist gets ERROR status.

        Given a non-lazy-loaded database (e.g., oauth.db)
        When the database file doesn't exist
        Then the health check returns ERROR status (not NOT_INITIALIZED)
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
            DatabaseHealthStatus,
        )

        with tempfile.TemporaryDirectory(prefix="cidx_lazy_test_") as tmp:
            # Create non-existent path for non-lazy database
            db_path = Path(tmp) / "oauth.db"

            result = DatabaseHealthService.check_database_health(
                str(db_path), display_name="OAuth"
            )

            assert result.status == DatabaseHealthStatus.ERROR
            assert result.checks["connect"].passed is False
            assert "file not found" in result.checks["connect"].error_message

    def test_lazy_loaded_database_tooltip(self):
        """
        Lazy-loaded database tooltip shows 'Not initialized (optional)'.

        Given a lazy-loaded database that doesn't exist yet
        When get_tooltip() is called
        Then it shows the display name, path, and 'Not initialized (optional)'
        """
        from code_indexer.server.services.database_health_service import (
            DatabaseHealthService,
        )

        with tempfile.TemporaryDirectory(prefix="cidx_lazy_test_") as tmp:
            db_path = Path(tmp) / "file_content_limits.db"

            result = DatabaseHealthService.check_database_health(
                str(db_path), display_name="File Limits"
            )

            tooltip = result.get_tooltip()
            assert "File Limits" in tooltip
            assert str(db_path) in tooltip
            assert "Not initialized (optional)" in tooltip

    def test_both_lazy_databases_defined(self):
        """
        Verify both lazy-loaded databases are defined in LAZY_LOADED_DATABASES.

        This test documents which databases are lazy-loaded and ensures
        they're properly configured in the constant.
        """
        from code_indexer.server.services.database_health_service import (
            LAZY_LOADED_DATABASES,
        )

        assert "search_config.db" in LAZY_LOADED_DATABASES
        assert "file_content_limits.db" in LAZY_LOADED_DATABASES
        assert len(LAZY_LOADED_DATABASES) == 2
