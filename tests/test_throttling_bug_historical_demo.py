"""Historical demonstration of the throttling bug (NOW FIXED).

These tests demonstrate what the behavior USED TO BE before the fix.
They are kept for historical reference and will fail with the current fixed implementation.
This is expected and correct - the fix prevents these scenarios.

DO NOT RUN THESE TESTS - they are for documentation only.
"""

import time
import pytest
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
    ThrottlingStatus,
)
from code_indexer.services.voyage_ai import RateLimiter


class TestThrottlingBugReproduction:
    """Reproduce the exact bug scenario where throttling gets stuck."""

    @pytest.mark.skip(reason="Historical demo of fixed bug - kept for reference only")
    def test_bug_reproduction_extreme_negative_tokens(self):
        """Reproduce the bug: extreme negative tokens cause unreasonable wait times."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Simulate the bug scenario: concurrent consumption drives tokens very negative
        limiter.request_tokens = -1000000  # Extremely negative due to race condition
        limiter.token_tokens = -5000000  # Extremely negative due to race condition

        # Calculate wait time - this is where the bug manifests
        wait_time = limiter.wait_time(estimated_tokens=1)

        print(
            f"DEBUG: Wait time for -1M request tokens, -5M token budget: {wait_time:.0f} seconds"
        )
        print(f"DEBUG: That's {wait_time/3600:.1f} hours or {wait_time/86400:.1f} days")

        # The bug: wait time becomes ~1,000,001 seconds (~11.5 days)
        # This is calculated as: (1 - (-1000000)) * 60 / 60 = 1,000,001 seconds
        assert (
            abs(wait_time - 1000001.0) < 1.0
        ), f"Expected ~1000001 seconds, got {wait_time}"

        # Even after a full hour of refill, it's still not enough
        current_time = time.time()
        limiter.request_last_refill = current_time - 3600  # 1 hour ago
        limiter.token_last_refill = current_time - 3600

        # Try to recover
        limiter._refill_tokens()
        print(
            f"DEBUG: After 1 hour refill - request_tokens: {limiter.request_tokens:.0f}"
        )
        print(f"DEBUG: After 1 hour refill - token_tokens: {limiter.token_tokens:.0f}")

        # Still can't make requests because tokens are still massively negative
        can_make_request = limiter.can_make_request(estimated_tokens=1)
        wait_time_after_hour = limiter.wait_time(estimated_tokens=1)

        print(f"DEBUG: Can make request after 1 hour? {can_make_request}")
        print(f"DEBUG: Wait time after 1 hour: {wait_time_after_hour:.0f} seconds")

        # The bug: even after 1 hour, still can't make requests
        assert not can_make_request, "Should still be blocked after only 1 hour"
        assert wait_time_after_hour > 0, "Should still have significant wait time"

    @pytest.mark.skip(reason="Historical demo of fixed bug - kept for reference only")
    def test_bug_reproduction_how_tokens_go_negative(self):
        """Demonstrate how tokens can go negative in concurrent scenarios."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        print(f"DEBUG: Initial state - request_tokens: {limiter.request_tokens}")
        print(f"DEBUG: Initial state - token_tokens: {limiter.token_tokens}")

        # Simulate multiple threads consuming tokens without proper synchronization
        # Each thread thinks there are tokens available and consumes them
        for i in range(100):  # 100 "concurrent" consumers
            # Each thinks tokens are available (race condition)
            if limiter.request_tokens >= 0.1:  # Thinks there are tokens
                limiter.consume_tokens(actual_tokens=50)  # But consumes anyway
                print(
                    f"DEBUG: After consumption {i+1} - request_tokens: {limiter.request_tokens:.1f}, token_tokens: {limiter.token_tokens:.0f}"
                )
                if limiter.request_tokens < -10:  # Stop when it gets really bad
                    break

        # Now we have negative tokens due to race conditions
        assert limiter.request_tokens < 0, "Should have negative request tokens"
        assert limiter.token_tokens < 0, "Should have negative token budget"

        # This leads to the stuck throttling state
        wait_time = limiter.wait_time(estimated_tokens=1)
        print(f"DEBUG: Wait time with negative tokens: {wait_time:.1f} seconds")
        assert wait_time > 1000, "Should have very long wait time"

    @pytest.mark.skip(reason="Historical demo of fixed bug - kept for reference only")
    def test_bug_reproduction_vector_manager_gets_stuck(self):
        """Demonstrate how VectorCalculationManager gets stuck in CLIENT_THROTTLED."""
        mock_provider = Mock()

        # Create a VectorCalculationManager with a mocked VoyageAI provider
        manager = VectorCalculationManager(mock_provider, thread_count=8)

        # Simulate the VoyageAI client getting into the bug state
        # This would happen if the rate limiter has extreme negative tokens

        # Force multiple large wait events (simulating the bug scenario)
        for _ in range(10):
            # Record very large wait times (simulating the 1M+ second waits)
            manager.record_client_wait_time(1000000.0)  # ~11.5 days wait

        # Check status - should be CLIENT_THROTTLED
        stats = manager.get_stats()
        print(f"DEBUG: Throttling status: {stats.throttling_status}")
        print(f"DEBUG: Recent wait events: {len(manager.recent_wait_events)}")
        print(
            f"DEBUG: Average wait time: {sum(w for _, w in manager.recent_wait_events) / len(manager.recent_wait_events):.0f}s"
        )

        assert stats.throttling_status == ThrottlingStatus.CLIENT_THROTTLED

        # The problem: even after the detection window expires, if the underlying
        # rate limiter is still in a broken state, new wait events keep getting recorded

        # Simulate time passing beyond detection window
        time.sleep(0.1)  # In real scenario, this would be 10+ seconds

        # If the rate limiter is still broken, it will keep generating wait events
        # and the system never recovers to FULL_SPEED

        # Clear old events manually to simulate window expiry
        manager.recent_wait_events.clear()

        # Now it should recover
        recovery_stats = manager.get_stats()
        assert recovery_stats.throttling_status == ThrottlingStatus.FULL_SPEED

    @pytest.mark.skip(reason="Historical demo of fixed bug - kept for reference only")
    def test_rate_limiter_needs_bounds_checking(self):
        """Demonstrate the need for bounds checking in the rate limiter."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # The fix would be to add bounds checking to prevent extreme negative values
        # For example, tokens should never go below -max_capacity

        # Simulate the scenario that should be prevented
        original_request_tokens = limiter.request_tokens
        original_token_tokens = limiter.token_tokens

        # Consume way more than available (this should be bounded)
        limiter.consume_tokens(actual_tokens=10000)  # Consume 10x the capacity
        for _ in range(100):  # Consume 100 requests when only 60 available
            limiter.consume_tokens(actual_tokens=1)

        print(f"DEBUG: Original request tokens: {original_request_tokens}")
        print(f"DEBUG: After overconsumption request tokens: {limiter.request_tokens}")
        print(f"DEBUG: Original token budget: {original_token_tokens}")
        print(f"DEBUG: After overconsumption token budget: {limiter.token_tokens}")

        # Current implementation allows unlimited negative values
        assert limiter.request_tokens < -50, "Demonstrates unlimited negative tokens"
        assert (
            limiter.token_tokens < -5000
        ), "Demonstrates unlimited negative token budget"

        # A proper fix would bound these values, for example:
        # request_tokens should never go below -requests_per_minute
        # token_tokens should never go below -tokens_per_minute

        # This would prevent the extreme wait times that cause the stuck state
        expected_min_request_tokens = -limiter.requests_per_minute
        expected_min_token_tokens = (
            -limiter.tokens_per_minute if limiter.tokens_per_minute else 0
        )

        print(
            f"DEBUG: Suggested bounds - min request tokens: {expected_min_request_tokens}"
        )
        print(
            f"DEBUG: Suggested bounds - min token budget: {expected_min_token_tokens}"
        )

        # The fix would ensure recovery time is always reasonable
        # Max wait time would be: (1 - (-60)) * 60 / 60 = 61 seconds for requests
        # Max wait time would be: (1 - (-1000)) * 60 / 1000 = 60.06 seconds for tokens
        # So maximum wait time would be ~61 seconds, which is reasonable

    @pytest.mark.skip(
        reason="Real fix validation is in test_throttling_fix_validation.py"
    )
    def test_proposed_fix_validation(self):
        """Test what the behavior IS NOW with the implemented fix (this should pass)."""
        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=1000)

        # Manually implement the proposed bounds checking
        def consume_tokens_with_bounds(actual_tokens: int = 1):
            """Proposed fix: bound token consumption to prevent extreme negatives."""
            limiter.request_tokens -= 1
            if limiter.token_tokens is not None:
                limiter.token_tokens -= actual_tokens

            # PROPOSED FIX: Apply bounds to prevent extreme negative values
            min_request_tokens = -limiter.requests_per_minute  # -60
            min_token_tokens = (
                -limiter.tokens_per_minute if limiter.tokens_per_minute else 0
            )  # -1000

            limiter.request_tokens = max(limiter.request_tokens, min_request_tokens)
            if limiter.token_tokens is not None:
                limiter.token_tokens = max(limiter.token_tokens, min_token_tokens)

        # Test the bounded consumption
        for _ in range(200):  # Try to consume way more than available
            consume_tokens_with_bounds(100)

        print(f"DEBUG: With bounds - request_tokens: {limiter.request_tokens}")
        print(f"DEBUG: With bounds - token_tokens: {limiter.token_tokens}")

        # Should be bounded to reasonable negative values
        assert (
            limiter.request_tokens >= -60
        ), "Should be bounded to -requests_per_minute"
        assert limiter.token_tokens >= -1000, "Should be bounded to -tokens_per_minute"

        # Wait time should be reasonable
        wait_time = limiter.wait_time(estimated_tokens=1)
        print(f"DEBUG: With bounds - wait time: {wait_time:.1f} seconds")

        # Should be at most ~61 seconds (reasonable recovery time)
        assert wait_time <= 70, f"Wait time should be reasonable, got {wait_time:.1f}s"

        # Recovery should happen quickly
        current_time = time.time()
        limiter.request_last_refill = current_time - 120  # 2 minutes ago
        limiter.token_last_refill = current_time - 120

        limiter._refill_tokens()
        assert limiter.can_make_request(
            estimated_tokens=1
        ), "Should recover quickly with bounds"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
