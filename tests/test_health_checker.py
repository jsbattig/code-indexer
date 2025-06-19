"""Tests for HealthChecker utility class."""

import time
import socket
from unittest.mock import Mock, patch, MagicMock
import httpx

from code_indexer.services.health_checker import HealthChecker


class TestHealthChecker:
    """Test HealthChecker functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.health_checker = HealthChecker()

    def test_init_without_config(self):
        """Test initialization without config manager."""
        hc = HealthChecker()
        assert hc.config_manager is None
        assert hc.default_timeouts["service_startup"] == 180
        assert hc.default_polling["initial_interval"] == 0.5

    def test_init_with_config(self):
        """Test initialization with config manager."""
        mock_config = Mock()
        hc = HealthChecker(mock_config)
        assert hc.config_manager == mock_config

    def test_get_timeouts_default(self):
        """Test getting default timeouts."""
        timeouts = self.health_checker.get_timeouts()
        expected_keys = [
            "service_startup",
            "service_shutdown",
            "port_release",
            "cleanup_validation",
            "health_check",
            "data_cleaner_startup",
        ]
        for key in expected_keys:
            assert key in timeouts
            assert isinstance(timeouts[key], int)

    def test_get_timeouts_from_config(self):
        """Test getting timeouts from config dictionary."""
        config_dict = {"timeouts": {"service_startup": 300, "health_check": 120}}
        hc = HealthChecker(config_dict)
        timeouts = hc.get_timeouts()
        assert timeouts["service_startup"] == 300
        assert timeouts["health_check"] == 120

    def test_get_polling_config_default(self):
        """Test getting default polling config."""
        polling = self.health_checker.get_polling_config()
        assert polling["initial_interval"] == 0.5
        assert polling["backoff_factor"] == 1.2
        assert polling["max_interval"] == 2.0

    def test_wait_for_condition_success_immediate(self):
        """Test wait_for_condition when condition is immediately true."""

        def always_true():
            return True

        start_time = time.time()
        result = self.health_checker.wait_for_condition(always_true, timeout=5)
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed < 1  # Should complete almost immediately

    def test_wait_for_condition_success_delayed(self):
        """Test wait_for_condition when condition becomes true after delay."""
        call_count = 0

        def becomes_true():
            nonlocal call_count
            call_count += 1
            return call_count >= 3  # True on third call

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            becomes_true, timeout=10, interval=0.1
        )
        elapsed = time.time() - start_time

        assert result is True
        assert call_count >= 3
        assert 0.2 <= elapsed <= 2  # Should take some time but not too much

    def test_wait_for_condition_timeout(self):
        """Test wait_for_condition when condition never becomes true."""

        def always_false():
            return False

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            always_false, timeout=1, interval=0.1
        )
        elapsed = time.time() - start_time

        assert result is False
        assert 0.9 <= elapsed <= 1.5  # Should timeout around 1 second

    def test_wait_for_condition_exponential_backoff(self):
        """Test that exponential backoff increases intervals."""
        intervals = []
        call_count = 0

        def track_intervals():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                intervals.append(time.time())
            elif call_count <= 4:
                intervals.append(time.time())
                return False
            else:
                return True  # Stop after collecting some intervals

        self.health_checker.wait_for_condition(
            track_intervals,
            timeout=10,
            interval=0.1,
            backoff=2.0,  # More aggressive for testing
            max_interval=1.0,
        )

        # Verify intervals increase (with some tolerance for timing)
        if len(intervals) >= 3:
            interval1 = intervals[2] - intervals[1]
            interval2 = intervals[1] - intervals[0] if len(intervals) > 2 else 0
            # Second interval should be larger than first (allowing for timing variance)
            assert interval1 > interval2 * 1.5 or interval1 > 0.15

    def test_wait_for_condition_exception_handling(self):
        """Test wait_for_condition handles exceptions gracefully."""
        call_count = 0

        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Test exception")
            return True

        result = self.health_checker.wait_for_condition(
            sometimes_fails, timeout=5, interval=0.1
        )

        assert result is True
        assert call_count >= 3

    def test_is_port_available_free_port(self):
        """Test port availability check on free port."""
        # Use a high port number that's likely to be free
        result = self.health_checker.is_port_available(65432)
        assert result is True

    def test_is_port_available_used_port(self):
        """Test port availability check on used port."""
        # Create a server socket to occupy a port
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind(("localhost", 0))  # Let OS choose port
        port = server_socket.getsockname()[1]
        server_socket.listen(1)

        try:
            result = self.health_checker.is_port_available(port)
            assert result is False
        finally:
            server_socket.close()

    def test_wait_for_ports_available_success(self):
        """Test waiting for ports to become available."""
        # Use high port numbers that should be free
        ports = [65430, 65431, 65432]
        result = self.health_checker.wait_for_ports_available(ports, timeout=5)
        assert result is True

    def test_wait_for_ports_available_timeout(self):
        """Test waiting for ports times out when ports are occupied."""
        # Create servers to occupy ports
        servers = []
        ports = []

        try:
            for i in range(2):
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.bind(("localhost", 0))
                port = server.getsockname()[1]
                server.listen(1)
                servers.append(server)
                ports.append(port)

            result = self.health_checker.wait_for_ports_available(ports, timeout=1)
            assert result is False
        finally:
            for server in servers:
                server.close()

    @patch("code_indexer.services.health_checker.httpx.Client")
    def test_is_service_healthy_success(self, mock_client_class):
        """Test service health check success."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response

        result = self.health_checker.is_service_healthy("http://localhost:8080/health")
        assert result is True
        mock_client.get.assert_called_once_with("http://localhost:8080/health")

    @patch("code_indexer.services.health_checker.httpx.Client")
    def test_is_service_healthy_failure(self, mock_client_class):
        """Test service health check failure."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_response = Mock()
        mock_response.status_code = 500
        mock_client.get.return_value = mock_response

        result = self.health_checker.is_service_healthy("http://localhost:8080/health")
        assert result is False

    @patch("code_indexer.services.health_checker.httpx.Client")
    def test_is_service_healthy_exception(self, mock_client_class):
        """Test service health check with exception."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.RequestError("Connection failed")

        result = self.health_checker.is_service_healthy("http://localhost:8080/health")
        assert result is False

    @patch("code_indexer.services.health_checker.subprocess.run")
    def test_is_container_running_true(self, mock_run):
        """Test container running check when container is running."""
        mock_result = Mock()
        mock_result.stdout = "test-container\n"
        mock_run.return_value = mock_result

        result = self.health_checker.is_container_running("test-container", "podman")
        assert result is True
        mock_run.assert_called_once_with(
            [
                "podman",
                "ps",
                "--filter",
                "name=test-container",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("code_indexer.services.health_checker.subprocess.run")
    def test_is_container_running_false(self, mock_run):
        """Test container running check when container is not running."""
        mock_result = Mock()
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        result = self.health_checker.is_container_running("test-container", "docker")
        assert result is False

    @patch("code_indexer.services.health_checker.subprocess.run")
    def test_is_container_stopped(self, mock_run):
        """Test container stopped check."""
        mock_result = Mock()
        mock_result.stdout = ""  # Container not running
        mock_run.return_value = mock_result

        result = self.health_checker.is_container_stopped("test-container")
        assert result is True

    def test_get_container_engine_timeouts_podman(self):
        """Test getting timeouts optimized for Podman."""
        timeouts = self.health_checker.get_container_engine_timeouts("podman")
        base_timeouts = self.health_checker.get_timeouts()

        # Podman should have longer timeouts
        assert timeouts["port_release"] > base_timeouts["port_release"]
        assert timeouts["service_shutdown"] > base_timeouts["service_shutdown"]

    def test_get_container_engine_timeouts_docker(self):
        """Test getting timeouts for Docker."""
        timeouts = self.health_checker.get_container_engine_timeouts("docker")
        base_timeouts = self.health_checker.get_timeouts()

        # Docker should use base timeouts
        assert timeouts["port_release"] == base_timeouts["port_release"]
        assert timeouts["service_shutdown"] == base_timeouts["service_shutdown"]

    @patch.object(HealthChecker, "is_container_stopped")
    @patch.object(HealthChecker, "is_port_available")
    def test_wait_for_cleanup_complete_success(
        self, mock_port_available, mock_container_stopped
    ):
        """Test successful cleanup completion."""
        mock_container_stopped.return_value = True
        mock_port_available.return_value = True

        result = self.health_checker.wait_for_cleanup_complete(
            ["container1", "container2"], [6333, 11434], "podman", timeout=5
        )

        assert result is True

    @patch.object(HealthChecker, "is_container_stopped")
    @patch.object(HealthChecker, "is_port_available")
    def test_wait_for_cleanup_complete_timeout(
        self, mock_port_available, mock_container_stopped
    ):
        """Test cleanup completion timeout."""
        mock_container_stopped.return_value = True
        mock_port_available.return_value = False  # Ports still in use

        result = self.health_checker.wait_for_cleanup_complete(
            ["container1"], [6333], "docker", timeout=1
        )

        assert result is False


class TestHealthCheckerIntegration:
    """Integration tests for HealthChecker with real services."""

    def setup_method(self):
        """Setup test environment."""
        self.health_checker = HealthChecker()

    def test_real_port_availability(self):
        """Test port availability checking with real ports."""
        # Test a port that should be available
        high_port = 65500
        assert self.health_checker.is_port_available(high_port) is True

        # Test a port that might be in use (SSH on many systems)
        # We don't assert this as it depends on system configuration
        ssh_port_available = self.health_checker.is_port_available(22)
        assert isinstance(ssh_port_available, bool)

    def test_wait_for_condition_real_timing(self):
        """Test wait_for_condition with real timing."""
        start_time = time.time()
        call_times = []

        def time_tracker():
            call_times.append(time.time() - start_time)
            return len(call_times) >= 5  # Return True after 5 calls

        result = self.health_checker.wait_for_condition(
            time_tracker, timeout=10, interval=0.1, backoff=1.5
        )

        assert result is True
        assert len(call_times) == 5

        # Verify exponential backoff in real timing
        if len(call_times) >= 3:
            # Allow some tolerance for timing variations
            assert call_times[1] > call_times[0]
            assert call_times[2] > call_times[1]
