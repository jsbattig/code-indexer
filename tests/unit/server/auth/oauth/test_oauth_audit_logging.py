"""
Test OAuth audit logging functionality with real file I/O.

Following TDD: Write failing tests FIRST, then implement features.
Following CLAUDE.md: Zero mocking - real audit logging, real file operations.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path

from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger


class TestOAuthAuditLogging:
    """Test OAuth-specific audit logging methods."""

    @pytest.fixture
    def temp_audit_log(self):
        """Create temporary audit log file for testing."""
        temp_dir = Path(tempfile.mkdtemp())
        log_file = temp_dir / "oauth_audit.log"
        yield str(log_file)
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def audit_logger(self, temp_audit_log):
        """Create audit logger instance with temporary log file."""
        return PasswordChangeAuditLogger(log_file_path=temp_audit_log)

    def _read_audit_entries(self, log_file_path: str) -> list:
        """Read and parse audit log entries from file."""
        log_path = Path(log_file_path)
        if not log_path.exists():
            return []

        entries = []
        with open(log_path, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        # Log format: "timestamp - level - EVENT_TYPE: {json}"
                        parts = line.strip().split(" - ", 2)
                        if len(parts) >= 3:
                            json_part = parts[2]
                            if ": {" in json_part:
                                json_str = json_part.split(": ", 1)[1]
                                entries.append(json.loads(json_str))
                    except (json.JSONDecodeError, IndexError):
                        continue
        return entries

    def test_log_oauth_client_registration_creates_audit_entry(
        self, audit_logger, temp_audit_log
    ):
        """
        RED: Test that OAuth client registration is audit logged.

        Expected behavior:
        - Audit logger should have log_oauth_client_registration() method
        - Method should log: client_id, client_name, ip_address, user_agent
        - Log entry should be written to real file with proper JSON structure
        """
        # Call method that doesn't exist yet (RED)
        audit_logger.log_oauth_client_registration(
            client_id="test_client_123",
            client_name="Test OAuth Client",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        # Verify audit entry was written
        entries = self._read_audit_entries(temp_audit_log)
        assert len(entries) == 1

        entry = entries[0]
        assert entry["event_type"] == "oauth_client_registration"
        assert entry["client_id"] == "test_client_123"
        assert entry["client_name"] == "Test OAuth Client"
        assert entry["ip_address"] == "192.168.1.100"
        assert entry["user_agent"] == "Mozilla/5.0"
        assert "timestamp" in entry

    def test_log_oauth_authorization_creates_audit_entry(
        self, audit_logger, temp_audit_log
    ):
        """
        RED: Test that OAuth authorization is audit logged.

        Expected behavior:
        - Audit logger should have log_oauth_authorization() method
        - Method should log: username, client_id, ip_address, user_agent
        """
        audit_logger.log_oauth_authorization(
            username="testuser",
            client_id="test_client_123",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        entries = self._read_audit_entries(temp_audit_log)
        assert len(entries) == 1

        entry = entries[0]
        assert entry["event_type"] == "oauth_authorization"
        assert entry["username"] == "testuser"
        assert entry["client_id"] == "test_client_123"
        assert entry["ip_address"] == "192.168.1.100"

    def test_log_oauth_token_exchange_creates_audit_entry(
        self, audit_logger, temp_audit_log
    ):
        """RED: Test that OAuth token exchange is audit logged."""
        audit_logger.log_oauth_token_exchange(
            username="testuser",
            client_id="test_client_123",
            grant_type="authorization_code",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        entries = self._read_audit_entries(temp_audit_log)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "oauth_token_exchange"
        assert entry["username"] == "testuser"
        assert entry["client_id"] == "test_client_123"
        assert entry["grant_type"] == "authorization_code"

    def test_log_oauth_token_revocation_creates_audit_entry(
        self, audit_logger, temp_audit_log
    ):
        """RED: Test that OAuth token revocation is audit logged."""
        audit_logger.log_oauth_token_revocation(
            username="testuser",
            token_type="access_token",
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )

        entries = self._read_audit_entries(temp_audit_log)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event_type"] == "oauth_token_revocation"
        assert entry["username"] == "testuser"
        assert entry["token_type"] == "access_token"
        assert entry["ip_address"] == "192.168.1.100"
