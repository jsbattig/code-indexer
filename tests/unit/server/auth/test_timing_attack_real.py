"""
Real Timing Attack Prevention Test Suite - Foundation #1 Compliant.

Tests timing attack prevention using real password validation without mocks.
No mocks for timing-critical functionality following MESSI Rule #1.
"""

import pytest
import time
import bcrypt
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.mark.e2e
class TestRealTimingAttackPrevention:
    """Test timing attack prevention with real password operations."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def test_user_with_real_hash(self):
        """Create test user with real bcrypt hash."""
        # Create real bcrypt hash for testing
        real_password = "TestPassword123!"
        password_hash = bcrypt.hashpw(real_password.encode("utf-8"), bcrypt.gensalt())

        return {
            "user": User(
                username="timingtest",
                password_hash=password_hash.decode("utf-8"),
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            ),
            "correct_password": real_password,
            "wrong_password": "WrongPassword123!",
        }

    def test_timing_attack_prevention_real_password_validation(
        self, client, test_user_with_real_hash
    ):
        """
        SECURITY TEST: Real password validation timing should be constant.

        This test uses REAL password hashing and validation without mocks
        to verify timing attack prevention works with actual bcrypt operations.
        """
        # Clear rate limiter state to ensure clean test
        from code_indexer.server.auth.rate_limiter import password_change_rate_limiter

        password_change_rate_limiter._attempts.clear()

        test_data = test_user_with_real_hash
        response_times = []

        # Mock only the authentication and user retrieval (not password validation)
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_dep_user_mgr:
                with patch("code_indexer.server.app.user_manager") as mock_user_mgr:

                    # Mock JWT authentication
                    mock_jwt.validate_token.return_value = {
                        "username": "timingtest",
                        "role": "normal_user",
                        "exp": 9999999999,
                        "iat": 1234567890,
                    }

                    # Mock user retrieval for authentication
                    mock_dep_user_mgr.get_user.return_value = test_data["user"]
                    mock_user_mgr.get_user.return_value = test_data["user"]

                    # CRITICAL: Use real password manager for verification
                    # This ensures timing attack prevention is actually tested
                    from code_indexer.server.auth.password_manager import (
                        PasswordManager,
                    )

                    real_password_manager = PasswordManager()
                    mock_user_mgr.password_manager = real_password_manager

                    # Mock only change_password to avoid actual password changes
                    mock_user_mgr.change_password.return_value = True

                    # Test with incorrect passwords (should use timing attack prevention)
                    # Use only 3 attempts to avoid rate limiting (limit is 5)
                    for i in range(3):
                        start_time = time.time()
                        response = client.put(
                            "/api/users/change-password",
                            headers={"Authorization": "Bearer valid.jwt.token"},
                            json={
                                "old_password": test_data["wrong_password"],
                                "new_password": "NewSecure123!Pass",
                            },
                        )
                        elapsed = time.time() - start_time
                        response_times.append(elapsed)

                        # Should fail with 401 (invalid old password)
                        assert response.status_code == 401
                        print(f"Invalid password attempt {i+1}: {elapsed:.4f}s")

                    # Test with correct passwords (should use timing attack prevention)
                    for i in range(3):
                        start_time = time.time()
                        response = client.put(
                            "/api/users/change-password",
                            headers={"Authorization": "Bearer valid.jwt.token"},
                            json={
                                "old_password": test_data["correct_password"],
                                "new_password": "NewSecure123!Pass",
                            },
                        )
                        elapsed = time.time() - start_time
                        response_times.append(elapsed)

                        # Should succeed with 200
                        assert response.status_code == 200
                        print(f"Valid password attempt {i+1}: {elapsed:.4f}s")

        # SECURITY REQUIREMENT: Response time variation should be minimal
        min_time = min(response_times)
        max_time = max(response_times)
        time_variation = (max_time - min_time) / min_time

        print(f"Response times: {[f'{t:.4f}s' for t in response_times]}")
        print(f"Min: {min_time:.4f}s, Max: {max_time:.4f}s")
        print(f"Timing variation: {time_variation:.2%} (target: <50%)")

        # Timing variation should be less than 50% (allows for some natural variation)
        assert time_variation < 0.5, f"Timing variation too large: {time_variation:.2%}"

    def test_timing_attack_prevention_unit_level(self):
        """
        UNIT TEST: Test timing attack prevention directly without HTTP overhead.
        """
        from code_indexer.server.auth.timing_attack_prevention import (
            timing_attack_prevention,
        )
        from code_indexer.server.auth.password_manager import PasswordManager

        password_manager = PasswordManager()

        # Create real password hash
        test_password = "RealTestPassword123!"
        wrong_password = "WrongPassword123!"
        password_hash = password_manager.hash_password(test_password)

        response_times = []

        # Test with wrong passwords (fast bcrypt failure)
        for i in range(5):
            start_time = time.time()
            result = timing_attack_prevention.normalize_password_validation_timing(
                password_manager.verify_password, wrong_password, password_hash
            )
            elapsed = time.time() - start_time
            response_times.append(elapsed)
            assert result is False
            print(f"Wrong password {i+1}: {elapsed:.4f}s")

        # Test with correct passwords (full bcrypt verification)
        for i in range(5):
            start_time = time.time()
            result = timing_attack_prevention.normalize_password_validation_timing(
                password_manager.verify_password, test_password, password_hash
            )
            elapsed = time.time() - start_time
            response_times.append(elapsed)
            assert result is True
            print(f"Correct password {i+1}: {elapsed:.4f}s")

        # SECURITY REQUIREMENT: Response time variation should be minimal
        min_time = min(response_times)
        max_time = max(response_times)
        time_variation = (max_time - min_time) / min_time

        print(f"Unit test timing variation: {time_variation:.2%} (target: <50%)")

        # Should have very low timing variation
        assert (
            time_variation < 0.5
        ), f"Unit-level timing variation too large: {time_variation:.2%}"
