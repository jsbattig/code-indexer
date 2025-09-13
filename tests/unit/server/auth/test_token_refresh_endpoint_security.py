"""
Test-Driven Development tests for secure token refresh endpoint.

SECURITY-FOCUSED TEST COVERAGE:
- Token refresh rotation (new access + refresh token pair)
- Invalid/expired refresh token rejection
- Revoked refresh token handling (password change scenarios)
- Token family detection and replay attack prevention
- Concurrent refresh attempt handling
- Comprehensive audit logging for security events
- Token family tracking to detect suspicious activity

Following TDD principles: write failing tests first, implement to make them pass.
"""

from datetime import datetime, timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
from fastapi import status

# Import the server application and test utilities
from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


class TestTokenRefreshSecurity:
    """Test suite for secure token refresh functionality."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.app = create_app()
        self.client = TestClient(self.app)

    def _get_auth_headers(self):
        """Helper method to get authentication headers for testing."""
        # Mock all required managers for login
        with (
            patch("code_indexer.server.app.user_manager") as mock_user_manager,
            patch("code_indexer.server.app.refresh_token_manager") as mock_refresh_mgr,
        ):

            test_user = User(
                username="testuser",
                password_hash="$2b$12$hash",
                role=UserRole.NORMAL_USER,
                created_at=datetime.now(timezone.utc),
            )
            mock_user_manager.authenticate_user.return_value = test_user
            mock_user_manager.get_user.return_value = test_user

            # Mock refresh token manager for login
            mock_refresh_mgr.create_token_family.return_value = "family_123"
            mock_refresh_mgr.create_initial_refresh_token.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "refresh_token_expires_in": 7 * 24 * 60 * 60,
            }

            # Login to get initial tokens for testing
            login_response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )
            assert login_response.status_code == 200
            login_data = login_response.json()

            return {"Authorization": f"Bearer {login_data['access_token']}"}

    def test_token_refresh_rotation_creates_new_tokens(self):
        """
        Test that token refresh creates new access and refresh tokens.

        SECURITY REQUIREMENT: Token rotation prevents token reuse attacks.
        Each refresh should create a new access + refresh token pair.
        """
        # This test will fail initially as we need to implement the refresh token system
        headers = self._get_auth_headers()

        with (
            patch("code_indexer.server.app.refresh_token_manager") as mock_manager,
            patch(
                "code_indexer.server.app.refresh_token_rate_limiter"
            ) as mock_rate_limiter,
        ):

            # Mock successful validation and rotation
            mock_manager.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
                "token_id": "token_123",
                "parent_token_id": "parent_123",
            }

            # Mock no rate limiting
            mock_rate_limiter.check_rate_limit.return_value = None

            # Submit refresh request with refresh token
            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_refresh_token_456"},
                headers=headers,
            )

            assert response.status_code == 200
            data = response.json()

            # Verify new tokens are returned
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["access_token"] == "new_access_token_123"
            assert data["refresh_token"] == "new_refresh_token_123"
            assert data["token_type"] == "bearer"

            # Verify token rotation was called
            mock_manager.validate_and_rotate_refresh_token.assert_called_once()

    def test_invalid_refresh_token_rejected_with_401(self):
        """
        Test that invalid refresh tokens are rejected with 401 Unauthorized.

        SECURITY REQUIREMENT: Invalid tokens must be rejected immediately.
        """
        headers = self._get_auth_headers()

        with (
            patch("code_indexer.server.app.refresh_token_manager") as mock_manager,
            patch(
                "code_indexer.server.app.refresh_token_rate_limiter"
            ) as mock_rate_limiter,
        ):

            mock_manager.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Invalid refresh token",
            }
            mock_rate_limiter.check_rate_limit.return_value = None

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "invalid_token"},
                headers=headers,
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            data = response.json()
            assert "Invalid refresh token" in data["detail"]

    def test_expired_refresh_token_rejected_with_401(self):
        """
        Test that expired refresh tokens are rejected with 401 Unauthorized.

        SECURITY REQUIREMENT: Expired tokens must be rejected.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Refresh token has expired",
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "expired_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            data = response.json()
            assert "expired" in data["detail"].lower()

    def test_revoked_refresh_token_handling_password_change(self):
        """
        Test that revoked refresh tokens (after password change) are properly handled.

        SECURITY REQUIREMENT: Password change must revoke all refresh tokens.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Refresh token revoked due to password change",
                "revocation_reason": "password_change",
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "revoked_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            data = response.json()
            assert "revoked" in data["detail"].lower()

    def test_token_family_replay_attack_detection(self):
        """
        Test that token family tracking detects replay attacks.

        SECURITY REQUIREMENT: Replay attacks must be detected and all family tokens revoked.
        """
        with (
            patch("code_indexer.server.app.refresh_token_manager") as mock_manager,
            patch(
                "code_indexer.server.app.refresh_token_rate_limiter"
            ) as mock_rate_limiter,
        ):

            # Simulate replay attack detection
            mock_manager.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Token replay attack detected",
                "security_incident": True,
                "family_revoked": True,
            }
            mock_rate_limiter.check_rate_limit.return_value = None

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "replayed_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            data = response.json()
            assert "replay attack" in data["detail"].lower()

    def test_concurrent_refresh_attempts_handled_with_409(self):
        """
        Test that concurrent refresh attempts are handled with 409 Conflict.

        SECURITY REQUIREMENT: Concurrent refresh should be detected and handled.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Concurrent refresh attempt detected",
                "concurrent_conflict": True,
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "concurrent_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == status.HTTP_409_CONFLICT
            data = response.json()
            assert "concurrent" in data["detail"].lower()

    def test_comprehensive_audit_logging_refresh_success(self):
        """
        Test that successful refresh attempts are comprehensively logged.

        SECURITY REQUIREMENT: All refresh attempts must be audited.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            with patch(
                "code_indexer.server.auth.audit_logger.password_audit_logger"
            ) as mock_audit:
                mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                    "valid": True,
                    "user_data": {"username": "testuser", "role": "normal_user"},
                    "new_access_token": "new_access_token_123",
                    "new_refresh_token": "new_refresh_token_123",
                    "family_id": "family_123",
                }

                response = self.client.post(
                    "/api/auth/refresh",
                    json={"refresh_token": "valid_refresh_token"},
                    headers=self._get_auth_headers(),
                )

                assert response.status_code == 200

                # Verify audit logging was called
                mock_audit.log_token_refresh_success.assert_called_once()
                call_args = mock_audit.log_token_refresh_success.call_args

                # Verify audit log contains security information
                assert call_args[1]["username"] == "testuser"
                assert "family_id" in call_args[1]
                assert "ip_address" in call_args[1]

    def test_comprehensive_audit_logging_refresh_failure(self):
        """
        Test that failed refresh attempts are comprehensively logged.

        SECURITY REQUIREMENT: All refresh failures must be audited for security monitoring.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            with patch(
                "code_indexer.server.auth.audit_logger.password_audit_logger"
            ) as mock_audit:
                mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                    "valid": False,
                    "error": "Invalid refresh token",
                    "security_incident": True,
                }

                response = self.client.post(
                    "/api/auth/refresh",
                    json={"refresh_token": "invalid_token"},
                    headers=self._get_auth_headers(),
                )

                assert response.status_code == status.HTTP_401_UNAUTHORIZED

                # Verify audit logging was called for failure
                mock_audit.log_token_refresh_failure.assert_called_once()
                call_args = mock_audit.log_token_refresh_failure.call_args

                # Verify audit log contains security information
                assert "username" in call_args[1]
                assert "reason" in call_args[1]
                assert "ip_address" in call_args[1]
                assert call_args[1]["security_incident"] is True

    def test_refresh_token_request_validation(self):
        """
        Test that refresh token requests are properly validated.

        SECURITY REQUIREMENT: Request validation prevents malformed attacks.
        """
        # Missing refresh_token
        response = self.client.post("/api/auth/refresh", json={}, headers=self.headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Empty refresh_token
        response = self.client.post(
            "/api/auth/refresh", json={"refresh_token": ""}, headers=self.headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Non-string refresh_token
        response = self.client.post(
            "/api/auth/refresh", json={"refresh_token": 12345}, headers=self.headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_refresh_token_lifetime_validation(self):
        """
        Test that refresh tokens have appropriate lifetime (7 days vs 15 minutes for access).

        SECURITY REQUIREMENT: Refresh tokens should have longer lifetime than access tokens.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
                "refresh_token_expires_in": 7 * 24 * 60 * 60,  # 7 days
                "access_token_expires_in": 15 * 60,  # 15 minutes
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_refresh_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == 200
            data = response.json()

            # Verify token lifetimes are properly set
            assert data.get("refresh_token_expires_in", 0) > data.get(
                "access_token_expires_in", 0
            )

    def test_refresh_endpoint_rate_limiting(self):
        """
        Test that the refresh endpoint has appropriate rate limiting.

        SECURITY REQUIREMENT: Rate limiting prevents brute force attacks.
        """
        with patch(
            "code_indexer.server.auth.rate_limiter.refresh_token_rate_limiter"
        ) as mock_rate_limiter:
            mock_rate_limiter.check_rate_limit.return_value = (
                "Rate limit exceeded. Try again in 5 minutes."
            )

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
            data = response.json()
            assert "rate limit" in data["detail"].lower()

    def test_refresh_token_storage_security(self):
        """
        Test that refresh tokens are stored securely.

        SECURITY REQUIREMENT: Refresh tokens must be stored with proper security.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            # Mock secure storage verification
            mock_manager.return_value.verify_secure_storage.return_value = True
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_refresh_token"},
                headers=self._get_auth_headers(),
            )

            assert response.status_code == 200

            # Verify secure storage was used
            mock_manager.return_value.verify_secure_storage.assert_called_once()


class TestRefreshTokenFamilyTracking:
    """Test suite for token family tracking and replay attack detection."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_token_family_creation_on_login(self):
        """
        Test that a new token family is created on login.

        SECURITY REQUIREMENT: Each login session gets a unique family ID.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.create_token_family.return_value = "family_123"

            response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )

            assert response.status_code == 200
            data = response.json()

            # Verify token family was created
            mock_manager.return_value.create_token_family.assert_called_once()
            assert "refresh_token" in data

    def test_token_family_relationship_tracking(self):
        """
        Test that token family relationships are properly tracked.

        SECURITY REQUIREMENT: All tokens in a family must be tracked.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            # Mock family relationship tracking
            mock_manager.return_value.track_token_relationship.return_value = True
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
                "parent_token_id": "token_456",
            }

            # Login first to get initial tokens
            login_response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )
            headers = {
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "parent_refresh_token"},
                headers=headers,
            )

            assert response.status_code == 200

            # Verify token relationship tracking
            mock_manager.return_value.track_token_relationship.assert_called_once()

    def test_family_revocation_on_replay_detection(self):
        """
        Test that entire token family is revoked when replay attack is detected.

        SECURITY REQUIREMENT: Replay attacks must trigger family revocation.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": False,
                "error": "Token replay attack detected",
                "security_incident": True,
                "family_revoked": True,
                "family_id": "family_123",
            }
            mock_manager.return_value.revoke_token_family.return_value = (
                5  # 5 tokens revoked
            )

            # Login first to get initial tokens
            login_response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )
            headers = {
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "replayed_token"},
                headers=headers,
            )

            assert response.status_code == status.HTTP_401_UNAUTHORIZED

            # Verify family revocation was triggered
            mock_manager.return_value.revoke_token_family.assert_called_once_with(
                "family_123"
            )


class TestRefreshTokenIntegrationWithExistingAuth:
    """Test suite for integration with existing CIDX authentication system."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_refresh_integrates_with_existing_user_manager(self):
        """
        Test that refresh token system integrates with existing UserManager.

        INTEGRATION REQUIREMENT: Must use existing user management system.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
            }

            # Login first to get initial tokens
            login_response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )
            headers = {
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_refresh_token"},
                headers=headers,
            )

            assert response.status_code == 200
            data = response.json()

            # Verify user data comes from existing UserManager
            assert "user" in data
            assert data["user"]["username"] == "testuser"

    def test_refresh_integrates_with_existing_jwt_manager(self):
        """
        Test that refresh token system integrates with existing JWTManager.

        INTEGRATION REQUIREMENT: Must use existing JWT creation patterns.
        """
        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                "valid": True,
                "user_data": {"username": "testuser", "role": "normal_user"},
                "new_access_token": "new_access_token_123",
                "new_refresh_token": "new_refresh_token_123",
                "family_id": "family_123",
            }

            # Login first to get initial tokens
            login_response = self.client.post(
                "/auth/login", json={"username": "testuser", "password": "testpass123"}
            )
            headers = {
                "Authorization": f"Bearer {login_response.json()['access_token']}"
            }

            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": "valid_refresh_token"},
                headers=headers,
            )

            assert response.status_code == 200
            data = response.json()

            # Verify token format matches existing JWT pattern
            assert data["token_type"] == "bearer"
            assert isinstance(data["access_token"], str)
            assert len(data["access_token"]) > 0

    def test_refresh_integrates_with_existing_audit_logging(self):
        """
        Test that refresh token system integrates with existing audit logging.

        INTEGRATION REQUIREMENT: Must use existing audit logging system.
        """
        # Login first to get initial tokens
        login_response = self.client.post(
            "/auth/login", json={"username": "testuser", "password": "testpass123"}
        )
        headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

        with patch(
            "code_indexer.server.auth.refresh_token_manager.RefreshTokenManager"
        ) as mock_manager:
            with patch(
                "code_indexer.server.auth.audit_logger.password_audit_logger"
            ) as mock_audit:
                mock_manager.return_value.validate_and_rotate_refresh_token.return_value = {
                    "valid": True,
                    "user_data": {"username": "testuser", "role": "normal_user"},
                    "new_access_token": "new_access_token_123",
                    "new_refresh_token": "new_refresh_token_123",
                    "family_id": "family_123",
                }

                response = self.client.post(
                    "/api/auth/refresh",
                    json={"refresh_token": "valid_refresh_token"},
                    headers=headers,
                )

                assert response.status_code == 200

                # Verify existing audit logger is used
                mock_audit.log_token_refresh_success.assert_called_once()
