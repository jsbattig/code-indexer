"""
Unit tests for interval-averaged system metrics in HealthCheckService.

Following TDD methodology - these tests are written FIRST before implementation.
Tests verify:
- AC1: CPU uses interval=None for interval-averaged measurement
- AC2: Disk I/O shows read/write speeds in KB/s
- AC3: Network I/O shows Rx/Tx speeds in KB/s
- AC5: First refresh shows zero for rate metrics
- AC6: API model includes new I/O fields
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from collections import namedtuple

from src.code_indexer.server.models.api_models import SystemHealthInfo


class TestSystemHealthInfoModel:
    """Tests for SystemHealthInfo model with new I/O fields (AC6)."""

    def test_system_health_info_has_disk_read_kb_s_field(self):
        """AC6: SystemHealthInfo should have disk_read_kb_s field."""
        # This test will FAIL initially - field doesn't exist yet
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.0,
            disk_write_kb_s=512.0,
            net_rx_kb_s=2048.0,
            net_tx_kb_s=1024.0,
        )
        assert hasattr(info, 'disk_read_kb_s')
        assert info.disk_read_kb_s == 1024.0

    def test_system_health_info_has_disk_write_kb_s_field(self):
        """AC6: SystemHealthInfo should have disk_write_kb_s field."""
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.0,
            disk_write_kb_s=512.0,
            net_rx_kb_s=2048.0,
            net_tx_kb_s=1024.0,
        )
        assert hasattr(info, 'disk_write_kb_s')
        assert info.disk_write_kb_s == 512.0

    def test_system_health_info_has_net_rx_kb_s_field(self):
        """AC6: SystemHealthInfo should have net_rx_kb_s field."""
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.0,
            disk_write_kb_s=512.0,
            net_rx_kb_s=2048.0,
            net_tx_kb_s=1024.0,
        )
        assert hasattr(info, 'net_rx_kb_s')
        assert info.net_rx_kb_s == 2048.0

    def test_system_health_info_has_net_tx_kb_s_field(self):
        """AC6: SystemHealthInfo should have net_tx_kb_s field."""
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.0,
            disk_write_kb_s=512.0,
            net_rx_kb_s=2048.0,
            net_tx_kb_s=1024.0,
        )
        assert hasattr(info, 'net_tx_kb_s')
        assert info.net_tx_kb_s == 1024.0

    def test_system_health_info_all_io_fields_are_floats(self):
        """AC6: All new I/O fields should be floats."""
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.0,
            disk_write_kb_s=512.0,
            net_rx_kb_s=2048.0,
            net_tx_kb_s=1024.0,
        )
        assert isinstance(info.disk_read_kb_s, float)
        assert isinstance(info.disk_write_kb_s, float)
        assert isinstance(info.net_rx_kb_s, float)
        assert isinstance(info.net_tx_kb_s, float)

    def test_system_health_info_serialization_includes_io_fields(self):
        """AC6: JSON serialization should include all new I/O fields."""
        info = SystemHealthInfo(
            memory_usage_percent=50.0,
            cpu_usage_percent=25.0,
            active_jobs=5,
            disk_free_space_gb=100.0,
            disk_read_kb_s=1024.5,
            disk_write_kb_s=512.25,
            net_rx_kb_s=2048.75,
            net_tx_kb_s=1024.125,
        )
        json_dict = info.model_dump()
        assert 'disk_read_kb_s' in json_dict
        assert 'disk_write_kb_s' in json_dict
        assert 'net_rx_kb_s' in json_dict
        assert 'net_tx_kb_s' in json_dict
        assert json_dict['disk_read_kb_s'] == 1024.5
        assert json_dict['disk_write_kb_s'] == 512.25
        assert json_dict['net_rx_kb_s'] == 2048.75
        assert json_dict['net_tx_kb_s'] == 1024.125


class TestHealthServiceCpuIntervalAveraged:
    """Tests for interval-averaged CPU measurement (AC1)."""

    def test_cpu_percent_uses_interval_none(self):
        """AC1: CPU should use psutil.cpu_percent(interval=None) for interval-averaging."""
        # We need to verify that the service calls cpu_percent with interval=None
        # This test verifies the implementation uses interval=None, not interval=0.1
        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            # Setup mock returns
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000, write_bytes=500000
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            # Import after patching
            from src.code_indexer.server.services.health_service import HealthCheckService

            # Create service and call _get_system_info
            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                service._get_system_info()

            # Verify cpu_percent was called with interval=None
            mock_psutil.cpu_percent.assert_called_once_with(interval=None)


class TestHealthServiceDiskIO:
    """Tests for disk I/O interval-averaged metrics (AC2)."""

    def test_first_call_returns_zero_disk_io(self):
        """AC5: First call should return 0.0 for disk I/O metrics."""
        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000, write_bytes=500000
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                result = service._get_system_info()

            assert result.disk_read_kb_s == 0.0
            assert result.disk_write_kb_s == 0.0

    def test_second_call_calculates_disk_io_rate(self):
        """AC2: Second call should calculate disk I/O in KB/s from counter diffs."""
        DiskCounters = namedtuple('DiskCounters', ['read_bytes', 'write_bytes'])

        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            # First call: 1MB read, 500KB written
            first_counters = DiskCounters(read_bytes=1024 * 1024, write_bytes=512 * 1024)
            # Second call: 2MB read (1MB more), 1MB written (512KB more), 1 second later
            second_counters = DiskCounters(read_bytes=2 * 1024 * 1024, write_bytes=1024 * 1024)

            mock_psutil.disk_io_counters.side_effect = [first_counters, second_counters]

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                # First call - establishes baseline
                service._get_system_info()

                # Manually set the time to 1 second ago to simulate interval
                service._last_disk_time = time.time() - 1.0

                # Second call - should calculate rate
                result = service._get_system_info()

            # Expected: (2MB - 1MB) / 1024 / 1s = 1024 KB/s read
            # Expected: (1MB - 512KB) / 1024 / 1s = 512 KB/s write
            assert abs(result.disk_read_kb_s - 1024.0) < 100  # Allow some tolerance
            assert abs(result.disk_write_kb_s - 512.0) < 100

    def test_disk_io_calculation_formula_accuracy(self):
        """AC2: Verify KB/s formula: (bytes_diff / 1024) / elapsed_seconds."""
        DiskCounters = namedtuple('DiskCounters', ['read_bytes', 'write_bytes'])

        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=0, bytes_sent=0
            )

            # Exact values for verification:
            # Start: 0 bytes, End: 102400 bytes (100 KB), Elapsed: 2 seconds
            # Expected rate: (102400 / 1024) / 2 = 50 KB/s
            first_counters = DiskCounters(read_bytes=0, write_bytes=0)
            second_counters = DiskCounters(read_bytes=102400, write_bytes=204800)

            mock_psutil.disk_io_counters.side_effect = [first_counters, second_counters]

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                # First call
                service._get_system_info()

                # Set elapsed time to exactly 2 seconds
                service._last_disk_time = time.time() - 2.0

                # Second call
                result = service._get_system_info()

            # Expected: 102400 bytes / 1024 / 2 seconds = 50 KB/s read
            # Expected: 204800 bytes / 1024 / 2 seconds = 100 KB/s write
            assert abs(result.disk_read_kb_s - 50.0) < 1.0
            assert abs(result.disk_write_kb_s - 100.0) < 1.0


class TestHealthServiceNetworkIO:
    """Tests for network I/O interval-averaged metrics (AC3)."""

    def test_first_call_returns_zero_network_io(self):
        """AC5: First call should return 0.0 for network I/O metrics."""
        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000, write_bytes=500000
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                result = service._get_system_info()

            assert result.net_rx_kb_s == 0.0
            assert result.net_tx_kb_s == 0.0

    def test_second_call_calculates_network_io_rate(self):
        """AC3: Second call should calculate network I/O in KB/s from counter diffs."""
        NetCounters = namedtuple('NetCounters', ['bytes_recv', 'bytes_sent'])

        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=0, write_bytes=0
            )

            # First call: 1MB received, 500KB sent
            first_counters = NetCounters(bytes_recv=1024 * 1024, bytes_sent=512 * 1024)
            # Second call: 2MB received (1MB more), 1MB sent (512KB more), 1 second later
            second_counters = NetCounters(bytes_recv=2 * 1024 * 1024, bytes_sent=1024 * 1024)

            mock_psutil.net_io_counters.side_effect = [first_counters, second_counters]

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                # First call - establishes baseline
                service._get_system_info()

                # Manually set the time to 1 second ago to simulate interval
                service._last_net_time = time.time() - 1.0

                # Second call - should calculate rate
                result = service._get_system_info()

            # Expected: (2MB - 1MB) / 1024 / 1s = 1024 KB/s rx
            # Expected: (1MB - 512KB) / 1024 / 1s = 512 KB/s tx
            assert abs(result.net_rx_kb_s - 1024.0) < 100
            assert abs(result.net_tx_kb_s - 512.0) < 100

    def test_network_io_calculation_formula_accuracy(self):
        """AC3: Verify KB/s formula: (bytes_diff / 1024) / elapsed_seconds."""
        NetCounters = namedtuple('NetCounters', ['bytes_recv', 'bytes_sent'])

        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=0, write_bytes=0
            )

            # Exact values for verification:
            # Start: 0 bytes, End: 102400 bytes (100 KB) recv, 204800 bytes (200 KB) sent
            # Elapsed: 2 seconds
            # Expected rx rate: (102400 / 1024) / 2 = 50 KB/s
            # Expected tx rate: (204800 / 1024) / 2 = 100 KB/s
            first_counters = NetCounters(bytes_recv=0, bytes_sent=0)
            second_counters = NetCounters(bytes_recv=102400, bytes_sent=204800)

            mock_psutil.net_io_counters.side_effect = [first_counters, second_counters]

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                # First call
                service._get_system_info()

                # Set elapsed time to exactly 2 seconds
                service._last_net_time = time.time() - 2.0

                # Second call
                result = service._get_system_info()

            assert abs(result.net_rx_kb_s - 50.0) < 1.0
            assert abs(result.net_tx_kb_s - 100.0) < 1.0


class TestDashboardRefreshInterval:
    """Tests for dashboard refresh interval (AC4)."""

    def test_dashboard_refresh_interval_is_2_seconds(self):
        """AC4: Dashboard refresh interval should be 2 seconds, not 5 seconds."""
        from pathlib import Path

        # Find the dashboard.html template
        template_path = Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "server" / "web" / "templates" / "dashboard.html"

        if template_path.exists():
            content = template_path.read_text()

            # Verify the interval is 2000ms (2 seconds), not 5000ms
            assert "setInterval(refreshAll, 2000)" in content, \
                "Dashboard should use 2000ms (2 second) refresh interval"

            # Verify 5000ms is NOT present (old interval)
            assert "setInterval(refreshAll, 5000)" not in content, \
                "Dashboard should NOT use 5000ms (5 second) refresh interval"
        else:
            pytest.skip("Dashboard template not found at expected path")


class TestDashboardHealthTemplate:
    """Tests for dashboard health template displaying I/O metrics (AC2, AC3)."""

    def test_dashboard_displays_disk_io_metrics(self):
        """AC2: Dashboard should display disk read/write speeds."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "server" / "web" / "templates" / "partials" / "dashboard_health.html"

        if template_path.exists():
            content = template_path.read_text()

            # Verify disk I/O metrics are displayed
            assert "disk_read_kb_s" in content, \
                "Dashboard should display disk read speed (disk_read_kb_s)"
            assert "disk_write_kb_s" in content, \
                "Dashboard should display disk write speed (disk_write_kb_s)"
        else:
            pytest.skip("Dashboard health template not found at expected path")

    def test_dashboard_displays_network_io_metrics(self):
        """AC3: Dashboard should display network Rx/Tx speeds."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "server" / "web" / "templates" / "partials" / "dashboard_health.html"

        if template_path.exists():
            content = template_path.read_text()

            # Verify network I/O metrics are displayed
            assert "net_rx_kb_s" in content, \
                "Dashboard should display network receive speed (net_rx_kb_s)"
            assert "net_tx_kb_s" in content, \
                "Dashboard should display network transmit speed (net_tx_kb_s)"
        else:
            pytest.skip("Dashboard health template not found at expected path")

    def test_dashboard_displays_io_labels(self):
        """Dashboard should have user-friendly labels for I/O metrics."""
        from pathlib import Path

        template_path = Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "server" / "web" / "templates" / "partials" / "dashboard_health.html"

        if template_path.exists():
            content = template_path.read_text()

            # Verify user-friendly labels exist
            assert "Disk" in content, \
                "Dashboard should have Disk label"
            assert "Network" in content or "Net" in content, \
                "Dashboard should have Network label"
            assert "KB/s" in content, \
                "Dashboard should display KB/s units"
        else:
            pytest.skip("Dashboard health template not found at expected path")


class TestHealthServiceStatePersistence:
    """Tests for state persistence between calls."""

    def test_state_variables_persist_across_calls(self):
        """State variables should persist across _get_system_info calls."""
        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000, write_bytes=500000
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = None
                service._last_disk_time = None
                service._last_net_counters = None
                service._last_net_time = None
                service._get_active_jobs_count = lambda: 0

                # First call
                service._get_system_info()

                # State should now be set
                assert service._last_disk_counters is not None
                assert service._last_disk_time is not None
                assert service._last_net_counters is not None
                assert service._last_net_time is not None

    def test_zero_elapsed_time_no_division_error(self):
        """Edge case: Handle zero elapsed time without division by zero."""
        with patch('src.code_indexer.server.services.health_service.psutil') as mock_psutil:
            mock_psutil.virtual_memory.return_value = MagicMock(percent=50.0)
            mock_psutil.cpu_percent.return_value = 25.0
            mock_psutil.disk_usage.return_value = MagicMock(free=100 * 1024**3)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000, write_bytes=500000
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_recv=2000000, bytes_sent=1000000
            )

            from src.code_indexer.server.services.health_service import HealthCheckService

            with patch.object(HealthCheckService, '__init__', lambda self: None):
                service = HealthCheckService()
                service._last_disk_counters = MagicMock(
                    read_bytes=500000, write_bytes=250000
                )
                service._last_disk_time = time.time()  # Current time = 0 elapsed
                service._last_net_counters = MagicMock(
                    bytes_recv=1000000, bytes_sent=500000
                )
                service._last_net_time = time.time()  # Current time = 0 elapsed
                service._get_active_jobs_count = lambda: 0

                # Should not raise ZeroDivisionError
                result = service._get_system_info()

                # Should return 0.0 when elapsed time is 0 or very small
                assert result.disk_read_kb_s >= 0.0
                assert result.disk_write_kb_s >= 0.0
                assert result.net_rx_kb_s >= 0.0
                assert result.net_tx_kb_s >= 0.0
