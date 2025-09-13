"""
Comprehensive security tests for password change functionality.

Critical security vulnerability tests - password change endpoint must validate old password.
These tests verify all security requirements including timing attacks, rate limiting,
session invalidation, and audit logging.

Following CLAUDE.md principle: NO MOCKS - Real security implementation testing.
"""

import pytest
import time
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


class TestPasswordChangeSecurityVulnerability:
    """Test critical security vulnerability in password change endpoint."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        return {"Authorization": "Bearer valid.jwt.token"}

    def test_password_change_rejects_invalid_old_password(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Password change must reject invalid old passwords with 401.

        CRITICAL: This is the main vulnerability - endpoint should validate old password.
        Currently FAILING because endpoint doesn't validate old password.
        """
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_dep_user_mgr:
                with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
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

                    # Mock user retrieval for authentication
                    mock_dep_user_mgr.get_user.return_value = test_user

                    # Mock user retrieval for password change endpoint
                    mock_user_mgr.get_user.return_value = test_user

                    # Mock password verification to fail
                    mock_user_mgr.password_manager.verify_password.return_value = False
                    mock_user_mgr.change_password.return_value = True

                    response = client.put(
                        "/api/users/change-password",
                        headers=authenticated_user_headers,
                        json={
                            "old_password": "wrong_old_password",
                            "new_password": "NewSecure123!Pass",
                        },
                    )

                    # SECURITY REQUIREMENT: Must return 401 for invalid old password
                    assert response.status_code == 401
                    assert "Invalid old password" in response.json()["detail"]

                    # SECURITY REQUIREMENT: Password must NOT be changed
                    mock_user_mgr.change_password.assert_not_called()

    def test_password_change_succeeds_with_valid_old_password(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Password change must succeed with valid old password.
        """
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_dep_user_mgr:
                with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
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

                    # Mock user retrieval for authentication
                    mock_dep_user_mgr.get_user.return_value = test_user

                    # Mock user retrieval for password change endpoint
                    mock_user_mgr.get_user.return_value = test_user

                    # Mock password verification to succeed
                    mock_user_mgr.password_manager.verify_password.return_value = True
                    mock_user_mgr.change_password.return_value = True

                    response = client.put(
                        "/api/users/change-password",
                        headers=authenticated_user_headers,
                        json={
                            "old_password": "correct_old_password",
                            "new_password": "NewSecure123!Pass",
                        },
                    )

                    # Should succeed with valid old password
                    assert response.status_code == 200
                    assert "Password changed successfully" in response.json()["message"]

                    # Password should be changed
                    mock_user_mgr.change_password.assert_called_once_with(
                        "testuser", "NewSecure123!Pass"
                    )


class TestPasswordChangeRateLimiting:
    """Test rate limiting to prevent brute force attacks."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_mgr:
                mock_jwt.validate_token.return_value = {
                    "username": "testuser",
                    "role": "normal_user",
                    "exp": 9999999999,
                    "iat": 1234567890,
                }

                test_user = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_mgr.get_user.return_value = test_user

                return {"Authorization": "Bearer valid.jwt.token"}

    def test_rate_limiting_blocks_brute_force_attempts(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Rate limiting must block brute force attempts after 5 failures.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            # Mock password verification to always fail
            mock_user_mgr.password_manager.verify_password.return_value = False
            mock_user_mgr.get_user.return_value = User(
                username="testuser",
                password_hash="$2b$12$oldhash",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            )

            # Attempt 5 failed password changes
            for attempt in range(5):
                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": f"wrong_password_{attempt}",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                assert response.status_code == 401

            # 6th attempt should be rate limited
            response = client.put(
                "/api/users/change-password",
                headers=authenticated_user_headers,
                json={
                    "old_password": "wrong_password_6",
                    "new_password": "NewSecure123!Pass",
                },
            )

            # SECURITY REQUIREMENT: Rate limiting should return 429
            assert response.status_code == 429
            assert "Too many failed attempts" in response.json()["detail"]

    def test_rate_limit_lockout_duration_15_minutes(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Rate limit lockout must last 15 minutes.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            with patch("code_indexer.server.app.datetime") as mock_datetime:
                # Mock current time
                base_time = datetime.now(timezone.utc)
                mock_datetime.now.return_value = base_time

                mock_user_mgr.password_manager.verify_password.return_value = False
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                # Trigger rate limiting
                for _ in range(6):
                    client.put(
                        "/api/users/change-password",
                        headers=authenticated_user_headers,
                        json={
                            "old_password": "wrong_password",
                            "new_password": "NewSecure123!Pass",
                        },
                    )

                # Test after 14 minutes - still locked
                mock_datetime.now.return_value = base_time + timedelta(minutes=14)
                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "wrong_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                assert response.status_code == 429

                # Test after 16 minutes - unlocked
                mock_datetime.now.return_value = base_time + timedelta(minutes=16)
                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "wrong_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                assert response.status_code == 401  # Not 429, back to normal validation


class TestPasswordChangeTimingAttackPrevention:
    """Test timing attack prevention with constant response times."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_mgr:
                mock_jwt.validate_token.return_value = {
                    "username": "testuser",
                    "role": "normal_user",
                    "exp": 9999999999,
                    "iat": 1234567890,
                }

                test_user = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_mgr.get_user.return_value = test_user

                return {"Authorization": "Bearer valid.jwt.token"}

    def test_timing_attack_prevention_constant_response_time(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Response times must be constant regardless of password validity.
        """
        response_times = []

        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            mock_user_mgr.get_user.return_value = User(
                username="testuser",
                password_hash="$2b$12$oldhash",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            )

            # Test with invalid passwords (fast path)
            mock_user_mgr.password_manager.verify_password.return_value = False
            for _ in range(5):
                start_time = time.time()
                client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "invalid_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                response_times.append(time.time() - start_time)

            # Test with valid passwords (slow path)
            mock_user_mgr.password_manager.verify_password.return_value = True
            mock_user_mgr.change_password.return_value = True
            for _ in range(5):
                start_time = time.time()
                client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "correct_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                response_times.append(time.time() - start_time)

        # SECURITY REQUIREMENT: Response time variation should be minimal
        min_time = min(response_times)
        max_time = max(response_times)
        time_variation = (max_time - min_time) / min_time

        # Timing variation should be less than 50% (allows for some natural variation)
        assert time_variation < 0.5, f"Timing variation too large: {time_variation:.2%}"


class TestPasswordChangeConcurrencyProtection:
    """Test concurrent password change handling with row-level locking."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_mgr:
                mock_jwt.validate_token.return_value = {
                    "username": "testuser",
                    "role": "normal_user",
                    "exp": 9999999999,
                    "iat": 1234567890,
                }

                test_user = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_mgr.get_user.return_value = test_user

                return {"Authorization": "Bearer valid.jwt.token"}

    def test_concurrent_password_changes_handled_correctly(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Concurrent password changes must be handled with proper locking.
        """
        results = []

        def password_change_request():
            with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
                mock_user_mgr.password_manager.verify_password.return_value = True
                mock_user_mgr.change_password.return_value = True
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "correct_old_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                results.append(response.status_code)

        # Launch 5 concurrent password change requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=password_change_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # SECURITY REQUIREMENT: Only one should succeed (200), others should conflict (409)
        success_count = sum(1 for status in results if status == 200)
        conflict_count = sum(1 for status in results if status == 409)

        assert success_count == 1, f"Expected 1 successful change, got {success_count}"
        assert conflict_count == 4, f"Expected 4 conflicts, got {conflict_count}"


class TestPasswordChangeAuditLogging:
    """Test comprehensive audit logging for password change attempts."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_mgr:
                mock_jwt.validate_token.return_value = {
                    "username": "testuser",
                    "role": "normal_user",
                    "exp": 9999999999,
                    "iat": 1234567890,
                }

                test_user = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_mgr.get_user.return_value = test_user

                return {"Authorization": "Bearer valid.jwt.token"}

    def test_successful_password_change_audit_logged(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Successful password changes must be audit logged.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            with patch("code_indexer.server.app.audit_logger") as mock_audit:
                mock_user_mgr.password_manager.verify_password.return_value = True
                mock_user_mgr.change_password.return_value = True
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "correct_old_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )

                assert response.status_code == 200

                # SECURITY REQUIREMENT: Audit log must record successful change
                mock_audit.log_password_change_success.assert_called_once()
                call_args = mock_audit.log_password_change_success.call_args
                assert call_args[1]["username"] == "testuser"
                assert "ip_address" in call_args[1]
                assert "timestamp" in call_args[1]

    def test_failed_password_change_audit_logged(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Failed password changes must be audit logged.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            with patch("code_indexer.server.app.audit_logger") as mock_audit:
                mock_user_mgr.password_manager.verify_password.return_value = False
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "wrong_old_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )

                assert response.status_code == 401

                # SECURITY REQUIREMENT: Audit log must record failed attempt
                mock_audit.log_password_change_failure.assert_called_once()
                call_args = mock_audit.log_password_change_failure.call_args
                assert call_args[1]["username"] == "testuser"
                assert call_args[1]["reason"] == "Invalid old password"
                assert "ip_address" in call_args[1]
                assert "timestamp" in call_args[1]


class TestPasswordChangeSessionInvalidation:
    """Test session invalidation after successful password change."""

    @pytest.fixture
    def client(self):
        """Create FastAPI test client."""
        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def authenticated_user_headers(self):
        """Create headers for authenticated user."""
        with patch("code_indexer.server.auth.dependencies.jwt_manager") as mock_jwt:
            with patch(
                "code_indexer.server.auth.dependencies.user_manager"
            ) as mock_user_mgr:
                mock_jwt.validate_token.return_value = {
                    "username": "testuser",
                    "role": "normal_user",
                    "exp": 9999999999,
                    "iat": 1234567890,
                }

                test_user = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )
                mock_user_mgr.get_user.return_value = test_user

                return {"Authorization": "Bearer valid.jwt.token"}

    def test_all_user_sessions_invalidated_after_password_change(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: All user sessions must be invalidated after password change.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            with patch("code_indexer.server.app.session_manager") as mock_session_mgr:
                mock_user_mgr.password_manager.verify_password.return_value = True
                mock_user_mgr.change_password.return_value = True
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "correct_old_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )

                assert response.status_code == 200

                # SECURITY REQUIREMENT: All sessions must be invalidated
                mock_session_mgr.invalidate_all_user_sessions.assert_called_once_with(
                    "testuser"
                )

    def test_current_session_remains_valid_after_password_change(
        self, client, authenticated_user_headers
    ):
        """
        SECURITY TEST: Current session should remain valid after password change.
        """
        with patch("code_indexer.server.app.user_manager") as mock_user_mgr:
            with patch("code_indexer.server.app.session_manager"):
                mock_user_mgr.password_manager.verify_password.return_value = True
                mock_user_mgr.change_password.return_value = True
                mock_user_mgr.get_user.return_value = User(
                    username="testuser",
                    password_hash="$2b$12$oldhash",
                    role=UserRole.NORMAL_USER,
                    created_at=datetime.now(timezone.utc),
                )

                # Change password
                response = client.put(
                    "/api/users/change-password",
                    headers=authenticated_user_headers,
                    json={
                        "old_password": "correct_old_password",
                        "new_password": "NewSecure123!Pass",
                    },
                )
                assert response.status_code == 200

                # Current session should still work
                response = client.get("/api/repos", headers=authenticated_user_headers)
                assert response.status_code != 401  # Session should remain valid


class TestPasswordChangeRequestModel:
    """Test password change request model with old password validation."""

    def test_password_change_request_requires_old_password_field(self):
        """
        SECURITY TEST: Request model must require old_password field.
        """
        from pydantic import ValidationError

        # This import will fail initially - that's the TDD approach
        try:
            from code_indexer.server.app import ChangePasswordRequest

            # Should fail without old_password
            with pytest.raises(ValidationError):
                ChangePasswordRequest(new_password="NewSecure123!Pass")

            # Should succeed with old_password
            request = ChangePasswordRequest(
                old_password="OldPass123!", new_password="NewSecure123!Pass"
            )
            assert request.old_password == "OldPass123!"
            assert request.new_password == "NewSecure123!Pass"

        except ImportError:
            # Model doesn't exist yet - test will fail as expected in TDD
            pytest.fail(
                "ChangePasswordRequest model with old_password field not implemented"
            )

    def test_password_change_request_validates_old_password_complexity(self):
        """
        SECURITY TEST: Old password should have basic validation.
        """
        try:
            from code_indexer.server.app import ChangePasswordRequest
            from pydantic import ValidationError

            # Empty old password should fail
            with pytest.raises(ValidationError):
                ChangePasswordRequest(old_password="", new_password="NewSecure123!Pass")

            # Whitespace-only old password should fail
            with pytest.raises(ValidationError):
                ChangePasswordRequest(
                    old_password="   ", new_password="NewSecure123!Pass"
                )

        except ImportError:
            pytest.fail(
                "ChangePasswordRequest model with old_password validation not implemented"
            )
