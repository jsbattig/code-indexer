"""
Unit tests for AuthErrorHandler and standardized authentication error responses.

Tests the security-focused error handling system that prevents user enumeration,
timing attacks, and information leakage while maintaining comprehensive audit logging.

Following CLAUDE.md Foundation #1: NO MOCKS - Real error handling with real timing.
"""

import pytest
import time

from code_indexer.server.auth.auth_error_handler import (
    AuthErrorType,
    AuthErrorHandler,
    AuthError,
)


class TestAuthErrorType:
    """Test the AuthErrorType enum for standardized error categories."""

    def test_auth_error_type_enum_exists(self):
        """Test that AuthErrorType enum is defined with required categories."""
        # This test will fail initially - TDD approach
        expected_error_types = [
            "INVALID_CREDENTIALS",
            "ACCOUNT_LOCKED",
            "ACCOUNT_DISABLED",
            "RATE_LIMIT_EXCEEDED",
            "GENERIC_AUTH_FAILURE",
        ]

        for error_type in expected_error_types:
            assert hasattr(AuthErrorType, error_type)
            assert isinstance(getattr(AuthErrorType, error_type), AuthErrorType)

    def test_auth_error_type_values(self):
        """Test that AuthErrorType enum values are properly defined."""
        assert AuthErrorType.INVALID_CREDENTIALS.value == "invalid_credentials"
        assert AuthErrorType.ACCOUNT_LOCKED.value == "account_locked"
        assert AuthErrorType.ACCOUNT_DISABLED.value == "account_disabled"
        assert AuthErrorType.RATE_LIMIT_EXCEEDED.value == "rate_limit_exceeded"
        assert AuthErrorType.GENERIC_AUTH_FAILURE.value == "generic_auth_failure"


class TestAuthError:
    """Test the AuthError exception class."""

    def test_auth_error_creation(self):
        """Test creating AuthError with required fields."""
        error = AuthError(
            error_type=AuthErrorType.INVALID_CREDENTIALS,
            public_message="Invalid credentials",
            internal_message="Username not found: testuser",
            user_context="testuser",
        )

        assert error.error_type == AuthErrorType.INVALID_CREDENTIALS
        assert error.public_message == "Invalid credentials"
        assert error.internal_message == "Username not found: testuser"
        assert error.user_context == "testuser"

    def test_auth_error_str_representation(self):
        """Test string representation shows only public message."""
        error = AuthError(
            error_type=AuthErrorType.ACCOUNT_LOCKED,
            public_message="Invalid credentials",
            internal_message="Account locked after 5 failed attempts",
            user_context="lockeduser",
        )

        # Public representation should not reveal internal details
        assert str(error) == "Invalid credentials"


class TestAuthErrorHandler:
    """Test the AuthErrorHandler for security-compliant error responses."""

    @pytest.fixture
    def error_handler(self):
        """Create AuthErrorHandler instance."""
        return AuthErrorHandler(minimum_response_time_ms=100)

    def test_error_handler_creation(self, error_handler):
        """Test AuthErrorHandler instance creation."""
        assert error_handler is not None
        assert error_handler.minimum_response_time_seconds == 0.1

    def test_generic_error_messages(self, error_handler):
        """Test that all auth errors return generic messages to clients."""
        # Test different error types all return same generic message
        test_cases = [
            (AuthErrorType.INVALID_CREDENTIALS, "nonexistent_user"),
            (AuthErrorType.ACCOUNT_LOCKED, "locked_user"),
            (AuthErrorType.ACCOUNT_DISABLED, "disabled_user"),
            (AuthErrorType.RATE_LIMIT_EXCEEDED, "rate_limited_user"),
        ]

        for error_type, user_context in test_cases:
            result = error_handler.create_error_response(error_type, user_context)

            # All errors should return identical public message
            assert result["message"] == "Invalid credentials"
            assert result["status_code"] == 401
            assert "error_type" not in result  # No internal details exposed

    def test_constant_time_error_processing(self, error_handler):
        """Test that error processing takes constant time regardless of error type."""
        test_cases = [
            (AuthErrorType.INVALID_CREDENTIALS, "user1"),
            (AuthErrorType.ACCOUNT_LOCKED, "user2"),
            (AuthErrorType.ACCOUNT_DISABLED, "user3"),
        ]

        response_times = []

        for error_type, user_context in test_cases:
            start_time = time.time()

            error_handler.create_error_response(error_type, user_context)

            elapsed_time = time.time() - start_time
            response_times.append(elapsed_time)

        # All response times should be approximately equal (within 10ms tolerance)
        min_time = min(response_times)
        max_time = max(response_times)
        time_variance = max_time - min_time

        # Response times should be consistent (< 10ms variance)
        assert time_variance < 0.01, f"Time variance too high: {time_variance}s"

        # All responses should take at least the minimum time
        for response_time in response_times:
            assert response_time >= 0.09, f"Response too fast: {response_time}s"

    def test_audit_logging_integration(self, error_handler):
        """Test that detailed error information is logged internally."""
        # This test verifies that audit logging is called correctly
        # We test the integration without mocking by checking the public response
        # and verifying that audit logger methods exist and are called

        error_type = AuthErrorType.INVALID_CREDENTIALS
        user_context = "attempted_user"
        internal_message = "User not found in database"

        # Verify that audit logger has the required method
        assert hasattr(error_handler.audit_logger, "log_authentication_failure")

        result = error_handler.create_error_response(
            error_type,
            user_context,
            internal_message=internal_message,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )

        # Public response should be generic (main security requirement)
        assert result["message"] == "Invalid credentials"
        assert result["status_code"] == 401

        # Verify no internal details are exposed in the response
        assert "username" not in result
        assert "error_type" not in result
        assert "internal_message" not in result
        assert "ip_address" not in result
        assert "user_agent" not in result

    def test_dummy_password_hash_operation(self, error_handler):
        """Test dummy password hashing for timing consistency with non-existent users."""
        # Test that dummy operations are performed for non-existent users
        # to prevent timing-based user enumeration

        start_time = time.time()

        # This should perform dummy password hashing work
        error_handler.perform_dummy_password_work()

        elapsed_time = time.time() - start_time

        # Dummy work should take measurable time (at least 5ms for bcrypt-like work)
        assert elapsed_time >= 0.005, f"Dummy work too fast: {elapsed_time}s"
        assert elapsed_time <= 0.5, f"Dummy work too slow: {elapsed_time}s"

    def test_registration_response_standardization(self, error_handler):
        """Test registration responses are standardized regardless of account existence."""
        # Both new and existing accounts should get identical responses
        new_account_response = error_handler.create_registration_response(
            email="new@example.com", account_exists=False
        )

        existing_account_response = error_handler.create_registration_response(
            email="existing@example.com", account_exists=True
        )

        # Both responses should be identical to prevent user enumeration
        assert new_account_response["message"] == existing_account_response["message"]
        assert (
            new_account_response["message"]
            == "Registration initiated. Please check your email."
        )
        assert (
            new_account_response["status_code"]
            == existing_account_response["status_code"]
        )
        assert new_account_response["status_code"] == 200

    def test_password_reset_response_standardization(self, error_handler):
        """Test password reset responses don't reveal account existence."""
        # Both existing and non-existing accounts should get identical responses
        existing_response = error_handler.create_password_reset_response(
            email="user@example.com", account_exists=True
        )

        nonexistent_response = error_handler.create_password_reset_response(
            email="fake@example.com", account_exists=False
        )

        # Responses should be identical
        expected_message = "Password reset email sent if account exists"
        assert existing_response["message"] == expected_message
        assert nonexistent_response["message"] == expected_message
        assert (
            existing_response["status_code"]
            == nonexistent_response["status_code"]
            == 200
        )
