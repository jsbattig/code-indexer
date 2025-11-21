"""
Real Audit Logging Test Suite - Foundation #1 Compliant.

Tests audit logging functionality using real file system operations.
No mocks for audit logging - tests real log file creation and content.
"""

import pytest
import json

from code_indexer.server.auth.user_manager import UserRole
from tests.fixtures.test_infrastructure import RealComponentTestInfrastructure


@pytest.mark.e2e
class TestRealAuditLogging:
    """Test audit logging with real file system operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment with real audit logging using working infrastructure."""
        # Use working infrastructure instead of broken StandardTestAuth
        self.infrastructure = RealComponentTestInfrastructure()
        self.infrastructure.setup()

        # Get client and app from infrastructure
        self.client = self.infrastructure.client
        self.app = self.infrastructure.app

        # Create test user using working approach
        self.test_user_data = self.infrastructure.create_test_user(
            "audit_test_user", "TestPass123!", UserRole.NORMAL_USER
        )
        self.test_username = self.test_user_data["username"]

        # Audit logs will be in the infrastructure temp directory
        self.audit_log_path = (
            self.infrastructure.temp_dir / "audit" / "password_changes.log"
        )

        # Ensure audit directory exists
        self.audit_log_path.parent.mkdir(exist_ok=True)

        yield

        # Cleanup using infrastructure cleanup
        self.infrastructure.cleanup()

    def _get_auth_headers(self):
        """Get valid authentication headers using working infrastructure."""
        token_data = self.infrastructure.get_auth_token(
            self.test_username, "TestPass123!"
        )
        return self.infrastructure.authenticate_request(token_data["access_token"])

    def _read_audit_log(self):
        """Read and parse audit log entries."""
        if not self.audit_log_path.exists():
            return []

        entries = []
        with open(self.audit_log_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        # Log format: "timestamp - level - message"
                        # The message part contains the JSON
                        parts = line.strip().split(" - ", 2)
                        if len(parts) >= 3:
                            json_part = parts[2]
                            # Extract JSON from message (after "EVENT_TYPE: ")
                            if ": {" in json_part:
                                json_str = json_part.split(": ", 1)[1]
                                entries.append(json.loads(json_str))
                    except (json.JSONDecodeError, IndexError):
                        continue
        return entries

    def test_failed_password_change_audit_logging_real(self):
        """
        GREEN: Test real audit logging for failed password changes.

        This test uses real audit logging with real file operations,
        replacing the broken mock-based test.
        """
        headers = self._get_auth_headers()

        # Make failed password change attempt
        response = self.client.put(
            "/api/users/change-password",
            headers=headers,
            json={
                "old_password": "wrong_password",
                "new_password": "NewSecure123!Pass",
            },
        )

        # Should fail with 401
        assert response.status_code == 401

        # Check real audit log file
        audit_entries = self._read_audit_log()

        # Should have at least one entry
        assert len(audit_entries) > 0

        # Find password change failure entry
        failure_entries = [
            entry
            for entry in audit_entries
            if entry.get("event_type") == "password_change_failure"
        ]

        assert len(failure_entries) >= 1
        failure_entry = failure_entries[-1]  # Get most recent

        # Verify entry content
        assert failure_entry["username"] == "audit_test_user"
        assert failure_entry["reason"] == "Invalid old password"
        assert "timestamp" in failure_entry
        assert "ip_address" in failure_entry

        print(f"✅ Real audit logging captured: {failure_entry}")

    def test_successful_password_change_audit_logging_real(self):
        """
        GREEN: Test real audit logging for successful password changes.
        """
        headers = self._get_auth_headers()

        # Make successful password change attempt
        response = self.client.put(
            "/api/users/change-password",
            headers=headers,
            json={
                "old_password": "TestPass123!",
                "new_password": "NewSecure456!Pass",
            },
        )

        # Should succeed
        assert response.status_code == 200

        # Check real audit log file
        audit_entries = self._read_audit_log()

        # Find password change success entry
        success_entries = [
            entry
            for entry in audit_entries
            if entry.get("event_type") == "password_change_success"
        ]

        assert len(success_entries) >= 1
        success_entry = success_entries[-1]  # Get most recent

        # Verify entry content
        assert success_entry["username"] == "audit_test_user"
        assert "timestamp" in success_entry
        assert "ip_address" in success_entry

        print(f"✅ Real audit logging captured: {success_entry}")

    def test_rate_limit_trigger_audit_logging_real(self):
        """
        GREEN: Test real audit logging for rate limit triggers.
        """
        headers = self._get_auth_headers()

        # Exhaust rate limiter (5 failed attempts)
        for i in range(5):
            response = self.client.put(
                "/api/users/change-password",
                headers=headers,
                json={
                    "old_password": f"wrong_password_{i}",
                    "new_password": "NewSecure123!Pass",
                },
            )
            if i < 4:
                assert response.status_code == 401
            else:
                assert response.status_code == 429  # Rate limited

        # Check real audit log file
        audit_entries = self._read_audit_log()

        # Find rate limit trigger entry
        rate_limit_entries = [
            entry
            for entry in audit_entries
            if entry.get("event_type") == "password_change_rate_limit"
        ]

        assert len(rate_limit_entries) >= 1
        rate_limit_entry = rate_limit_entries[-1]

        # Verify entry content
        assert rate_limit_entry["username"] == "audit_test_user"
        assert rate_limit_entry["attempt_count"] >= 5
        assert "timestamp" in rate_limit_entry

        print(f"✅ Real rate limit audit logging: {rate_limit_entry}")

    def test_refresh_token_audit_logging_real(self):
        """
        GREEN: Test real audit logging for refresh token operations.
        """
        # Get initial tokens using working infrastructure
        tokens = self.infrastructure.get_auth_token(self.test_username, "TestPass123!")

        # Use refresh token
        refresh_response = self.client.post(
            "/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refresh_response.status_code == 200

        # Check real audit log file
        audit_entries = self._read_audit_log()

        # Find refresh success entry
        refresh_entries = [
            entry
            for entry in audit_entries
            if entry.get("event_type") == "token_refresh_success"
        ]

        assert len(refresh_entries) >= 1
        refresh_entry = refresh_entries[-1]

        # Verify entry content
        assert refresh_entry["username"] == "audit_test_user"
        assert "family_id" in refresh_entry
        assert "timestamp" in refresh_entry

        print(f"✅ Real refresh token audit logging: {refresh_entry}")

    def test_invalid_refresh_token_audit_logging_real(self):
        """
        GREEN: Test real audit logging for invalid refresh token attempts.
        """
        # Try invalid refresh token
        response = self.client.post(
            "/api/auth/refresh", json={"refresh_token": "invalid_token_12345"}
        )
        assert response.status_code == 401

        # Check real audit log file
        audit_entries = self._read_audit_log()

        # Find refresh failure entry
        failure_entries = [
            entry
            for entry in audit_entries
            if entry.get("event_type") == "token_refresh_failure"
        ]

        assert len(failure_entries) >= 1
        failure_entry = failure_entries[-1]

        # Verify entry content
        assert "Invalid refresh token" in failure_entry["reason"]
        assert "timestamp" in failure_entry

        print(f"✅ Real refresh failure audit logging: {failure_entry}")


@pytest.mark.e2e
class TestAuditLoggerIntegrationFix:
    """Fix for tests that incorrectly reference audit_logger."""

    def test_password_audit_logger_exists_in_app_module(self):
        """
        Verify that password_audit_logger is correctly imported in app module.

        This test documents the correct import name for future test writers.
        """
        import code_indexer.server.app as app_module

        # The correct attribute name
        assert hasattr(app_module, "password_audit_logger")

        # The incorrect attribute name that tests were trying to use
        assert not hasattr(app_module, "audit_logger")

        # Verify it's the right type
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        assert isinstance(app_module.password_audit_logger, PasswordChangeAuditLogger)

    def test_audit_logging_methods_available(self):
        """Verify audit logger has expected methods."""
        import code_indexer.server.app as app_module

        audit_logger = app_module.password_audit_logger

        # Check expected methods exist
        assert hasattr(audit_logger, "log_password_change_success")
        assert hasattr(audit_logger, "log_password_change_failure")
        assert hasattr(audit_logger, "log_token_refresh_success")
        assert hasattr(audit_logger, "log_token_refresh_failure")
        assert hasattr(audit_logger, "log_rate_limit_triggered")

        print("✅ All expected audit logging methods are available")
