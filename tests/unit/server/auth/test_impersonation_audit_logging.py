"""
Unit tests for impersonation audit logging.

Story #722: Tests for audit logging of impersonation operations:
- IMPERSONATION_SET: Admin X began impersonating user Y
- IMPERSONATION_CLEARED: Admin X stopped impersonating user Y
- IMPERSONATION_DENIED: User X (non-admin) attempted impersonation
"""

import json
import tempfile
import os


class TestImpersonationSetAuditLogging:
    """Test log_impersonation_set audit events."""

    def setup_method(self):
        """Set up test fixtures with temporary log file."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "password_audit.log")

    def teardown_method(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_impersonation_set_creates_entry(self):
        """Test that setting impersonation creates an audit log entry."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_set(
            actor_username="admin_user",
            target_username="sales_user",
            session_id="session-123",
            ip_address="192.168.1.100",
            user_agent="Claude-MCP-Client/1.0",
        )

        with open(self.log_file, "r") as f:
            log_content = f.read()

        assert "IMPERSONATION_SET" in log_content
        assert "admin_user" in log_content
        assert "sales_user" in log_content
        assert "session-123" in log_content
        assert "192.168.1.100" in log_content

    def test_log_impersonation_set_entry_format(self):
        """Test that impersonation_set log entry has correct JSON structure."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_set(
            actor_username="admin_user",
            target_username="target_user",
            session_id="session-456",
            ip_address="10.0.0.1",
            user_agent="Test-Agent/1.0",
            additional_context={"reason": "support investigation"},
        )

        with open(self.log_file, "r") as f:
            log_line = f.read()

        json_start = log_line.index("{")
        json_str = log_line[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "impersonation_set"
        assert log_entry["actor_username"] == "admin_user"
        assert log_entry["target_username"] == "target_user"
        assert log_entry["session_id"] == "session-456"
        assert log_entry["ip_address"] == "10.0.0.1"
        assert log_entry["user_agent"] == "Test-Agent/1.0"
        assert log_entry["additional_context"]["reason"] == "support investigation"
        assert "timestamp" in log_entry


class TestImpersonationClearedAuditLogging:
    """Test log_impersonation_cleared audit events."""

    def setup_method(self):
        """Set up test fixtures with temporary log file."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "password_audit.log")

    def teardown_method(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_impersonation_cleared_creates_entry(self):
        """Test that clearing impersonation creates an audit log entry."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_cleared(
            actor_username="admin_user",
            previous_target="sales_user",
            session_id="session-123",
            ip_address="192.168.1.100",
        )

        with open(self.log_file, "r") as f:
            log_content = f.read()

        assert "IMPERSONATION_CLEARED" in log_content
        assert "admin_user" in log_content
        assert "sales_user" in log_content
        assert "session-123" in log_content

    def test_log_impersonation_cleared_entry_format(self):
        """Test that impersonation_cleared log entry has correct JSON structure."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_cleared(
            actor_username="admin_user",
            previous_target="target_user",
            session_id="session-789",
            ip_address="10.0.0.2",
            user_agent="Test-Agent/1.0",
        )

        with open(self.log_file, "r") as f:
            log_line = f.read()

        json_start = log_line.index("{")
        json_str = log_line[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "impersonation_cleared"
        assert log_entry["actor_username"] == "admin_user"
        assert log_entry["previous_target"] == "target_user"
        assert log_entry["session_id"] == "session-789"
        assert "timestamp" in log_entry


class TestImpersonationDeniedAuditLogging:
    """Test log_impersonation_denied audit events."""

    def setup_method(self):
        """Set up test fixtures with temporary log file."""
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "password_audit.log")

    def teardown_method(self):
        """Clean up temporary files."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_log_impersonation_denied_creates_entry(self):
        """Test that denied impersonation attempts create an audit log entry."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_denied(
            actor_username="power_user",
            target_username="admin_user",
            reason="Impersonation requires ADMIN role",
            session_id="session-123",
            ip_address="192.168.1.100",
        )

        with open(self.log_file, "r") as f:
            log_content = f.read()

        assert "IMPERSONATION_DENIED" in log_content
        assert "power_user" in log_content
        assert "admin_user" in log_content
        assert "ADMIN role" in log_content
        assert "WARNING" in log_content  # Should be WARNING level

    def test_log_impersonation_denied_entry_format(self):
        """Test that impersonation_denied log entry has correct JSON structure."""
        from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger

        logger = PasswordChangeAuditLogger(log_file_path=self.log_file)

        logger.log_impersonation_denied(
            actor_username="normal_user",
            target_username="sales_user",
            reason="Impersonation requires ADMIN role",
            session_id="session-999",
            ip_address="192.168.0.50",
            user_agent="Test-Client/2.0",
        )

        with open(self.log_file, "r") as f:
            log_line = f.read()

        json_start = log_line.index("{")
        json_str = log_line[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "impersonation_denied"
        assert log_entry["actor_username"] == "normal_user"
        assert log_entry["target_username"] == "sales_user"
        assert log_entry["reason"] == "Impersonation requires ADMIN role"
        assert log_entry["session_id"] == "session-999"
        assert "timestamp" in log_entry
