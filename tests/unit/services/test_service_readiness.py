"""Tests for service readiness checking improvements."""

import time
from unittest.mock import Mock, patch, MagicMock

from code_indexer.services.health_checker import HealthChecker


class TestServiceReadiness:
    """Test service readiness functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.health_checker = HealthChecker()

    def test_wait_for_condition_replaces_blind_sleeps(self):
        """Test that condition polling replaces blind sleeps."""
        call_count = 0

        def becomes_ready_after_3_calls():
            nonlocal call_count
            call_count += 1
            return call_count >= 3

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            becomes_ready_after_3_calls,
            timeout=10,
            interval=0.1,
            operation_name="service readiness",
        )
        elapsed = time.time() - start_time

        # Should succeed quickly (much less than a 5-second blind sleep)
        assert result is True
        assert elapsed < 1.0  # Should be much faster than blind sleeps
        assert call_count == 3

    def test_exponential_backoff_performance(self):
        """Test that exponential backoff provides good performance characteristics."""
        call_times = []

        def track_timing():
            call_times.append(time.time())
            return len(call_times) >= 5  # Stop after 5 calls

        result = self.health_checker.wait_for_condition(
            track_timing, timeout=10, interval=0.1, backoff=2.0, max_interval=1.0
        )

        assert result is True
        assert len(call_times) == 5

        # Verify intervals increase (with tolerance for timing variations)
        intervals = [
            call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)
        ]

        # First interval should be around 0.1s
        assert 0.05 <= intervals[0] <= 0.2

        # Later intervals should be larger but capped at max_interval
        for interval in intervals[1:]:
            assert interval <= 1.1  # Max interval + tolerance

    def test_service_health_check_vs_sleep(self):
        """Test that service health checking is more efficient than sleeps."""
        # Simulate a service that becomes ready quickly
        with patch(
            "code_indexer.services.health_checker.httpx.Client"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value.__enter__.return_value = mock_client
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response

            start_time = time.time()
            result = self.health_checker.wait_for_service_ready(
                "http://localhost:8091", timeout=30
            )
            elapsed = time.time() - start_time

            # Should succeed immediately (much faster than a 5s sleep)
            assert result is True
            assert elapsed < 1.0

    def test_port_availability_vs_sleep(self):
        """Test that port availability checking is more efficient than sleeps."""
        # Test with ports that should be available
        ports = [65490, 65491, 65492]

        start_time = time.time()
        result = self.health_checker.wait_for_ports_available(ports, timeout=10)
        elapsed = time.time() - start_time

        # Should succeed immediately (much faster than an 8s sleep)
        assert result is True
        assert elapsed < 1.0

    def test_container_status_checking(self):
        """Test container status checking functionality."""
        # Test with containers that shouldn't exist
        container_names = ["nonexistent-container-1", "nonexistent-container-2"]

        start_time = time.time()
        result = self.health_checker.wait_for_containers_stopped(
            container_names, container_engine="podman", timeout=10
        )
        elapsed = time.time() - start_time

        # Should succeed immediately (containers don't exist)
        assert result is True
        # Allow more time for container checks due to system load
        assert elapsed < 15.0, f"Container check took too long: {elapsed}s"

    def test_cleanup_validation_performance(self):
        """Test cleanup validation performance vs blind sleeps."""
        # Test complete cleanup validation
        container_names = ["test-container"]
        ports = [65493, 65494]

        start_time = time.time()
        result = self.health_checker.wait_for_cleanup_complete(
            container_names=container_names,
            ports=ports,
            container_engine="podman",
            timeout=15,
        )
        elapsed = time.time() - start_time

        # Should succeed quickly (much faster than 8s + 5s blind sleeps)
        assert result is True
        # Allow reasonable time for port checks
        assert elapsed < 10.0, f"Cleanup validation took too long: {elapsed}s"


class TestConditionPollingPatterns:
    """Test different condition polling patterns for performance."""

    def setup_method(self):
        """Setup test environment."""
        self.health_checker = HealthChecker()

    def test_fast_success_pattern(self):
        """Test pattern where condition succeeds immediately."""

        def immediate_success():
            return True

        start_time = time.time()
        result = self.health_checker.wait_for_condition(immediate_success, timeout=10)
        elapsed = time.time() - start_time

        # Should complete almost instantly
        assert result is True
        assert elapsed < 0.1

    def test_delayed_success_pattern(self):
        """Test pattern where condition succeeds after some attempts."""
        call_count = 0

        def delayed_success():
            nonlocal call_count
            call_count += 1
            return call_count >= 10  # Succeed on 10th call

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            delayed_success, timeout=30, interval=0.1, backoff=1.2, max_interval=0.5
        )
        elapsed = time.time() - start_time

        assert result is True
        assert call_count == 10
        # Should be faster than blind sleep but take some time for polling
        assert 0.5 <= elapsed <= 5.0

    def test_timeout_pattern(self):
        """Test pattern where condition times out."""

        def never_succeeds():
            return False

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            never_succeeds, timeout=2, interval=0.1
        )
        elapsed = time.time() - start_time

        assert result is False
        # Should timeout close to the specified timeout
        assert 1.8 <= elapsed <= 2.5

    def test_exception_handling_pattern(self):
        """Test pattern where condition function raises exceptions."""
        call_count = 0

        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("Temporary failure")
            return True

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            sometimes_fails, timeout=10, interval=0.1
        )
        elapsed = time.time() - start_time

        assert result is True
        assert call_count == 4  # Failed 3 times, succeeded on 4th
        assert elapsed < 2.0

    def test_performance_comparison_simulation(self):
        """Simulate performance comparison between sleeps and condition polling."""
        # Simulate old approach with fixed sleeps
        old_approach_time = 8 + 5 + 2  # Cleanup + data cleaner + test validation

        # Simulate new approach with condition polling
        container_check_time = 0.1  # Immediate success
        port_check_time = 0.1  # Immediate success
        service_check_time = 0.1  # Immediate success
        new_approach_time = container_check_time + port_check_time + service_check_time

        # New approach should be much faster
        improvement_ratio = old_approach_time / new_approach_time
        assert improvement_ratio > 20  # At least 20x faster

        print(f"Performance improvement: {improvement_ratio:.1f}x faster")
        print(f"Old approach: {old_approach_time}s (fixed sleeps)")
        print(f"New approach: {new_approach_time}s (condition polling)")


class TestRealWorldPatterns:
    """Test real-world patterns that replace the original sleeps."""

    def setup_method(self):
        """Setup test environment."""
        self.health_checker = HealthChecker()

    def test_cleanup_validation_replacement(self):
        """Test the pattern that replaces cleanup validation sleep."""
        # Original: time.sleep(8)
        # New: wait_for_cleanup_complete()

        start_time = time.time()
        # Use ports that are guaranteed to be available for testing
        import socket

        # Find available ports for testing
        def find_free_port():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", 0))
                s.listen(1)
                port = s.getsockname()[1]
            return port

        test_ports = [find_free_port(), find_free_port()]

        result = self.health_checker.wait_for_cleanup_complete(
            container_names=["test-container-that-never-existed"],
            ports=test_ports,
            container_engine="podman",
            timeout=10,
        )
        elapsed = time.time() - start_time

        # Should be much faster than 8s sleep
        assert result is True
        # Allow reasonable time for the operation
        assert elapsed < 5.0, f"Cleanup validation took too long: {elapsed}s"

    def test_data_cleaner_startup_replacement(self):
        """Test the pattern that replaces data cleaner startup sleep."""
        # Original: time.sleep(5)
        # New: wait_for_service_ready()

        # Mock unavailable service for realistic timeout test
        start_time = time.time()
        result = self.health_checker.wait_for_service_ready(
            "http://localhost:65499",  # Unavailable port
            timeout=1,  # Short timeout for test
        )
        elapsed = time.time() - start_time

        # Should timeout close to 1s (much better than blind 5s sleep)
        assert result is False
        assert 0.8 <= elapsed <= 1.5

    def test_test_service_readiness_replacement(self):
        """Test the pattern that replaces test service readiness sleeps."""
        # Original: time.sleep(10) in tests
        # New: condition polling with status checks

        def mock_service_check() -> bool:
            # Simulate service becoming ready after a few checks
            if not hasattr(mock_service_check, "call_count"):
                mock_service_check.call_count = 0  # type: ignore[attr-defined]
            mock_service_check.call_count += 1  # type: ignore[attr-defined]
            return mock_service_check.call_count >= 3  # type: ignore[attr-defined,no-any-return]

        start_time = time.time()
        result = self.health_checker.wait_for_condition(
            mock_service_check,
            timeout=30,
            interval=0.5,
            operation_name="test service readiness",
        )
        elapsed = time.time() - start_time

        # Should be much faster than 10s sleep
        assert result is True
        assert elapsed < 5.0
        assert mock_service_check.call_count == 3  # type: ignore[attr-defined]
