"""
TDD Test Suite for Rate Limiting 500 Error Fix.

MESSI RULE #1 COMPLIANCE: ZERO MOCKS - REAL SYSTEMS ONLY

This test suite reproduces the bug where rate limiting with invalid tokens
causes 500 Internal Server Error instead of proper 401 Unauthorized.

RED-GREEN-REFACTOR: Writing failing tests first to reproduce the exact issue.
"""

import tempfile
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.refresh_token_manager import RefreshTokenManager
from code_indexer.server.auth.rate_limiter import RefreshTokenRateLimiter
from code_indexer.server.auth.audit_logger import password_audit_logger
from code_indexer.server.utils.config_manager import PasswordSecurityConfig
from code_indexer.server.utils.jwt_secret_manager import JWTSecretManager


import pytest


@pytest.mark.e2e
class TestRateLimiting500ErrorFix:
    """
    TDD test suite for rate limiting 500 error fix.

    RED PHASE: These tests should FAIL until the username extraction bug is fixed.
    """

    def setup_method(self):
        """Set up real test environment with actual components."""
        # Create temporary directory for test data
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Initialize REAL components
        self.jwt_secret_manager = JWTSecretManager(
            str(self.temp_path / "jwt_secret.key")
        )
        self.jwt_manager = JWTManager(
            secret_key=self.jwt_secret_manager.get_or_create_secret(),
            algorithm="HS256",
            token_expiration_minutes=15,
        )

        # Create REAL user manager with weak password config for testing
        self.users_file_path = self.temp_path / "users.json"
        weak_password_config = PasswordSecurityConfig(
            min_length=1,
            max_length=128,
            required_char_classes=0,
            min_entropy_bits=0,
            check_common_passwords=False,
            check_personal_info=False,
            check_keyboard_patterns=False,
            check_sequential_chars=False,
        )
        self.user_manager = UserManager(
            users_file_path=str(self.users_file_path),
            password_security_config=weak_password_config,
        )

        # Create REAL refresh token manager
        self.refresh_db_path = self.temp_path / "refresh_tokens.db"
        self.refresh_token_manager = RefreshTokenManager(
            jwt_manager=self.jwt_manager,
            db_path=str(self.refresh_db_path),
            refresh_token_lifetime_days=7,
        )

        # Create REAL rate limiter
        self.rate_limiter = RefreshTokenRateLimiter()

        # Create test user
        self.user_manager.create_user(
            username="testuser", password="TestPass123!", role=UserRole.NORMAL_USER
        )

        # Create app and inject REAL components
        self.app = create_app()
        self.client = TestClient(self.app)

        # Override app components
        import code_indexer.server.app as app_module

        app_module.jwt_manager = self.jwt_manager
        app_module.user_manager = self.user_manager
        app_module.refresh_token_manager = self.refresh_token_manager
        app_module.refresh_token_rate_limiter = self.rate_limiter
        app_module.password_audit_logger = password_audit_logger

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_invalid_token_rate_limiting_returns_401_not_500(self):
        """
        RED TEST: This should FAIL showing 500 error instead of 401.

        When rate limiting with completely invalid tokens, the system should
        return 401 Unauthorized, not 500 Internal Server Error.
        """
        # Attempt multiple refreshes with invalid tokens to trigger rate limiting
        for i in range(10):  # RefreshTokenRateLimiter allows 10 attempts
            response = self.client.post(
                "/api/auth/refresh",
                json={"refresh_token": f"completely_invalid_token_{i}"},
            )
            # Should get 401 for invalid token, NOT 500
            assert response.status_code == 401, (
                f"Attempt {i+1}: Expected 401 Unauthorized for invalid token, "
                f"got {response.status_code} with response: {response.text}"
            )

        # 11th attempt should still be 401 or 429, never 500
        response = self.client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid_token_attempt_11"}
        )

        # Should get either 401 or 429, but NEVER 500
        assert response.status_code in [401, 429], (
            f"Rate limited request should return 401 or 429, not {response.status_code}. "
            f"Response: {response.text}"
        )

    def test_malformed_token_rate_limiting_returns_401_not_500(self):
        """
        RED TEST: Test with malformed tokens that might cause extraction errors.

        Various types of malformed tokens should all result in 401, not 500.
        """
        malformed_tokens = [
            "",  # Empty token
            "not_a_jwt_token_at_all",  # Non-JWT format
            "header.payload.signature.extra",  # Too many parts
            "onlyonepart",  # Too few parts
            "äöü.special.chars",  # Non-ASCII characters
            "a" * 1000,  # Very long token
            None,  # This would cause JSON error, but test framework handles it
        ]

        for token in malformed_tokens:
            if token is None:
                continue  # Skip None as it would cause request validation error

            response = self.client.post(
                "/api/auth/refresh", json={"refresh_token": token}
            )

            # Should get 401 or 422 (validation error), but NEVER 500
            assert response.status_code in [401, 422], (
                f"Malformed token '{token}' should return 401 or 422, "
                f"got {response.status_code} with response: {response.text}"
            )

    def test_rate_limiter_username_extraction_from_invalid_tokens(self):
        """
        RED TEST: Test specific username extraction issue.

        The rate limiter should handle cases where username cannot be extracted
        from invalid tokens without causing 500 errors.
        """
        # Use completely invalid token that would fail username extraction
        invalid_token = "definitely_not_a_valid_refresh_token_12345"

        # Try multiple times to trigger potential username extraction error
        for i in range(3):
            response = self.client.post(
                "/api/auth/refresh", json={"refresh_token": invalid_token}
            )

            # Each attempt should return 401, not 500
            assert response.status_code == 401, (
                f"Attempt {i+1} with invalid token should return 401, "
                f"got {response.status_code}. This suggests username extraction "
                f"is failing and causing 500 error. Response: {response.text}"
            )

    def test_empty_and_whitespace_tokens_handled_properly(self):
        """
        RED TEST: Test edge cases that might cause extraction errors.

        Edge case tokens should be handled gracefully with 401 or 422 responses.
        """
        edge_case_tokens = [
            "",  # Empty string
            " ",  # Single space
            "   ",  # Multiple spaces
            "\t",  # Tab
            "\n",  # Newline
            "null",  # String "null"
            "undefined",  # String "undefined"
        ]

        for token in edge_case_tokens:
            response = self.client.post(
                "/api/auth/refresh", json={"refresh_token": token}
            )

            # Should get 401 or 422, but NEVER 500
            assert response.status_code in [401, 422], (
                f"Edge case token '{repr(token)}' should return 401 or 422, "
                f"got {response.status_code} with response: {response.text}"
            )


# TDD VERDICT: 🔴 RED PHASE
# These tests should FAIL until the rate limiting username extraction is fixed.
# The bug is likely in the refresh endpoint where it tries to extract username
# from invalid token results for rate limiting purposes.
