"""Test server throttling detection functionality."""

from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    ThrottlingStatus,
)


class TestServerThrottlingDetection:
    """Test server-side throttling detection indicators."""

    def test_throttling_status_enum(self):
        """Test that throttling status enum has correct icons."""
        assert ThrottlingStatus.FULL_SPEED.value == "⚡"  # No throttling
        assert ThrottlingStatus.SERVER_THROTTLED.value == "🔴"  # Server-side throttling

    def test_server_throttle_recording(self):
        """Test recording server-side throttle events."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record some server throttles
        manager.record_server_throttle()
        manager.record_server_throttle()

        stats = manager.get_stats()
        assert stats.server_throttle_count == 2
        assert len(manager.recent_server_throttles) == 2

    def test_throttling_status_detection_full_speed(self):
        """Test throttling status detection when at full speed."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # No throttling events recorded
        stats = manager.get_stats()
        assert stats.throttling_status == ThrottlingStatus.FULL_SPEED

    def test_throttling_status_detection_server_throttled(self):
        """Test throttling status detection when server is throttling."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record multiple server throttle events to trigger SERVER_THROTTLED
        for _ in range(3):
            manager.record_server_throttle()

        stats = manager.get_stats()
        assert stats.throttling_status == ThrottlingStatus.SERVER_THROTTLED

    def test_server_throttling_error_detection(self):
        """Test detection of server throttling errors."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Test various server throttling error patterns
        throttling_errors = [
            Exception("HTTP 429 Too Many Requests"),
            Exception("rate limit exceeded"),
            Exception("quota exceeded for API"),
            Exception("timeout waiting for response"),
            Exception("server overload detected"),
        ]

        for error in throttling_errors:
            assert manager._is_server_throttling_error(error)

        # Test non-throttling errors
        normal_errors = [
            Exception("connection refused"),
            Exception("invalid API key"),
            Exception("file not found"),
        ]

        for error in normal_errors:
            assert not manager._is_server_throttling_error(error)

    def test_velocity_indicators_present(self):
        """Test that velocity indicators are included in stats."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        stats = manager.get_stats()

        # Check that embeddings_per_second is present (velocity indicator)
        assert hasattr(stats, "embeddings_per_second")
        assert stats.embeddings_per_second >= 0.0

        # Check that throttling status is present
        assert hasattr(stats, "throttling_status")
        assert isinstance(stats.throttling_status, ThrottlingStatus)
