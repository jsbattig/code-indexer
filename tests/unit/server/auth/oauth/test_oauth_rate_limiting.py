"""
Test OAuth rate limiting functionality.

Following TDD: Write failing tests FIRST, then implement features.
Following CLAUDE.md: Zero mocking - real rate limiting, real state management.
"""

from code_indexer.server.auth.oauth_rate_limiter import (
    OAuthTokenRateLimiter,
    OAuthRegisterRateLimiter,
    oauth_token_rate_limiter,
    oauth_register_rate_limiter,
)


class TestOAuthRateLimiting:
    """Test OAuth rate limiting for token and register endpoints."""

    def test_oauth_token_rate_limiter_allows_initial_requests(self):
        """Test that token rate limiter allows requests under limit."""
        limiter = OAuthTokenRateLimiter()
        client_id = "test_client"
        result = limiter.check_rate_limit(client_id)
        assert result is None

    def test_oauth_token_rate_limiter_blocks_after_max_attempts(self):
        """Test that token rate limiter blocks after 10 failed attempts."""
        limiter = OAuthTokenRateLimiter()
        client_id = "test_client_fail"

        for i in range(10):
            is_locked = limiter.record_failed_attempt(client_id)
            if i < 9:
                assert is_locked is False
            else:
                assert is_locked is True

        result = limiter.check_rate_limit(client_id)
        assert result is not None
        assert "Try again in" in result

    def test_oauth_token_rate_limiter_lockout_duration_5_minutes(self):
        """Test that token rate limiter has 5 minute lockout."""
        limiter = OAuthTokenRateLimiter()
        client_id = "test_lockout_duration"

        for _ in range(10):
            limiter.record_failed_attempt(client_id)

        result = limiter.check_rate_limit(client_id)
        assert result is not None
        assert "5 minutes" in result or "4 minutes" in result

    def test_oauth_register_rate_limiter_blocks_after_5_attempts(self):
        """Test that register rate limiter blocks after 5 failed attempts."""
        limiter = OAuthRegisterRateLimiter()
        ip_address = "192.168.1.101"

        for i in range(5):
            is_locked = limiter.record_failed_attempt(ip_address)
            if i < 4:
                assert is_locked is False
            else:
                assert is_locked is True

        result = limiter.check_rate_limit(ip_address)
        assert result is not None
        assert "Try again in" in result

    def test_oauth_register_rate_limiter_lockout_duration_15_minutes(self):
        """Test that register rate limiter has 15 minute lockout."""
        limiter = OAuthRegisterRateLimiter()
        ip_address = "192.168.1.102"

        for _ in range(5):
            limiter.record_failed_attempt(ip_address)

        result = limiter.check_rate_limit(ip_address)
        assert result is not None
        assert "15 minutes" in result or "14 minutes" in result

    def test_successful_attempt_clears_rate_limit(self):
        """Test that successful attempt clears rate limiting state."""
        limiter = OAuthTokenRateLimiter()
        client_id = "test_clear"

        for _ in range(3):
            limiter.record_failed_attempt(client_id)

        limiter.record_successful_attempt(client_id)
        result = limiter.check_rate_limit(client_id)
        assert result is None

    def test_global_instances_exist(self):
        """Test that global rate limiter instances are available."""
        assert oauth_token_rate_limiter is not None
        assert oauth_register_rate_limiter is not None
        assert oauth_token_rate_limiter != oauth_register_rate_limiter
