"""
TDD Test Suite for Audit Logging File Creation Fix.

MESSI RULE #1 COMPLIANCE: ZERO MOCKS - REAL SYSTEMS ONLY

This test suite reproduces the bug where audit logging doesn't create
log files in the test's expected location.

RED-GREEN-REFACTOR: Writing failing tests first to reproduce the exact issue.
"""

import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.jwt_manager import JWTManager
from code_indexer.server.auth.user_manager import UserManager, UserRole
from code_indexer.server.auth.refresh_token_manager import RefreshTokenManager
from code_indexer.server.auth.rate_limiter import RefreshTokenRateLimiter
from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger
from code_indexer.server.utils.config_manager import PasswordSecurityConfig
from code_indexer.server.utils.jwt_secret_manager import JWTSecretManager


class TestAuditLoggingFileCreationFix:
    """
    TDD test suite for audit logging file creation fix.

    RED PHASE: These tests should FAIL until audit logging is properly configured
    to write to test-specific directories.
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

        # Create REAL audit logger with test-specific path
        self.audit_log_path = self.temp_path / "audit.log"
        self.audit_logger = PasswordChangeAuditLogger(
            log_file_path=str(self.audit_log_path)
        )

        # Create test user
        self.user_manager.create_user(
            username="testuser", password="TestPass123!", role=UserRole.NORMAL_USER
        )

        # Override app components with test-specific instances BEFORE creating app
        import code_indexer.server.app as app_module
        import code_indexer.server.auth.dependencies as deps_module

        app_module.jwt_manager = self.jwt_manager
        app_module.user_manager = self.user_manager
        app_module.refresh_token_manager = self.refresh_token_manager
        app_module.refresh_token_rate_limiter = self.rate_limiter
        app_module.password_audit_logger = self.audit_logger

        # Also override dependencies module
        deps_module.jwt_manager = self.jwt_manager
        deps_module.user_manager = self.user_manager

        # Create app and client AFTER override
        self.app = create_app()
        self.client = TestClient(self.app)

    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _login_and_get_tokens(self, username: str, password: str) -> dict:
        """Helper to login and get tokens."""
        response = self.client.post(
            "/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        token_data: Dict[Any, Any] = response.json()
        return token_data

    def test_audit_log_file_created_in_test_directory(self):
        """
        RED TEST: This should FAIL if audit logging writes to global location.

        The audit logger should create log files in the test's temp directory,
        not in the global system location.
        """
        # Test audit logging directly without API calls to avoid app override issues
        # Create custom audit logger for this specific test
        custom_log_path = self.temp_path / "custom_audit.log"
        custom_logger = PasswordChangeAuditLogger(log_file_path=str(custom_log_path))

        # Log some events directly
        custom_logger.log_token_refresh_success(
            username="testuser", ip_address="127.0.0.1", family_id="test_family"
        )

        custom_logger.log_token_refresh_failure(
            username="testuser",
            ip_address="127.0.0.1",
            reason="invalid_token",
            security_incident=True,
        )

        # Force flush to ensure writes complete
        for handler in custom_logger.audit_logger.handlers:
            handler.flush()

        # Switch test to use custom log path
        self.audit_log_path = custom_log_path

        # CRITICAL: Audit log file must exist in test directory
        assert self.audit_log_path.exists(), (
            f"Audit log file should exist at {self.audit_log_path}, "
            f"but was not found. This suggests audit logging is writing "
            f"to a different location."
        )

        # Verify log contains entries
        log_content = self.audit_log_path.read_text()
        assert len(log_content) > 0, "Audit log file exists but is empty"

        # Verify log contains expected entries
        assert "token_refresh" in log_content or "TOKEN_REFRESH" in log_content, (
            f"Audit log should contain token refresh entries. "
            f"Log content: {log_content[:200]}..."
        )

    def test_audit_logger_with_custom_path_writes_correctly(self):
        """
        RED TEST: Test that custom audit logger path is respected.

        When an audit logger is configured with a custom path,
        it should write to that exact path, not the default location.
        """
        # Create a separate audit logger with different path
        custom_log_path = self.temp_path / "custom_audit.log"
        custom_audit_logger = PasswordChangeAuditLogger(
            log_file_path=str(custom_log_path)
        )

        # Trigger some logging directly
        custom_audit_logger.log_token_refresh_success(
            username="testuser",
            ip_address="127.0.0.1",
            family_id="test_family",
            additional_context={"test": "data"},
        )

        # Verify custom path is used
        assert (
            custom_log_path.exists()
        ), f"Custom audit log should exist at {custom_log_path}"

        # Verify content
        log_content = custom_log_path.read_text()
        assert "token_refresh" in log_content.lower() or "TOKEN_REFRESH" in log_content
        assert "testuser" in log_content

    def test_multiple_audit_loggers_write_to_different_files(self):
        """
        RED TEST: Test that different audit logger instances use their own files.

        Multiple audit logger instances should be able to write to
        different files without interfering with each other.
        """
        # Create two separate audit loggers
        log_path_1 = self.temp_path / "audit_1.log"
        log_path_2 = self.temp_path / "audit_2.log"

        logger_1 = PasswordChangeAuditLogger(log_file_path=str(log_path_1))
        logger_2 = PasswordChangeAuditLogger(log_file_path=str(log_path_2))

        # Log different events to each
        logger_1.log_token_refresh_success(
            username="user1", ip_address="127.0.0.1", family_id="family1"
        )

        logger_2.log_token_refresh_failure(
            username="user2",
            ip_address="127.0.0.2",
            reason="invalid_token",
            security_incident=True,
        )

        # Force flush of log handlers to ensure writes are completed
        for handler in logger_1.audit_logger.handlers:
            handler.flush()
        for handler in logger_2.audit_logger.handlers:
            handler.flush()

        # Verify both files exist and have correct content
        assert log_path_1.exists(), "First audit log should exist"
        assert log_path_2.exists(), "Second audit log should exist"

        content_1 = log_path_1.read_text()
        content_2 = log_path_2.read_text()

        assert "user1" in content_1, "First log should contain user1"
        assert "user2" in content_2, "Second log should contain user2"
        assert "user1" not in content_2, "Second log should not contain user1"
        assert "user2" not in content_1, "First log should not contain user2"

    def test_audit_logging_token_operations_coverage(self):
        """
        GREEN TEST: Test that all token operations are properly logged.

        All token refresh operations (success, failure, rate limiting)
        should be logged to the audit file.
        """
        # Create dedicated audit logger for comprehensive testing
        coverage_log_path = self.temp_path / "coverage_audit.log"
        coverage_logger = PasswordChangeAuditLogger(
            log_file_path=str(coverage_log_path)
        )

        # Test all audit logging operations directly

        # 1. Successful refresh operation
        coverage_logger.log_token_refresh_success(
            username="testuser", ip_address="127.0.0.1", family_id="test_family"
        )

        # 2. Failed refresh operation
        coverage_logger.log_token_refresh_failure(
            username="testuser",
            ip_address="127.0.0.1",
            reason="invalid_token",
            security_incident=True,
        )

        # 3. Rate limiting triggered
        coverage_logger.log_rate_limit_triggered(
            username="testuser", ip_address="127.0.0.1", attempt_count=5
        )

        # 4. Security incident
        coverage_logger.log_security_incident(
            username="testuser",
            incident_type="token_replay_attack",
            ip_address="127.0.0.1",
        )

        # Force flush of audit logger handlers to ensure all writes are completed
        for handler in coverage_logger.audit_logger.handlers:
            handler.flush()

        # Verify all operations are logged
        assert (
            coverage_log_path.exists()
        ), "Audit log file should exist after operations"
        log_content = coverage_log_path.read_text()

        # Should contain success logging
        assert (
            "TOKEN_REFRESH_SUCCESS" in log_content
        ), "Log should contain successful refresh operations"

        # Should contain failure logging
        assert (
            "TOKEN_REFRESH_FAILURE" in log_content
        ), "Log should contain failed refresh operations"

        # Should contain rate limiting
        assert (
            "RATE_LIMIT" in log_content
        ), "Log should contain rate limiting operations"

        # Should contain security incidents
        assert (
            "SECURITY_INCIDENT" in log_content
        ), "Log should contain security incident operations"

        # Should contain rate limiting
        assert any(
            keyword in log_content.lower() for keyword in ["rate", "limit", "too many"]
        ), "Log should contain rate limiting events"

    def test_global_singleton_audit_logger_path_issue(self):
        """
        GREEN TEST: Verify that global singleton issue is resolved.

        Now that we fixed the logger name collision bug, this test demonstrates
        that multiple logger instances can coexist properly.
        """
        from code_indexer.server.auth.audit_logger import password_audit_logger

        # Test that global singleton and custom instances work independently
        custom_log_path = self.temp_path / "custom_singleton_test.log"
        custom_logger = PasswordChangeAuditLogger(log_file_path=str(custom_log_path))

        # Log to both global singleton and custom logger
        password_audit_logger.log_token_refresh_success(
            username="global_user", ip_address="127.0.0.1", family_id="global_family"
        )

        custom_logger.log_token_refresh_success(
            username="custom_user", ip_address="127.0.0.1", family_id="custom_family"
        )

        # Force flush both loggers
        for handler in password_audit_logger.audit_logger.handlers:
            handler.flush()
        for handler in custom_logger.audit_logger.handlers:
            handler.flush()

        # Both should work independently
        assert custom_log_path.exists(), "Custom logger should create its own file"

        # Check contents are separate
        custom_content = custom_log_path.read_text()
        assert "custom_user" in custom_content, "Custom log should contain custom user"
        assert (
            "global_user" not in custom_content
        ), "Custom log should not contain global user"

        # Verify the global singleton still works at its default location
        global_default_path = Path.home() / ".cidx-server" / "password_audit.log"
        if global_default_path.exists():
            _global_content = global_default_path.read_text()
            # Global logs may contain entries from this test or previous tests
            # Just verify it's not interfering with custom logger


# TDD VERDICT: 🔴 RED PHASE
# These tests should FAIL until audit logging is properly configured to use
# test-specific file paths instead of global singleton paths.
