"""Tests to validate the throttling fix prevents stuck states."""

import time
import pytest
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    ThrottlingStatus,
)
from code_indexer.services.voyage_ai import RateLimiter


class TestThrottlingFixValidation:
    """Validate that the throttling fix prevents stuck states."""

    def test_bounds_checking_prevents_extreme_negative_tokens(self):
        """Test that bounds checking prevents extreme negative token values."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Try to consume way more tokens than available (should be bounded)
        for _ in range(200):  # Try to consume 200 requests (only 60 available)
            limiter.consume_tokens(actual_tokens=100)  # Try to consume 100 tokens each

        # Should be bounded to reasonable negative values
        assert (
            limiter.request_tokens >= -60
        ), f"Request tokens should be bounded to -60, got {limiter.request_tokens}"
        assert (
            limiter.token_tokens >= -1000
        ), f"Token budget should be bounded to -1000, got {limiter.token_tokens}"

        # Wait time should be reasonable (not days)
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert (
            wait_time <= 120.0
        ), f"Wait time should be capped at 2 minutes, got {wait_time:.1f}s"

    def test_overflow_protection_caps_wait_times(self):
        """Test that overflow protection caps wait times to reasonable values."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Force extreme negative values (bypassing bounds for testing overflow protection)
        limiter.request_tokens = -1000000  # Extreme negative
        limiter.token_tokens = -5000000  # Extreme negative

        # Wait time should be capped by overflow protection
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert (
            wait_time <= 120.0
        ), f"Overflow protection should cap wait time to 2 minutes, got {wait_time:.1f}s"

    def test_fix_enables_fast_recovery(self):
        """Test that the fix enables fast recovery from bounded negative states."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Consume many tokens (should be bounded)
        for _ in range(100):
            limiter.consume_tokens(actual_tokens=50)

        # Should be in bounded negative state
        print(f"DEBUG: Final request_tokens: {limiter.request_tokens}")
        print(f"DEBUG: Final token_tokens: {limiter.token_tokens}")
        assert limiter.request_tokens >= -60  # Should be bounded to at least -60
        assert limiter.token_tokens >= -1000  # Should be bounded to at least -1000

        # Should not be able to make requests initially
        assert not limiter.can_make_request(estimated_tokens=1)

        # Simulate 2 minutes passing (should be enough for recovery)
        current_time = time.time()
        limiter.request_last_refill = current_time - 120  # 2 minutes ago
        limiter.token_last_refill = current_time - 120

        # Should recover completely
        assert limiter.can_make_request(estimated_tokens=1)
        assert limiter.wait_time(estimated_tokens=1) == 0.0

    def test_concurrent_consumption_simulation_with_fix(self):
        """Test that concurrent consumption with fix doesn't cause stuck states."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Simulate many concurrent consumers (race condition scenario)
        for i in range(1000):  # Much more than available
            # Each "thread" tries to consume tokens
            limiter.consume_tokens(actual_tokens=10)

            # Even under extreme concurrent load, tokens should be bounded
            assert (
                limiter.request_tokens >= -60
            ), f"Request tokens went below bound at iteration {i}"
            assert (
                limiter.token_tokens >= -1000
            ), f"Token budget went below bound at iteration {i}"

        # Wait time should always be reasonable
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert (
            wait_time <= 120.0
        ), f"Wait time should be reasonable, got {wait_time:.1f}s"

    def test_vector_manager_recovery_with_fixed_rate_limiter(self):
        """Test that VectorCalculationManager recovers properly with fixed rate limiter."""
        # Create a mock VoyageAI provider with the fixed rate limiter
        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "voyage-ai"

        # Create VectorCalculationManager
        manager = VectorCalculationManager(mock_provider, thread_count=8)

        # Set short detection window for testing
        original_window = manager.throttling_detection_window
        manager.throttling_detection_window = 0.2  # 200ms

        try:
            # Simulate the fixed behavior - even with many wait events, they should be reasonable
            for _ in range(10):
                # With the fix, wait times are capped at 2 minutes instead of days
                manager.record_client_wait_time(120.0)  # 2 minutes (maximum with fix)

            # Should be CLIENT_THROTTLED but with reasonable wait times
            stats = manager.get_stats()
            assert stats.throttling_status == ThrottlingStatus.CLIENT_THROTTLED

            # Wait for detection window to expire
            time.sleep(0.25)

            # Should recover to FULL_SPEED
            recovery_stats = manager.get_stats()
            assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED
            assert len(manager.recent_wait_events) == 0

        finally:
            manager.throttling_detection_window = original_window

    def test_backwards_compatibility(self):
        """Test that the fix doesn't break normal operation."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Normal usage should work exactly as before
        assert limiter.can_make_request(estimated_tokens=1)
        assert limiter.wait_time(estimated_tokens=1) == 0.0

        # Consume some tokens normally
        limiter.consume_tokens(actual_tokens=10)

        # Should still be able to make requests
        assert limiter.can_make_request(estimated_tokens=1)

        # Consume tokens up to the limit
        for _ in range(59):  # Total 60 requests consumed
            limiter.consume_tokens(actual_tokens=1)

        # Should now need to wait, but for a reasonable time
        assert not limiter.can_make_request(estimated_tokens=1)
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert 0 < wait_time <= 120.0  # Should be reasonable wait time

    def test_extreme_scenario_recovery(self):
        """Test recovery in the most extreme scenario that previously caused stuck states."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Force the most extreme consumption scenario
        for _ in range(10000):  # Massive overconsumption attempt
            limiter.consume_tokens(actual_tokens=1000)

        # Should be bounded to minimum values
        assert limiter.request_tokens == -60
        assert limiter.token_tokens == -1000

        # Wait time should be capped
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert wait_time <= 120.0, f"Wait time should be capped, got {wait_time:.1f}s"

        # Recovery should happen within reasonable time
        current_time = time.time()
        limiter.request_last_refill = current_time - 180  # 3 minutes ago
        limiter.token_last_refill = current_time - 180

        # Should fully recover
        limiter._refill_tokens()
        assert limiter.can_make_request(estimated_tokens=1)
        assert limiter.wait_time(estimated_tokens=1) == 0.0

        # Tokens should be at capacity
        assert limiter.request_tokens == 60
        assert limiter.token_tokens == 1000

    def test_edge_case_single_token_per_minute(self):
        """Test fix works with very low rate limits."""
        # Test with very restrictive limits
        limiter = RateLimiter(requests_per_minute=1, tokens_per_minute=10)

        # Overconsume
        for _ in range(100):
            limiter.consume_tokens(actual_tokens=5)

        # Should be bounded appropriately
        assert limiter.request_tokens >= -1  # Minimum for 1 RPM
        assert limiter.token_tokens >= -10  # Minimum for 10 TPM

        # Wait time should be capped
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert wait_time <= 120.0

    def test_no_token_limit_scenario(self):
        """Test fix works when token limits are disabled."""
        # Test with no token limit (only request limit)
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=None)

        # Overconsume requests
        for _ in range(200):
            limiter.consume_tokens(
                actual_tokens=1000
            )  # Large token count should be ignored

        # Should be bounded for requests only
        assert limiter.request_tokens >= -60
        assert limiter.token_tokens == 0  # Should remain 0 when disabled

        # Wait time should be reasonable
        wait_time = limiter.wait_time(estimated_tokens=1)
        assert wait_time <= 120.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
