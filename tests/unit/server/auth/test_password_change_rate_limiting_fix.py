"""
TDD Tests for Password Change Rate Limiting Fix

Tests to reproduce the exact rate limiting issue where 401 is returned instead of 429
after multiple failed password attempts.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


class TestPasswordChangeRateLimitingFix:
    """Test suite to reproduce and fix rate limiting issues."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        return {"Authorization": "Bearer valid.jwt.token"}

    def test_rate_limiting_returns_429_after_multiple_failures(
        self, client, authenticated_user_headers
    ):
        """
        TDD TEST: Rate limiting should return 429 after recording multiple failed attempts.

        Current behavior: Returns 401 every time
        Expected behavior: Returns 429 after reaching rate limit threshold
        """
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_dep_user_mgr:
                with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
                    with patch(
                        "code_indexer.server.app.password_change_rate_limiter"
                    ) as mock_rate_limiter:
                        with patch(
                            "code_indexer.server.app.password_audit_logger"
                        ) as _mock_audit_logger:
                            # Mock JWT authentication
                            mock_jwt.validate_token.return_value = {
                                "username": "testuser",
                                "role": "normal_user",
                                "exp": 9999999999,
                                "iat": 1234567890,
                            }

                            # Create test user
                            test_user = User(
                                username="testuser",
                                password_hash="$2b$12$oldhash",
                                role=UserRole.NORMAL_USER,
                                created_at=datetime.now(timezone.utc),
                            )

                            # Mock user retrieval
                            mock_dep_user_mgr.get_user.return_value = test_user
                            mock_user_mgr.get_user.return_value = test_user

                            # Mock password verification to always fail
                            mock_user_mgr.password_manager.verify_password.return_value = (
                                False
                            )

                            # Configure rate limiter behavior
                            # First check should pass (no rate limit yet)
                            mock_rate_limiter.check_rate_limit.side_effect = [
                                None,  # 1st attempt - no rate limit
                                None,  # 2nd attempt - no rate limit
                                None,  # 3rd attempt - no rate limit
                                None,  # 4th attempt - no rate limit
                                None,  # 5th attempt - no rate limit
                                "Too many failed attempts. Please try again in 15 minutes.",  # 6th attempt - rate limited
                            ]

                            # record_failed_attempt should return True when lockout should occur
                            mock_rate_limiter.record_failed_attempt.side_effect = [
                                False,  # 1st through 4th attempts - no lockout
                                False,
                                False,
                                False,
                                True,  # 5th attempt - triggers lockout
                            ]

                            # Mock get_attempt_count for audit logging
                            mock_rate_limiter.get_attempt_count.return_value = 5

                            # Make failed attempts
                            for attempt in range(5):
                                response = client.put(
                                    "/api/users/change-password",
                                    headers=authenticated_user_headers,
                                    json={
                                        "old_password": f"wrong_password_{attempt}",
                                        "new_password": "NewSecure123!Pass",
                                    },
                                )
                                # First 4 attempts should get 401, 5th should trigger rate limit (429)
                                if attempt < 4:
                                    assert (
                                        response.status_code == 401
                                    ), f"Attempt {attempt + 1} should return 401"
                                else:
                                    assert (
                                        response.status_code == 429
                                    ), f"Attempt {attempt + 1} should return 429"
                                    assert (
                                        "Too many failed attempts"
                                        in response.json()["detail"]
                                    )

    def test_fifth_attempt_triggers_immediate_rate_limiting(
        self, client, authenticated_user_headers
    ):
        """
        TDD TEST: The 5th failed attempt should trigger rate limiting immediately.

        This tests the case where record_failed_attempt returns True,
        indicating that this attempt triggered the lockout.
        """
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_dep_user_mgr:
                with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
                    with patch(
                        "code_indexer.server.app.password_change_rate_limiter"
                    ) as mock_rate_limiter:
                        with patch(
                            "code_indexer.server.app.password_audit_logger"
                        ) as _mock_audit_logger:
                            # Mock JWT authentication
                            mock_jwt.validate_token.return_value = {
                                "username": "testuser",
                                "role": "normal_user",
                                "exp": 9999999999,
                                "iat": 1234567890,
                            }

                            # Create test user
                            test_user = User(
                                username="testuser",
                                password_hash="$2b$12$oldhash",
                                role=UserRole.NORMAL_USER,
                                created_at=datetime.now(timezone.utc),
                            )

                            # Mock user retrieval
                            mock_dep_user_mgr.get_user.return_value = test_user
                            mock_user_mgr.get_user.return_value = test_user

                            # Mock password verification to always fail
                            mock_user_mgr.password_manager.verify_password.return_value = (
                                False
                            )

                            # No rate limit initially
                            mock_rate_limiter.check_rate_limit.return_value = None

                            # The 5th attempt should trigger lockout
                            mock_rate_limiter.record_failed_attempt.return_value = True

                            # Mock get_attempt_count for audit logging
                            mock_rate_limiter.get_attempt_count.return_value = 5

                            response = client.put(
                                "/api/users/change-password",
                                headers=authenticated_user_headers,
                                json={
                                    "old_password": "wrong_password",
                                    "new_password": "NewSecure123!Pass",
                                },
                            )

                            # Should return 429 because record_failed_attempt returned True
                            assert (
                                response.status_code == 429
                            ), f"Expected 429, got {response.status_code}"
                            assert (
                                "Too many failed attempts" in response.json()["detail"]
                            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
