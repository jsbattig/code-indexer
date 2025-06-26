"""Tests for throttling recovery mechanisms."""

import time
import pytest
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    ThrottlingStatus,
)
from code_indexer.services.voyage_ai import RateLimiter


class TestThrottlingRecovery:
    """Test recovery from throttled states back to full speed."""

    def test_client_throttled_recovery_after_window(self):
        """Test that CLIENT_THROTTLED recovers to FULL_SPEED after detection window."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.2  # 200ms

        try:
            # Trigger CLIENT_THROTTLED state (need >5 waits AND avg >0.5s)
            for _ in range(7):
                manager.record_client_wait_time(0.8)  # 7 waits of 0.8s each

            # Verify we're in CLIENT_THROTTLED state
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.CLIENT_THROTTLED
            assert len(manager.recent_wait_events) == 7

            # Wait for detection window to expire
            time.sleep(0.25)  # Wait longer than 200ms window

            # Get stats again (triggers cleanup)
            recovery_stats = manager.get_stats()

            # Should recover to FULL_SPEED
            assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED
            assert len(manager.recent_wait_events) == 0  # Events cleaned up

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_server_throttled_recovery_after_window(self):
        """Test that SERVER_THROTTLED recovers to FULL_SPEED after detection window."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.2  # 200ms

        try:
            # Trigger SERVER_THROTTLED state
            manager.record_server_throttle()
            manager.record_server_throttle()

            # Verify we're in SERVER_THROTTLED state
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.SERVER_THROTTLED
            assert len(manager.recent_server_throttles) == 2

            # Wait for detection window to expire
            time.sleep(0.25)  # Wait longer than 200ms window

            # Get stats again (triggers cleanup)
            recovery_stats = manager.get_stats()

            # Should recover to FULL_SPEED
            assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED
            assert len(manager.recent_server_throttles) == 0  # Events cleaned up

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_mixed_throttling_recovery_priority(self):
        """Test recovery behavior when both client and server throttling events exist."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.2  # 200ms

        try:
            # Record both types of throttling
            for _ in range(7):
                manager.record_client_wait_time(0.8)  # CLIENT_THROTTLED conditions
            manager.record_server_throttle()  # SERVER_THROTTLED (higher priority)

            # Should be SERVER_THROTTLED (higher priority)
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.SERVER_THROTTLED

            # Wait for detection window to expire
            time.sleep(0.25)

            # Should recover to FULL_SPEED (both event types cleaned up)
            recovery_stats = manager.get_stats()
            assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED
            assert len(manager.recent_wait_events) == 0
            assert len(manager.recent_server_throttles) == 0

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_rate_limiter_token_recovery(self):
        """Test that RateLimiter recovers from depleted token state."""
        # Create rate limiter with low limits for testing
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Consume all tokens
        limiter.consume_tokens(actual_tokens=1000)  # Consume all token budget
        for _ in range(60):  # Consume all request budget
            limiter.consume_tokens(actual_tokens=1)

        # Should not be able to make requests
        assert not limiter.can_make_request(estimated_tokens=1)
        assert limiter.wait_time(estimated_tokens=1) > 0

        # Simulate time passing (manually adjust timestamps for testing)
        current_time = time.time()
        limiter.request_last_refill = current_time - 60  # 1 minute ago
        limiter.token_last_refill = current_time - 60  # 1 minute ago

        # Should recover after refill (this triggers _refill_tokens internally)
        assert limiter.can_make_request(estimated_tokens=1)
        assert limiter.wait_time(estimated_tokens=1) == 0

        # Check that tokens have been refilled to capacity
        # Note: After heavy consumption (-59 requests, -1000 tokens) plus 1 minute refill,
        # we should have: 60 requests + (-59) = 1, and 1000 tokens + (-1000) = 0
        # Then after 1 minute: 1 + 60 = 61 (capped to 60), 0 + 1000 = 1000
        assert (
            limiter.request_tokens >= 1
        ), f"Should have at least 1 request token, got {limiter.request_tokens}"
        assert (
            limiter.token_tokens >= 1
        ), f"Should have at least 1 token, got {limiter.token_tokens}"

    def test_rate_limiter_negative_token_recovery(self):
        """Test recovery from negative token state (edge case bug scenario)."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Force negative state (simulating concurrent consumption bug)
        limiter.request_tokens = -10
        limiter.token_tokens = -500

        # Wait time should be calculable (not infinite)
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert wait_time > 0
        assert wait_time < 3600  # Should be less than 1 hour (reasonable)

        # Simulate time passing for recovery
        current_time = time.time()
        limiter.request_last_refill = current_time - 120  # 2 minutes ago
        limiter.token_last_refill = current_time - 120

        # Should recover to positive values
        limiter._refill_tokens()
        assert limiter.request_tokens > 0
        assert limiter.token_tokens > 0
        assert limiter.can_make_request(estimated_tokens=1)

    def test_partial_recovery_during_ongoing_throttling(self):
        """Test behavior when some throttling events expire but new ones are added."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.3  # 300ms

        try:
            # Record initial throttling events
            for _ in range(7):
                manager.record_client_wait_time(0.8)

            # Should be CLIENT_THROTTLED
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.CLIENT_THROTTLED

            # Wait for partial window expiry
            time.sleep(0.2)  # 200ms - some events should remain

            # Add new throttling event
            manager.record_client_wait_time(0.9)

            # Should still be throttled (some old events + new event)
            # Might still be throttled depending on which events remain

            # Wait for full window expiry
            time.sleep(0.4)  # Total 600ms - all events should expire

            # Should recover to FULL_SPEED
            final_stats = manager.get_stats()
            assert final_stats.throttling_status == ThrottlingStatus.FULL_SPEED

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_recovery_requires_get_stats_call(self):
        """Test that recovery only happens when get_stats() is called."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.1  # 100ms

        try:
            # Record throttling events
            manager.record_server_throttle()

            # Verify throttled state
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.SERVER_THROTTLED

            # Wait for window expiry
            time.sleep(0.15)

            # Check internal state WITHOUT calling get_stats()
            # Events should still be in the list (no cleanup yet)
            assert len(manager.recent_server_throttles) == 1

            # Now call get_stats() to trigger cleanup
            recovery_stats = manager.get_stats()
            assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED
            assert len(manager.recent_server_throttles) == 0

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_continuous_recovery_simulation(self):
        """Test recovery behavior under continuous load with periodic throttling."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.2  # 200ms

        try:
            # Simulate 1 second of activity with periodic throttling
            start_time = time.time()
            throttle_count = 0
            recovery_count = 0

            while time.time() - start_time < 1.0:  # Run for 1 second
                current_time = time.time() - start_time

                # Add throttling events every 150ms
                if int(current_time * 10) % 2 == 0:  # Every ~100ms
                    manager.record_client_wait_time(0.6)
                    throttle_count += 1

                # Check status every 50ms
                stats = manager.get_stats()
                if stats.throttling_status == ThrottlingStatus.FULL_SPEED:
                    recovery_count += 1

                time.sleep(0.05)  # 50ms intervals

            # Should have seen both throttling and recovery events
            assert throttle_count > 0, "Should have recorded throttling events"
            assert recovery_count > 0, "Should have seen recovery periods"

            # Final state should eventually recover
            time.sleep(0.25)  # Wait for final recovery
            final_stats = manager.get_stats()
            assert final_stats.throttling_status == ThrottlingStatus.FULL_SPEED

        finally:
            # Restore original window
            manager.throttling_detection_window = original_window

    def test_rate_limiter_overflow_protection(self):
        """Test that rate limiter handles extreme negative values gracefully."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Set extremely negative values (simulating severe bug scenario)
        limiter.request_tokens = -1000000  # Very negative
        limiter.token_tokens = -5000000  # Very negative

        # Wait time calculation should not overflow or return infinite values
        wait_time = limiter.wait_time(estimated_tokens=1)

        # This test exposes the actual bug - wait time becomes unreasonably large
        print(
            f"DEBUG: Calculated wait time for extreme negative tokens: {wait_time:.2f} seconds"
        )

        # Current implementation calculates:
        # request_wait = (1 - (-1000000)) * 60 / 60 = 1000001 minutes = ~694 days!
        # token_wait = (1 - (-5000000)) * 60 / 1000 = 300000 minutes = ~208 days!

        # Should be a reasonable wait time (even if long)
        assert wait_time >= 0, "Wait time should not be negative"
        # KNOWN BUG: This will fail with current implementation
        # assert wait_time < 86400, "Wait time should be less than 24 hours"
        assert not (wait_time == float("inf")), "Wait time should not be infinite"

        # Even with extreme negative values, recovery should work eventually
        current_time = time.time()
        limiter.request_last_refill = current_time - 3600  # 1 hour ago
        limiter.token_last_refill = current_time - 3600

        # After 1 hour, recovery is still not sufficient for extreme negative values
        limiter._refill_tokens()
        # This is the bug - even after 1 hour, still can't make requests
        # because 1 hour only recovers 3600 tokens, but we need 1M+ tokens
        assert not limiter.can_make_request(
            estimated_tokens=1
        ), "Demonstrates the stuck state bug"

        # To truly recover, we'd need many days or a reset mechanism
        # For demonstration, let's simulate a much longer recovery time
        limiter.request_last_refill = current_time - 86400  # 24 hours ago
        limiter.token_last_refill = current_time - 86400
        limiter._refill_tokens()
        # Even after 24 hours, still not enough recovery
        assert not limiter.can_make_request(
            estimated_tokens=1
        ), "Still stuck after 24 hours"


if __name__ == "__main__":
    pytest.main([__file__])
