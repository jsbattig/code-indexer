"""Tests for throttling status indicators in VectorCalculationManager."""

import time
import pytest
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    ThrottlingStatus,
    VectorCalculationStats,
)
from code_indexer.services.voyage_ai import VoyageAIClient


class TestThrottlingIndicators:
    """Test throttling status indicators."""

    def test_throttling_status_enum(self):
        """Test that throttling status enum has correct icons."""
        assert ThrottlingStatus.FULL_SPEED.value == "⚡"  # No throttling
        assert (
            ThrottlingStatus.CLIENT_THROTTLED.value == "🟡"
        )  # CIDX-initiated throttling
        assert ThrottlingStatus.SERVER_THROTTLED.value == "🔴"  # Server-side throttling

    def test_vector_calculation_stats_includes_throttling(self):
        """Test that VectorCalculationStats includes throttling fields."""
        stats = VectorCalculationStats()

        # Check default values
        assert stats.throttling_status == ThrottlingStatus.FULL_SPEED
        assert stats.client_wait_time == 0.0
        assert stats.server_throttle_count == 0

    def test_client_wait_time_recording(self):
        """Test recording CIDX-initiated wait time for throttling detection."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record some client wait times
        manager.record_client_wait_time(1.5)
        manager.record_client_wait_time(2.0)

        stats = manager.get_stats()
        assert stats.client_wait_time == 3.5
        assert len(manager.recent_wait_events) == 2  # Both waits are > 0.1s threshold

    def test_server_throttle_recording(self):
        """Test recording server-side throttle events (429s, API issues)."""
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

    def test_throttling_status_detection_client_throttled(self):
        """Test throttling status detection when CIDX is throttling requests."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record multiple significant client wait events to trigger new logic
        # Need >5 waits AND avg >0.5s to trigger CLIENT_THROTTLED
        for _ in range(7):
            manager.record_client_wait_time(0.8)  # 7 waits of 0.8s each

        stats = manager.get_stats()
        assert stats.throttling_status == ThrottlingStatus.CLIENT_THROTTLED

    def test_throttling_status_detection_moderate_waits_not_throttled(self):
        """Test that moderate waits don't trigger false throttling detection."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record moderate waits that shouldn't trigger throttling
        # 6 waits of 0.4s each (avg 0.4s < 0.5s threshold)
        for _ in range(6):
            manager.record_client_wait_time(0.4)

        stats = manager.get_stats()
        assert stats.throttling_status == ThrottlingStatus.FULL_SPEED

    def test_throttling_status_detection_server_throttled(self):
        """Test throttling status detection when server is throttling (429s, API issues)."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Record some client waits and server throttle
        manager.record_client_wait_time(1.0)
        manager.record_server_throttle()

        stats = manager.get_stats()
        # Server throttling takes priority
        assert stats.throttling_status == ThrottlingStatus.SERVER_THROTTLED

    def test_throttling_window_cleanup(self):
        """Test that old throttling events are cleaned up."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Override detection window for testing
        manager.throttling_detection_window = 0.1  # 100ms

        # Record events
        manager.record_client_wait_time(1.0)
        manager.record_server_throttle()

        # Wait longer than window
        time.sleep(0.15)

        # Get stats (triggers cleanup)
        stats = manager.get_stats()

        # Events should be cleaned up
        assert len(manager.recent_wait_events) == 0
        assert len(manager.recent_server_throttles) == 0
        assert stats.throttling_status == ThrottlingStatus.FULL_SPEED

    def test_voyage_ai_throttling_callback_setup(self):
        """Test that VoyageAI throttling callback is set up correctly."""
        mock_voyage_client = Mock(spec=VoyageAIClient)
        mock_voyage_client.set_throttling_callback = Mock()

        manager = VectorCalculationManager(mock_voyage_client, thread_count=2)

        # Verify callback was set
        mock_voyage_client.set_throttling_callback.assert_called_once()

        # Get the callback function that was passed
        callback = mock_voyage_client.set_throttling_callback.call_args[0][0]

        # Test callback with client wait
        callback("client_wait", 2.5)
        stats = manager.get_stats()
        assert stats.client_wait_time == 2.5

        # Test callback with server throttle
        callback("server_throttle", None)
        stats = manager.get_stats()
        assert stats.server_throttle_count == 1

    def test_non_voyage_provider_no_callback(self):
        """Test that non-VoyageAI providers don't get throttling callback."""
        mock_provider = Mock()
        # Remove set_throttling_callback method to simulate other providers
        if hasattr(mock_provider, "set_throttling_callback"):
            delattr(mock_provider, "set_throttling_callback")

        # Should not raise an error
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Should work normally
        stats = manager.get_stats()
        assert stats.throttling_status == ThrottlingStatus.FULL_SPEED


if __name__ == "__main__":
    pytest.main([__file__])
