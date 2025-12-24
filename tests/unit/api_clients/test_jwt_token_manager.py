"""Test suite for JWT Token Manager used in API clients.

Tests JWT token validation, expiration detection, and refresh logic
following TDD principles with no mocks.
"""

import pytest
import time
from datetime import datetime, timedelta, timezone

from code_indexer.api_clients.jwt_token_manager import (
    JWTTokenManager,
    TokenValidationError,
)


class TestJWTTokenManagerValidation:
    """Test JWT token validation functionality."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT token manager for testing."""
        return JWTTokenManager(refresh_threshold_minutes=2)

    def test_valid_jwt_token_validation(self, jwt_manager):
        """Test validation of a properly formatted JWT token."""
        # Create a valid JWT token for testing
        import jwt as jose_jwt

        secret = "test_secret_key"
        payload = {
            "username": "testuser",
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        valid_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should validate successfully (we don't verify signature, just structure)
        result = jwt_manager.decode_token(valid_token)

        assert result["username"] == "testuser"
        assert "exp" in result
        assert "iat" in result

    def test_malformed_token_handling(self, jwt_manager):
        """Test handling of malformed JWT tokens."""
        malformed_tokens = [
            "not.a.jwt",
            "definitely_not_jwt",
            "too.few.parts",
            "way.too.many.parts.here.definitely",
            "",
            None,
        ]

        for token in malformed_tokens:
            with pytest.raises(TokenValidationError):
                jwt_manager.decode_token(token)

    def test_token_without_expiration(self, jwt_manager):
        """Test handling of JWT tokens without expiration claim."""
        import jwt as jose_jwt

        secret = "test_secret_key"
        payload = {
            "username": "testuser",
            "iat": datetime.now(timezone.utc).timestamp(),
            # Missing 'exp' claim
        }

        token_without_exp = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should handle gracefully but treat as suspicious
        result = jwt_manager.decode_token(token_without_exp)
        assert result["username"] == "testuser"
        assert "exp" not in result


class TestJWTTokenManagerExpiration:
    """Test JWT token expiration detection."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT token manager for testing."""
        return JWTTokenManager(refresh_threshold_minutes=2)

    def test_expired_token_detection(self, jwt_manager):
        """Test detection of expired JWT tokens."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Create token that expired 5 minutes ago
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "username": "testuser",
            "exp": expired_time.timestamp(),
            "iat": (expired_time - timedelta(minutes=10)).timestamp(),
        }

        expired_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should detect as expired
        assert jwt_manager.is_token_expired(expired_token) is True

    def test_valid_token_not_expired(self, jwt_manager):
        """Test that valid future tokens are not detected as expired."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Create token that expires in 10 minutes
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "username": "testuser",
            "exp": future_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        valid_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should not be detected as expired
        assert jwt_manager.is_token_expired(valid_token) is False

    def test_token_expiring_soon_detection(self, jwt_manager):
        """Test detection of tokens that are about to expire."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Create token that expires in 1 minute (less than refresh threshold of 2)
        soon_expire_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        payload = {
            "username": "testuser",
            "exp": soon_expire_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        soon_expire_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should detect as needing refresh
        assert jwt_manager.is_token_near_expiry(soon_expire_token) is True

    def test_token_not_expiring_soon(self, jwt_manager):
        """Test tokens that are not close to expiration."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Create token that expires in 10 minutes (well beyond refresh threshold)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "username": "testuser",
            "exp": future_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        valid_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should not need refresh
        assert jwt_manager.is_token_near_expiry(valid_token) is False

    def test_boundary_expiration_times(self, jwt_manager):
        """Test expiration detection at exact boundary conditions."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Test token that expires exactly at the refresh threshold (2 minutes)
        boundary_time = datetime.now(timezone.utc) + timedelta(minutes=2)
        payload = {
            "username": "testuser",
            "exp": boundary_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        boundary_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should be considered near expiry (at or below threshold)
        assert jwt_manager.is_token_near_expiry(boundary_token) is True


class TestJWTTokenManagerConfiguration:
    """Test JWT token manager configuration options."""

    def test_custom_refresh_threshold(self):
        """Test custom refresh threshold configuration."""
        custom_threshold = 5  # 5 minutes
        jwt_manager = JWTTokenManager(refresh_threshold_minutes=custom_threshold)

        assert jwt_manager.refresh_threshold_minutes == custom_threshold

    def test_zero_refresh_threshold(self):
        """Test zero refresh threshold (immediate refresh when expired)."""
        jwt_manager = JWTTokenManager(refresh_threshold_minutes=0)

        import jwt as jose_jwt

        secret = "test_secret_key"

        # Token expires in 1 minute
        future_time = datetime.now(timezone.utc) + timedelta(minutes=1)
        payload = {
            "username": "testuser",
            "exp": future_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # With zero threshold, should not need refresh until actually expired
        assert jwt_manager.is_token_near_expiry(token) is False

    def test_large_refresh_threshold(self):
        """Test large refresh threshold configuration."""
        large_threshold = 60  # 1 hour
        jwt_manager = JWTTokenManager(refresh_threshold_minutes=large_threshold)

        import jwt as jose_jwt

        secret = "test_secret_key"

        # Token expires in 30 minutes
        future_time = datetime.now(timezone.utc) + timedelta(minutes=30)
        payload = {
            "username": "testuser",
            "exp": future_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # With large threshold, even 30-minute token should need refresh
        assert jwt_manager.is_token_near_expiry(token) is True


class TestJWTTokenManagerPerformance:
    """Test JWT token manager performance characteristics."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT token manager for testing."""
        return JWTTokenManager(refresh_threshold_minutes=2)

    def test_token_parsing_performance(self, jwt_manager):
        """Test that token parsing is fast for valid tokens."""
        import jwt as jose_jwt

        secret = "test_secret_key"
        payload = {
            "username": "testuser",
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Multiple rapid calls should be fast
        start_time = time.time()

        for _ in range(100):
            jwt_manager.is_token_expired(token)
            jwt_manager.is_token_near_expiry(token)

        elapsed = time.time() - start_time

        # Should complete 200 operations in well under 1 second
        assert elapsed < 0.5

    def test_malformed_token_handling_performance(self, jwt_manager):
        """Test that malformed token handling doesn't cause performance issues."""
        malformed_token = "not.a.jwt.token"

        start_time = time.time()

        # Multiple rapid calls to malformed token should fail fast
        for _ in range(50):
            with pytest.raises(TokenValidationError):
                jwt_manager.decode_token(malformed_token)

        elapsed = time.time() - start_time

        # Should complete 50 error cases quickly
        assert elapsed < 0.2

    def test_repeated_token_operations_consistent(self, jwt_manager):
        """Test that repeated operations on same token give consistent results."""
        import jwt as jose_jwt

        secret = "test_secret_key"
        payload = {
            "username": "testuser",
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Multiple calls should return same results
        results_expired = [jwt_manager.is_token_expired(token) for _ in range(10)]
        results_near_expiry = [
            jwt_manager.is_token_near_expiry(token) for _ in range(10)
        ]

        # All results should be consistent
        assert all(result == results_expired[0] for result in results_expired)
        assert all(result == results_near_expiry[0] for result in results_near_expiry)


class TestJWTTokenManagerEdgeCases:
    """Test JWT token manager edge cases and error conditions."""

    @pytest.fixture
    def jwt_manager(self):
        """Create JWT token manager for testing."""
        return JWTTokenManager(refresh_threshold_minutes=2)

    def test_token_with_string_timestamps(self, jwt_manager):
        """Test handling of tokens with string timestamp values."""
        import jwt as jose_jwt

        secret = "test_secret_key"
        future_time = datetime.now(timezone.utc) + timedelta(minutes=10)
        payload = {
            "username": "testuser",
            "exp": str(future_time.timestamp()),  # String instead of number
            "iat": str(datetime.now(timezone.utc).timestamp()),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should handle string timestamps gracefully
        result = jwt_manager.decode_token(token)
        assert result["username"] == "testuser"

        # Should still detect expiration correctly
        assert jwt_manager.is_token_expired(token) is False

    def test_token_with_invalid_timestamp_format(self, jwt_manager):
        """Test handling of tokens with invalid timestamp formats."""
        import jwt as jose_jwt

        secret = "test_secret_key"
        payload = {
            "username": "testuser",
            "exp": "not-a-timestamp",
            "iat": "also-not-a-timestamp",
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should handle invalid timestamps without crashing
        with pytest.raises(TokenValidationError):
            jwt_manager.is_token_expired(token)

    def test_token_with_very_old_timestamps(self, jwt_manager):
        """Test handling of tokens with timestamps from long ago."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Very old timestamps (year 2000)
        old_time = datetime(2000, 1, 1, tzinfo=timezone.utc)
        payload = {
            "username": "testuser",
            "exp": old_time.timestamp(),
            "iat": (old_time - timedelta(hours=1)).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should correctly identify as expired
        assert jwt_manager.is_token_expired(token) is True

    def test_token_with_far_future_timestamps(self, jwt_manager):
        """Test handling of tokens with timestamps far in the future."""
        import jwt as jose_jwt

        secret = "test_secret_key"

        # Very future timestamps (year 2099)
        future_time = datetime(2099, 12, 31, tzinfo=timezone.utc)
        payload = {
            "username": "testuser",
            "exp": future_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should correctly identify as not expired
        assert jwt_manager.is_token_expired(token) is False
        assert jwt_manager.is_token_near_expiry(token) is False
