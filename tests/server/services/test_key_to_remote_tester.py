"""Unit tests for KeyToRemoteTester service."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from code_indexer.server.services.key_to_remote_tester import (
    KeyToRemoteTester,
    TestResult,
)


class TestKeyToRemoteTesterTestResult:
    """Tests for TestResult dataclass."""

    def test_test_result_success(self):
        """Should create successful test result."""
        result = TestResult(success=True, message="Successfully authenticated")

        assert result.success is True
        assert "authenticated" in result.message.lower()
        assert result.timed_out is False

    def test_test_result_failure(self):
        """Should create failed test result."""
        result = TestResult(success=False, message="Permission denied")

        assert result.success is False
        assert result.timed_out is False

    def test_test_result_timeout(self):
        """Should indicate timeout."""
        result = TestResult(success=False, message="Connection timed out", timed_out=True)

        assert result.success is False
        assert result.timed_out is True


class TestKeyToRemoteTesterParseOutput:
    """Tests for KeyToRemoteTester output parsing."""

    def test_parse_github_success_message(self):
        """Should recognize GitHub success message."""
        tester = KeyToRemoteTester()

        # GitHub returns: "Hi username! You've successfully authenticated..."
        result = tester._parse_ssh_output(
            exit_code=1,  # GitHub returns 1 even on success
            stdout="",
            stderr="Hi testuser! You've successfully authenticated, but GitHub does not provide shell access."
        )

        assert result.success is True

    def test_parse_gitlab_success_message(self):
        """Should recognize GitLab success message."""
        tester = KeyToRemoteTester()

        # GitLab returns: "Welcome to GitLab, @username!"
        result = tester._parse_ssh_output(
            exit_code=0,
            stdout="Welcome to GitLab, @testuser!",
            stderr=""
        )

        assert result.success is True

    def test_parse_permission_denied(self):
        """Should recognize permission denied."""
        tester = KeyToRemoteTester()

        result = tester._parse_ssh_output(
            exit_code=255,
            stdout="",
            stderr="Permission denied (publickey)."
        )

        assert result.success is False
        assert "permission denied" in result.message.lower()

    def test_parse_generic_success(self):
        """Should recognize generic success message."""
        tester = KeyToRemoteTester()

        result = tester._parse_ssh_output(
            exit_code=0,
            stdout="successfully authenticated",
            stderr=""
        )

        assert result.success is True


class TestKeyToRemoteTesterIntegration:
    """Integration tests for KeyToRemoteTester (mocked subprocess)."""

    def test_test_key_against_host_success(self, tmp_path):
        """Should return success when SSH auth succeeds."""
        # Create a mock key file
        key_path = tmp_path / "test_key"
        key_path.write_text("MOCK PRIVATE KEY")

        tester = KeyToRemoteTester(timeout_seconds=5)

        # Mock subprocess to return GitHub-style success
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Hi testuser! You've successfully authenticated"
            )

            result = tester.test_key_against_host(key_path, "github.com")

            assert result.success is True
            mock_run.assert_called_once()

    def test_test_key_against_host_permission_denied(self, tmp_path):
        """Should return failure when permission denied."""
        key_path = tmp_path / "test_key"
        key_path.write_text("MOCK PRIVATE KEY")

        tester = KeyToRemoteTester(timeout_seconds=5)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=255,
                stdout="",
                stderr="Permission denied (publickey)."
            )

            result = tester.test_key_against_host(key_path, "github.com")

            assert result.success is False

    def test_test_key_against_host_timeout(self, tmp_path):
        """Should handle timeout gracefully."""
        key_path = tmp_path / "test_key"
        key_path.write_text("MOCK PRIVATE KEY")

        tester = KeyToRemoteTester(timeout_seconds=5)

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=5)

            result = tester.test_key_against_host(key_path, "github.com")

            assert result.success is False
            assert result.timed_out is True

    def test_test_key_against_multiple_hosts(self, tmp_path):
        """Should test key against multiple hosts."""
        key_path = tmp_path / "test_key"
        key_path.write_text("MOCK PRIVATE KEY")

        tester = KeyToRemoteTester(timeout_seconds=5)

        with patch("subprocess.run") as mock_run:
            # First call succeeds (github), second fails (gitlab)
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="Hi user! You've successfully authenticated"),
                MagicMock(returncode=255, stdout="", stderr="Permission denied"),
            ]

            results = tester.test_key_against_multiple_hosts(
                key_path,
                ["github.com", "gitlab.com"]
            )

            assert len(results) == 2
            assert results["github.com"].success is True
            assert results["gitlab.com"].success is False
