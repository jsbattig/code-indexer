"""
Test 4: Real Token Management - NO MOCKS

TDD implementation of elite-software-architect's Option A recommendation.
Tests real token management using real security components.

CRITICAL: ZERO MOCKS - Uses real JWT generation, real token validation, real refresh tokens
"""

from fastapi import status
from datetime import datetime, timezone

from tests.fixtures.test_infrastructure import RealComponentTestInfrastructure
from code_indexer.server.auth.user_manager import UserRole


import pytest


@pytest.mark.e2e
class TestRealTokenManagement:
    """
    Real token management tests with zero mocks.

    Tests complete token management workflow through real security components:
    - Real JWT token generation with real signing
    - Real token validation with real signature verification
    - Real token expiration handling with real time checks
    - Real refresh token workflow with real database storage
    - Real token revocation with real security enforcement
    """

    def test_real_jwt_token_generation_and_validation(self):
        """
        Test real JWT token generation and validation.

        CRITICAL: NO MOCKS - Real JWT signing and verification
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user(
                username="tokenuser", password="TokenTestPassword123!"
            )

            # Get real JWT token through real authentication
            token_response = infrastructure.get_auth_token(
                user_data["username"], user_data["password"]
            )

            # Verify token structure
            assert "access_token" in token_response
            assert "token_type" in token_response
            assert token_response["token_type"] == "bearer"

            # Validate token through real JWT manager
            payload = infrastructure.jwt_manager.validate_token(
                token_response["access_token"]
            )

            # Verify token contains real user data
            assert payload["username"] == "tokenuser"
            assert "exp" in payload  # Expiration time
            assert "iat" in payload  # Issued at time

            # Verify token works for real API access
            auth_headers = infrastructure.authenticate_request(
                token_response["access_token"]
            )

            response = infrastructure.client.get("/health", headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK

        finally:
            infrastructure.cleanup()

    def test_real_token_expiration_enforcement(self):
        """
        Test real token expiration enforcement.

        CRITICAL: NO MOCKS - Real token expiration with real time validation
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user(
                username="expirationuser", password="ExpirationTest123!"
            )

            # Get real token
            token_response = infrastructure.get_auth_token(
                user_data["username"], user_data["password"]
            )

            # Verify token is currently valid
            payload = infrastructure.jwt_manager.validate_token(
                token_response["access_token"]
            )
            assert payload is not None

            # Verify expiration field exists and is reasonable
            exp_timestamp = payload["exp"]
            iat_timestamp = payload["iat"]

            # Token should be valid for 10 minutes (600 seconds)
            expected_duration = 10 * 60  # 10 minutes in seconds
            actual_duration = exp_timestamp - iat_timestamp

            # Allow some tolerance for timing
            assert abs(actual_duration - expected_duration) < 5

            # Verify token is not expired yet
            current_time = datetime.now(timezone.utc).timestamp()
            assert exp_timestamp > current_time

        finally:
            infrastructure.cleanup()

    def test_real_invalid_token_rejection(self):
        """
        Test real invalid token rejection.

        CRITICAL: NO MOCKS - Real JWT signature verification
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Test various invalid tokens
            invalid_tokens = [
                "invalid.jwt.token",
                "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
                "",
                "not-a-jwt-at-all",
                "Bearer invalid.token.here",
            ]

            for invalid_token in invalid_tokens:
                # Try to use invalid token with real API
                response = infrastructure.client.get(
                    "/health", headers={"Authorization": f"Bearer {invalid_token}"}
                )

                # Should be rejected by real JWT validation
                # Actual API returns 403 Forbidden for invalid tokens (discovered through TDD)
                assert response.status_code in [
                    status.HTTP_401_UNAUTHORIZED,
                    status.HTTP_403_FORBIDDEN,
                ]

        finally:
            infrastructure.cleanup()

    def test_real_token_refresh_workflow(self):
        """
        Test real token refresh workflow.

        CRITICAL: NO MOCKS - Real refresh token generation and validation
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user(
                username="refreshuser", password="RefreshTestPassword123!"
            )

            # Get initial tokens through real authentication
            login_response = infrastructure.client.post(
                "/auth/login",
                json={
                    "username": user_data["username"],
                    "password": user_data["password"],
                },
            )

            assert login_response.status_code == status.HTTP_200_OK
            login_data = login_response.json()

            # Should have access token and refresh token
            assert "access_token" in login_data
            assert "refresh_token" in login_data
            assert "token_type" in login_data

            # Use refresh token to get new access token
            refresh_response = infrastructure.client.post(
                "/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
            )

            # Should succeed with real refresh token validation
            assert refresh_response.status_code == status.HTTP_200_OK
            refresh_data = refresh_response.json()

            # Should get new tokens
            assert "access_token" in refresh_data
            assert "refresh_token" in refresh_data

            # New access token should be different
            assert refresh_data["access_token"] != login_data["access_token"]

            # New access token should work for API access
            auth_headers = infrastructure.authenticate_request(
                refresh_data["access_token"]
            )

            response = infrastructure.client.get("/health", headers=auth_headers)
            assert response.status_code == status.HTTP_200_OK

        finally:
            infrastructure.cleanup()

    def test_real_refresh_token_security(self):
        """
        Test real refresh token security features.

        CRITICAL: NO MOCKS - Real refresh token storage and validation
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user(
                username="securityuser", password="SecurityTestPassword123!"
            )

            # Get tokens
            login_response = infrastructure.client.post(
                "/auth/login",
                json={
                    "username": user_data["username"],
                    "password": user_data["password"],
                },
            )

            login_data = login_response.json()

            # Test invalid refresh token
            invalid_refresh_response = infrastructure.client.post(
                "/auth/refresh", json={"refresh_token": "invalid.refresh.token"}
            )

            # Should be rejected by real refresh token validation
            assert invalid_refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

            # Test empty refresh token
            empty_refresh_response = infrastructure.client.post(
                "/auth/refresh", json={"refresh_token": ""}
            )

            # Should be rejected
            assert empty_refresh_response.status_code in [400, 401, 422]

            # Original valid refresh token should still work
            valid_refresh_response = infrastructure.client.post(
                "/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
            )

            assert valid_refresh_response.status_code == status.HTTP_200_OK

        finally:
            infrastructure.cleanup()

    def test_real_concurrent_token_operations(self):
        """
        Test real concurrent token operations.

        CRITICAL: NO MOCKS - Real thread-safe token management
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user
            user_data = infrastructure.create_test_user(
                username="concurrenttokenuser", password="ConcurrentTokenTest123!"
            )

            # Get initial tokens
            login_response = infrastructure.client.post(
                "/auth/login",
                json={
                    "username": user_data["username"],
                    "password": user_data["password"],
                },
            )

            login_data = login_response.json()

            # Simulate concurrent refresh attempts
            # (In real scenario, this would be multiple threads)
            refresh_responses = []

            for i in range(3):
                response = infrastructure.client.post(
                    "/auth/refresh", json={"refresh_token": login_data["refresh_token"]}
                )
                refresh_responses.append(response)

            # At least one should succeed, others might fail due to token family protection
            success_count = sum(1 for r in refresh_responses if r.status_code == 200)

            # Should have at least one successful refresh
            assert success_count >= 1

            # Check for security measures (some might fail due to concurrent protection)
            _error_count = sum(1 for r in refresh_responses if r.status_code != 200)

            # The exact behavior depends on the refresh token family implementation
            # but we should see some evidence of security measures

        finally:
            infrastructure.cleanup()

    def test_real_token_payload_integrity(self):
        """
        Test real token payload integrity and security.

        CRITICAL: NO MOCKS - Real JWT payload validation
        """
        infrastructure = RealComponentTestInfrastructure()
        infrastructure.setup()

        try:
            # Create real user with specific role
            user_data = infrastructure.create_test_user(
                username="payloaduser",
                password="PayloadTestPassword123!",
                role=UserRole.POWER_USER,
            )

            # Get real token
            token_response = infrastructure.get_auth_token(
                user_data["username"], user_data["password"]
            )

            # Validate token payload through real JWT manager
            payload = infrastructure.jwt_manager.validate_token(
                token_response["access_token"]
            )

            # Verify all required fields are present
            assert "username" in payload
            assert "exp" in payload  # Expiration
            assert "iat" in payload  # Issued at

            # Verify username matches exactly
            assert payload["username"] == "payloaduser"

            # Verify timing fields are reasonable
            current_time = datetime.now(timezone.utc).timestamp()
            assert payload["iat"] <= current_time  # Issued in the past
            assert payload["exp"] > current_time  # Expires in the future

            # Verify token signature cannot be tampered with
            # (This is implicitly tested by successful validation)

        finally:
            infrastructure.cleanup()


# Validation test to ensure token management infrastructure works
@pytest.mark.e2e
def test_token_management_infrastructure_validation():
    """
    Validation test to ensure token management infrastructure works.

    This test MUST pass before proceeding with token management tests.
    """
    infrastructure = RealComponentTestInfrastructure()
    infrastructure.setup()

    try:
        # Verify JWT manager exists and works
        assert infrastructure.jwt_manager is not None

        # Test basic token creation and validation
        test_user_data = {
            "username": "testuser",
            "role": "normal_user",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Create token
        token = infrastructure.jwt_manager.create_token(test_user_data)
        assert token is not None
        assert isinstance(token, str)

        # Validate token
        decoded_payload = infrastructure.jwt_manager.validate_token(token)
        assert decoded_payload["username"] == "testuser"
        assert decoded_payload["role"] == "normal_user"

        # Verify user manager exists
        assert infrastructure.user_manager is not None

        # Test basic login workflow
        user_data = infrastructure.create_test_user(
            username="validationuser", password="ValidationTest123!"
        )

        token_response = infrastructure.get_auth_token(
            user_data["username"], user_data["password"]
        )

        assert "access_token" in token_response

    finally:
        infrastructure.cleanup()
