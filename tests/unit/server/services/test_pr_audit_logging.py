"""
Unit tests for PR creation audit logging.

Tests audit logging for PR creation workflow:
- Success logging with all metadata
- Failure logging with error details
- Log format validation

Story #659: Git State Management for SCIP Self-Healing with PR Workflow
AC7: Audit Logging
"""

import json
from pathlib import Path
from unittest.mock import Mock, patch


from code_indexer.server.auth.audit_logger import PasswordChangeAuditLogger


class TestPRCreationAuditLogging:
    """Tests for PR creation audit logging (AC7)."""

    def test_log_pr_creation_success(self, tmp_path):
        """AC7: Log successful PR creation with all required fields."""
        # ARRANGE
        audit_log_file = tmp_path / "pr_audit.log"
        logger = PasswordChangeAuditLogger(log_file_path=str(audit_log_file))

        # ACT
        logger.log_pr_creation_success(
            job_id="scip-fix-12345",
            repo_alias="my-repo",
            branch_name="scip-fix-20260101-123456",
            pr_url="https://github.com/owner/repo/pull/123",
            commit_hash="abc123def456",
            files_modified=["src/auth.py", "src/utils.py"],
        )

        # ASSERT
        assert audit_log_file.exists()
        log_content = audit_log_file.read_text()

        # Verify log entry contains all required fields
        assert "PR_CREATION_SUCCESS" in log_content
        assert "scip-fix-12345" in log_content
        assert "my-repo" in log_content
        assert "scip-fix-20260101-123456" in log_content
        assert "https://github.com/owner/repo/pull/123" in log_content
        assert "abc123def456" in log_content
        assert "src/auth.py" in log_content
        assert "src/utils.py" in log_content

        # Verify JSON structure
        json_start = log_content.index("{")
        json_str = log_content[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "pr_creation_success"
        assert log_entry["job_id"] == "scip-fix-12345"
        assert log_entry["repo_alias"] == "my-repo"
        assert log_entry["branch_name"] == "scip-fix-20260101-123456"
        assert log_entry["pr_url"] == "https://github.com/owner/repo/pull/123"
        assert log_entry["commit_hash"] == "abc123def456"
        assert "timestamp" in log_entry
        assert len(log_entry["files_modified"]) == 2

    def test_log_pr_creation_failure(self, tmp_path):
        """AC7: Log failed PR creation with error details."""
        # ARRANGE
        audit_log_file = tmp_path / "pr_audit.log"
        logger = PasswordChangeAuditLogger(log_file_path=str(audit_log_file))

        # ACT
        logger.log_pr_creation_failure(
            job_id="scip-fix-67890",
            repo_alias="failed-repo",
            reason="git push failed: Permission denied",
            branch_name="scip-fix-20260101-234567",
        )

        # ASSERT
        assert audit_log_file.exists()
        log_content = audit_log_file.read_text()

        # Verify log entry contains failure information
        assert "PR_CREATION_FAILURE" in log_content
        assert "scip-fix-67890" in log_content
        assert "failed-repo" in log_content
        assert "Permission denied" in log_content
        assert "scip-fix-20260101-234567" in log_content

        # Verify JSON structure
        json_start = log_content.index("{")
        json_str = log_content[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "pr_creation_failure"
        assert log_entry["reason"] == "git push failed: Permission denied"

    def test_log_pr_creation_disabled(self, tmp_path):
        """AC7: Log when PR creation is disabled in configuration."""
        # ARRANGE
        audit_log_file = tmp_path / "pr_audit.log"
        logger = PasswordChangeAuditLogger(log_file_path=str(audit_log_file))

        # ACT
        logger.log_pr_creation_disabled(
            job_id="scip-fix-99999",
            repo_alias="disabled-repo",
        )

        # ASSERT
        assert audit_log_file.exists()
        log_content = audit_log_file.read_text()

        # Verify log entry
        assert "PR_CREATION_DISABLED" in log_content
        assert "scip-fix-99999" in log_content
        assert "disabled-repo" in log_content

        # Verify JSON structure
        json_start = log_content.index("{")
        json_str = log_content[json_start:]
        log_entry = json.loads(json_str)

        assert log_entry["event_type"] == "pr_creation_disabled"

    def test_git_state_manager_calls_audit_logger_on_success(self, tmp_path):
        """AC7: GitStateManager calls audit logger on successful PR creation."""
        # ARRANGE
        from code_indexer.server.services.git_state_manager import GitStateManager

        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        # Mock audit logger
        mock_audit_logger = Mock()

        with (
            patch(
                "code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "code_indexer.server.services.git_state_manager.GitHubPRClient"
            ) as mock_pr_client,
            patch(
                "code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
            patch.object(manager, "audit_logger", mock_audit_logger),
        ):
            mock_token.return_value = "token"
            mock_git.side_effect = [
                Mock(stdout="main\n"),  # Current branch
                Mock(stdout=""),  # Checkout
                Mock(stdout=""),  # Add
                Mock(stdout=""),  # Commit
                Mock(stdout="abc123def456\n"),  # git rev-parse HEAD (get commit hash)
                Mock(stdout=""),  # Push
                Mock(stdout=""),  # Return to main
            ]

            mock_pr_instance = Mock()
            mock_pr_instance.create_pull_request.return_value = (
                "https://github.com/test/repo/pull/1"
            )
            mock_pr_client.return_value = mock_pr_instance

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description="Fix",
                files_modified=[Path("file.py")],
                pr_description="Auto-fix",
                platform="github",
                job_id="job-12345",
            )

            # ASSERT
            assert result.success is True
            mock_audit_logger.log_pr_creation_success.assert_called_once()

            # Verify audit log was called with correct parameters
            call_args = mock_audit_logger.log_pr_creation_success.call_args
            assert call_args[1]["job_id"] == "job-12345"
            assert call_args[1]["pr_url"] == "https://github.com/test/repo/pull/1"

    def test_git_state_manager_calls_audit_logger_on_failure(self, tmp_path):
        """AC7: GitStateManager calls audit logger on PR creation failure."""
        # ARRANGE
        from code_indexer.server.services.git_state_manager import GitStateManager
        import subprocess

        config = Mock(enable_pr_creation=True, default_branch="main")
        manager = GitStateManager(config=config)

        # Mock audit logger
        mock_audit_logger = Mock()

        with (
            patch(
                "code_indexer.server.services.git_state_manager.run_git_command"
            ) as mock_git,
            patch(
                "code_indexer.server.services.git_state_manager.TokenAuthenticator.resolve_token"
            ) as mock_token,
            patch.object(manager, "audit_logger", mock_audit_logger),
        ):
            mock_token.return_value = "token"
            mock_git.side_effect = [
                Mock(stdout="main\n"),  # Current branch
                Mock(stdout=""),  # Checkout
                Mock(stdout=""),  # Add
                subprocess.CalledProcessError(
                    1, ["git", "commit"], stderr="Nothing to commit"
                ),
                Mock(stdout=""),  # Return to main
            ]

            # ACT
            result = manager.create_pr_after_fix(
                repo_path=tmp_path,
                fix_description="Fix",
                files_modified=[Path("file.py")],
                pr_description="Auto-fix",
                platform="github",
                job_id="job-67890",
            )

            # ASSERT
            assert result.success is False
            mock_audit_logger.log_pr_creation_failure.assert_called_once()

            # Verify audit log was called with failure reason
            call_args = mock_audit_logger.log_pr_creation_failure.call_args
            assert call_args[1]["job_id"] == "job-67890"
            assert "commit" in call_args[1]["reason"].lower()
