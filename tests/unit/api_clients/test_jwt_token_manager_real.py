"""Real JWT Token Manager Test Suite - Foundation #1 Compliant.

Tests JWT token manager using real tokens and real timing behavior.
Enhanced real-world testing beyond the base JWT token manager tests.
No mocks - real implementations only following MESSI Rule #1.
"""

import pytest
import time
from datetime import datetime, timedelta, timezone

from code_indexer.api_clients.jwt_token_manager import (
    JWTTokenManager,
)


class TestRealJWTTokenManagerNetworkIntegration:
    """Real JWT token manager tests with network integration."""

    @pytest.fixture
    def real_jwt_manager(self):
        """Create JWT token manager for real testing."""
        return JWTTokenManager(refresh_threshold_minutes=1)

    @pytest.fixture
    def test_server_token(self):
        """Get a real token from test server if available."""
        # This would normally come from a real authentication endpoint
        # For testing, we create a real token with proper structure
        import jwt as jose_jwt

        secret = "real_test_secret_for_integration"
        payload = {
            "username": "integration_test_user",
            "user_id": "test_user_12345",
            "permissions": ["read", "query"],
            "server_id": "cidx_server_test",
            "exp": (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
            "nbf": datetime.now(timezone.utc).timestamp(),
        }

        return jose_jwt.encode(payload, secret, algorithm="HS256")

    def test_real_token_lifecycle_validation(self, real_jwt_manager, test_server_token):
        """Test complete real token lifecycle validation."""
        # Decode real token structure
        decoded = real_jwt_manager.decode_token(test_server_token)

        # Verify real token has expected claims
        assert "username" in decoded
        assert "user_id" in decoded
        assert "permissions" in decoded
        assert "exp" in decoded
        assert "iat" in decoded

        # Verify token is not expired
        assert not real_jwt_manager.is_token_expired(test_server_token)

        # Verify token is not near expiry initially (5 min > 1 min threshold)
        assert not real_jwt_manager.is_token_near_expiry(test_server_token)

    def test_real_token_expiration_progression(self, real_jwt_manager):
        """Test real token expiration over time progression."""
        import jwt as jose_jwt

        secret = "real_timing_test_secret"

        # Create token that expires in 2 seconds for real timing test
        near_future = datetime.now(timezone.utc) + timedelta(seconds=2)
        payload = {
            "username": "timing_test_user",
            "exp": near_future.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        short_lived_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Initially should not be expired
        assert not real_jwt_manager.is_token_expired(short_lived_token)

        # Wait for real expiration (3 seconds to ensure it's past expiry)
        time.sleep(3)

        # Now should be expired (real time progression)
        assert real_jwt_manager.is_token_expired(short_lived_token)

    def test_real_token_near_expiry_timing(self, real_jwt_manager):
        """Test real near-expiry detection with actual timing."""
        import jwt as jose_jwt

        secret = "real_near_expiry_test_secret"

        # Create token that expires in 30 seconds (well within 1 minute threshold)
        near_expiry_time = datetime.now(timezone.utc) + timedelta(seconds=30)
        payload = {
            "username": "near_expiry_test_user",
            "exp": near_expiry_time.timestamp(),
            "iat": datetime.now(timezone.utc).timestamp(),
        }

        near_expiry_token = jose_jwt.encode(payload, secret, algorithm="HS256")

        # Should detect as near expiry (30 seconds < 1 minute threshold)
        assert real_jwt_manager.is_token_near_expiry(near_expiry_token)

        # Should not be expired yet
        assert not real_jwt_manager.is_token_expired(near_expiry_token)

    def test_real_concurrent_token_validation(
        self, real_jwt_manager, test_server_token
    ):
        """Test real concurrent token validation operations."""
        import threading
        import queue

        results = queue.Queue()
        errors = queue.Queue()

        def validate_token_worker():
            """Worker function for concurrent token validation."""
            try:
                for _ in range(10):
                    # Real concurrent operations
                    decoded = real_jwt_manager.decode_token(test_server_token)
                    is_expired = real_jwt_manager.is_token_expired(test_server_token)
                    is_near_expiry = real_jwt_manager.is_token_near_expiry(
                        test_server_token
                    )

                    results.put((decoded["username"], is_expired, is_near_expiry))
                    time.sleep(0.01)  # Small delay for real concurrency

            except Exception as e:
                errors.put(e)

        # Start multiple threads for real concurrent testing
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=validate_token_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors occurred in real concurrent operations
        assert errors.empty(), f"Concurrent validation errors: {list(errors.queue)}"

        # Verify all results are consistent
        all_results = list(results.queue)
        assert len(all_results) == 50  # 5 threads * 10 operations each

        # All usernames should be the same
        usernames = [result[0] for result in all_results]
        assert all(username == usernames[0] for username in usernames)
