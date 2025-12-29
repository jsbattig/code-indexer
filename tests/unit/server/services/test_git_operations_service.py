"""
Unit tests for GitOperationsService.

Tests all 17 git operations across 5 feature groups using mocked subprocess.
Integration tests use real git operations on test repositories.

Feature Groups:
- F2: Status/Inspection (git_status, git_diff, git_log)
- F3: Staging/Commit (git_stage, git_unstage, git_commit)
- F4: Remote Operations (git_push, git_pull, git_fetch)
- F5: Recovery (git_reset, git_clean, git_merge_abort, git_checkout_file)
- F6: Branch Management (git_branch_list, git_branch_create, git_branch_switch, git_branch_delete)
"""

import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from code_indexer.config import ConfigManager, GitServiceConfig
from code_indexer.server.services.git_operations_service import (
    GitCommandError,
    GitOperationsService,
)

# Test constants for Story #623 security and reliability tests
TOKEN_EXPIRY_SECONDS = 300  # 5 minutes (matches TOKEN_EXPIRY in service)
EXPIRY_TEST_BUFFER = 60  # 1 minute buffer for expiration tests
CONCURRENT_THREADS_SMALL = 5  # Small concurrent test (token validation)
CONCURRENT_THREADS_MEDIUM = 10  # Medium concurrent test (token generation)
CONCURRENT_OPERATIONS_MEDIUM = 50  # Medium operation count


@pytest.fixture
def service():
    """Create GitOperationsService with mocked ConfigManager."""
    mock_config_manager = MagicMock(spec=ConfigManager)
    mock_config = MagicMock()
    mock_config.git_service = GitServiceConfig()
    mock_config_manager.load.return_value = mock_config
    return GitOperationsService(mock_config_manager)


class TestGitServiceConfiguration:
    """Test Git service configuration (Story #623)."""

    def test_git_service_config_defaults(self, service):
        """Test GitServiceConfig has correct default values."""
        config = GitServiceConfig()

        assert config.service_committer_name == "CIDX Service"
        assert config.service_committer_email == "cidx-service@example.com"

    def test_git_service_config_valid_email(self, service):
        """Test GitServiceConfig accepts valid email formats."""
        valid_emails = [
            "user@example.com",
            "test.user@domain.co.uk",
            "name+tag@subdomain.example.org",
        ]

        for email in valid_emails:
            config = GitServiceConfig(service_committer_email=email)
            assert config.service_committer_email == email

    def test_git_service_config_invalid_email_no_at(self, service):
        """Test GitServiceConfig rejects email without @."""
        with pytest.raises(ValueError) as exc_info:
            GitServiceConfig(service_committer_email="invalid.email.com")

        assert "must contain exactly one '@'" in str(exc_info.value)

    def test_git_service_config_invalid_email_no_domain_dot(self, service):
        """Test GitServiceConfig rejects email without dot in domain."""
        with pytest.raises(ValueError) as exc_info:
            GitServiceConfig(service_committer_email="user@domain")

        assert "domain must contain '.'" in str(exc_info.value)

    def test_git_service_config_invalid_email_empty_local(self, service):
        """Test GitServiceConfig rejects email with empty local part."""
        with pytest.raises(ValueError) as exc_info:
            GitServiceConfig(service_committer_email="@example.com")

        assert "empty local or domain part" in str(exc_info.value)

    def test_git_service_config_invalid_email_empty_domain(self, service):
        """Test GitServiceConfig rejects email with empty domain."""
        with pytest.raises(ValueError) as exc_info:
            GitServiceConfig(service_committer_email="user@")

        assert "empty local or domain part" in str(exc_info.value)

    def test_git_service_config_loading_from_config_manager(self, service):
        """Test loading git service config via ConfigManager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # Create minimal config with git_service
            import json
            config_data = {
                "git_service": {
                    "service_committer_name": "Test Service",
                    "service_committer_email": "test@example.com"
                }
            }
            config_path.write_text(json.dumps(config_data))

            # Load via ConfigManager
            manager = ConfigManager(config_path)
            config = manager.load()

            assert config.git_service.service_committer_name == "Test Service"
            assert config.git_service.service_committer_email == "test@example.com"

    def test_git_operations_service_loads_git_config(self, service):
        """Test GitOperationsService loads git_config from ConfigManager."""
        # Mock ConfigManager
        mock_config_manager = MagicMock(spec=ConfigManager)
        mock_config = MagicMock()
        mock_git_service = GitServiceConfig(
            service_committer_name="Test Committer",
            service_committer_email="committer@test.com"
        )
        mock_config.git_service = mock_git_service
        mock_config_manager.load.return_value = mock_config

        # Create service
        service = GitOperationsService(mock_config_manager)

        # Verify git_config is loaded
        assert service.git_config.service_committer_name == "Test Committer"
        assert service.git_config.service_committer_email == "committer@test.com"


class TestGitStatusAndInspection:
    """Test F2: Git Status and Inspection operations."""

    def test_git_status_clean_repo(self, service):
        """Test git status on clean repository."""
        pass  # Use service fixture

        # Mock subprocess to return empty status
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_status(Path("/tmp/repo"))

            assert result["staged"] == []
            assert result["unstaged"] == []
            assert result["untracked"] == []

    def test_git_status_mixed_changes(self, service):
        """Test git status with staged, unstaged, and untracked files."""
        pass  # Use service fixture

        # Simulate porcelain v1 output
        status_output = """M  staged_file.py
 M unstaged_file.py
?? untracked_file.py
A  added_file.py
 D deleted_file.py"""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=status_output,
                stderr=""
            )

            result = service.git_status(Path("/tmp/repo"))

            assert "staged_file.py" in result["staged"]
            assert "added_file.py" in result["staged"]
            assert "unstaged_file.py" in result["unstaged"]
            assert "deleted_file.py" in result["unstaged"]
            assert "untracked_file.py" in result["untracked"]

    def test_git_diff_entire_repo(self, service):
        """Test git diff without file filter."""
        pass  # Use service fixture

        diff_output = """diff --git a/file.py b/file.py
index abc123..def456 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,3 @@
-old line
+new line"""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=diff_output,
                stderr=""
            )

            result = service.git_diff(Path("/tmp/repo"))

            assert "diff_text" in result
            assert "file.py" in result["diff_text"]
            assert result["files_changed"] == 1

    def test_git_diff_specific_files(self, service):
        """Test git diff with file path filter."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="diff --git a/specific.py b/specific.py",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                file_paths=["specific.py"]
            )

            assert "specific.py" in result["diff_text"]
            # Verify git diff was called with file paths
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert "specific.py" in call_args

    def test_git_log_with_limit(self, service):
        """Test git log with commit limit."""
        pass  # Use service fixture

        # Simulate git log JSON output
        log_output = """{"commit_hash": "abc123", "author": "John Doe", "date": "2025-01-01", "message": "Initial commit"}
{"commit_hash": "def456", "author": "Jane Smith", "date": "2025-01-02", "message": "Add feature"}"""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=log_output,
                stderr=""
            )

            result = service.git_log(Path("/tmp/repo"), limit=2)

            assert len(result["commits"]) == 2
            assert result["commits"][0]["commit_hash"] == "abc123"
            assert result["commits"][1]["commit_hash"] == "def456"

    def test_git_log_with_since_date(self, service):
        """Test git log with date filter."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-15", "message": "Recent"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                since_date="2025-01-10"
            )

            # Verify --since flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--since=2025-01-10" in call_args

    def test_git_diff_with_context_lines(self, service):
        """Test git diff with custom context lines."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="diff --git a/file.py b/file.py",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                context_lines=5
            )

            # Verify -U5 flag was passed
            call_args = mock_run.call_args[0][0]
            assert "-U5" in call_args

    def test_git_diff_with_revision_range(self, service):
        """Test git diff with from_revision and to_revision."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="diff --git a/file.py b/file.py",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                from_revision="abc123",
                to_revision="def456"
            )

            # Verify revision range was passed
            call_args = mock_run.call_args[0][0]
            assert "abc123..def456" in call_args

    def test_git_diff_with_single_revision(self, service):
        """Test git diff with only from_revision (diff from revision to working tree)."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="diff --git a/file.py b/file.py",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                from_revision="abc123"
            )

            # Verify single revision was passed
            call_args = mock_run.call_args[0][0]
            assert "abc123" in call_args
            assert ".." not in " ".join(call_args)

    def test_git_diff_with_path_filter(self, service):
        """Test git diff with path parameter."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="diff --git a/src/module.py b/src/module.py",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                path="src/module.py"
            )

            # Verify -- path was passed
            call_args = mock_run.call_args[0][0]
            assert "--" in call_args
            assert "src/module.py" in call_args

    def test_git_diff_with_stat_only(self, service):
        """Test git diff with stat_only flag."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=" file.py | 5 +++--",
                stderr=""
            )

            result = service.git_diff(
                Path("/tmp/repo"),
                stat_only=True
            )

            # Verify --stat flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--stat" in call_args

    def test_git_log_with_until_date(self, service):
        """Test git log with until date filter."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-05", "message": "Old"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                until="2025-01-10"
            )

            # Verify --until flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--until=2025-01-10" in call_args

    def test_git_log_with_author_filter(self, service):
        """Test git log with author filter."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John Doe", "date": "2025-01-10", "message": "Fix"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                author="John Doe"
            )

            # Verify --author flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--author=John Doe" in call_args

    def test_git_log_with_branch(self, service):
        """Test git log with specific branch."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-10", "message": "Feature"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                branch="feature-branch"
            )

            # Verify branch was passed
            call_args = mock_run.call_args[0][0]
            assert "feature-branch" in call_args

    def test_git_log_with_path_filter(self, service):
        """Test git log with path filter."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-10", "message": "Fix"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                path="src/module.py"
            )

            # Verify -- path was passed
            call_args = mock_run.call_args[0][0]
            assert "--" in call_args
            assert "src/module.py" in call_args

    def test_git_log_with_aggregation_mode(self, service):
        """Test git log with aggregation_mode parameter (MCP feature)."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-10", "message": "Fix"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                aggregation_mode="chronological"
            )

            # Note: aggregation_mode affects response formatting, not git command
            # It should be accepted but not modify git command flags
            assert "commits" in result

    def test_git_log_with_response_format(self, service):
        """Test git log with response_format parameter (MCP feature)."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout='{"commit_hash": "abc123", "author": "John", "date": "2025-01-10", "message": "Fix"}',
                stderr=""
            )

            result = service.git_log(
                Path("/tmp/repo"),
                response_format="grouped"
            )

            # Note: response_format affects response structure, not git command
            # It should be accepted but not modify git command flags
            assert "commits" in result


class TestGitStagingAndCommit:
    """Test F3: Git Staging and Commit operations."""

    def test_git_stage_files(self, service):
        """Test staging multiple files."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            files = ["file1.py", "file2.py"]
            result = service.git_stage(Path("/tmp/repo"), files)

            assert result["success"] is True
            assert result["staged_files"] == files
            # Verify git add was called with files
            call_args = mock_run.call_args[0][0]
            assert "add" in call_args
            assert all(f in call_args for f in files)

    def test_git_unstage_files(self, service):
        """Test unstaging multiple files."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            files = ["file1.py", "file2.py"]
            result = service.git_unstage(Path("/tmp/repo"), files)

            assert result["success"] is True
            assert result["unstaged_files"] == files
            # Verify git reset HEAD was called
            call_args = mock_run.call_args[0][0]
            assert "reset" in call_args
            assert "HEAD" in call_args

    def test_git_commit_dual_attribution(self, service):
        """Test commit uses dual attribution (author != committer)."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test commit",
                stderr=""
            )

            result = service.git_commit(
                Path("/tmp/repo"),
                message="Add new feature",
                user_email="user@claude.ai",
                user_name="Claude User"
            )

            assert result["success"] is True
            assert result["message"] == "Add new feature"
            assert result["author"] == "user@claude.ai"
            assert result["committer"] == "cidx-service@example.com"
            assert result["author"] != result["committer"]  # Dual attribution

    def test_git_commit_environment_vars(self, service):
        """Test commit sets GIT_AUTHOR_* and GIT_COMMITTER_* environment variables."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test commit",
                stderr=""
            )

            service.git_commit(
                Path("/tmp/repo"),
                message="Test commit",
                user_email="user@example.com",
                user_name="Test User"
            )

            # Verify run_git_command was called with correct env vars
            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env")

            assert env is not None
            assert env["GIT_AUTHOR_NAME"] == "Test User"
            assert env["GIT_AUTHOR_EMAIL"] == "user@example.com"
            assert env["GIT_COMMITTER_NAME"] == "CIDX Service"
            assert env["GIT_COMMITTER_EMAIL"] == "cidx-service@example.com"

    def test_git_commit_message_format(self, service):
        """Test commit message format includes AUTHOR prefix."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test",
                stderr=""
            )

            service.git_commit(
                Path("/tmp/repo"),
                message="User's actual message",
                user_email="user@test.com"
            )

            # Extract the commit message from the git command
            call_args = mock_run.call_args[0][0]
            commit_msg_index = call_args.index("-m") + 1
            actual_message = call_args[commit_msg_index]

            # Verify message format (Git trailers format)
            assert "Actual-Author: user@test.com" in actual_message
            assert "User's actual message" in actual_message
            assert "Committed-Via: CIDX API" in actual_message

    def test_git_commit_derives_author_name_from_email(self, service):
        """Test commit derives author name from email if not provided."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test",
                stderr=""
            )

            service.git_commit(
                Path("/tmp/repo"),
                message="Test",
                user_email="testuser@example.com"
                # No user_name provided
            )

            # Verify GIT_AUTHOR_NAME was derived from email
            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env")
            assert env["GIT_AUTHOR_NAME"] == "testuser"


class TestGitRemoteOperations:
    """Test F4: Git Remote Operations."""

    def test_git_push_success(self, service):
        """Test successful push to remote."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="To github.com:user/repo.git\n   abc1234..def5678  master -> master",
                stderr=""
            )

            result = service.git_push(Path("/tmp/repo"))

            assert result["success"] is True
            assert result["pushed_commits"] >= 0

    def test_git_push_authentication_failure(self, service):
        """Test push with authentication error."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "push"],
                stderr="Authentication failed"
            )

            with pytest.raises(GitCommandError) as exc_info:
                service.git_push(Path("/tmp/repo"))

            assert "Authentication" in str(exc_info.value)

    def test_git_push_network_error(self, service):
        """Test push with network connectivity error."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "push"],
                stderr="Could not resolve host"
            )

            with pytest.raises(GitCommandError) as exc_info:
                service.git_push(Path("/tmp/repo"))

            assert "Could not resolve host" in str(exc_info.value)

    def test_git_pull_success(self, service):
        """Test successful pull from remote."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Updating abc1234..def5678\nFast-forward\n file.py | 2 +-\n 1 file changed",
                stderr=""
            )

            result = service.git_pull(Path("/tmp/repo"))

            assert result["success"] is True
            assert result["updated_files"] >= 0
            assert result["conflicts"] == []

    def test_git_pull_merge_conflicts(self, service):
        """Test pull with merge conflicts."""
        pass  # Use service fixture

        conflict_output = """Auto-merging file.py
CONFLICT (content): Merge conflict in file.py
Automatic merge failed; fix conflicts and then commit the result."""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout=conflict_output,
                stderr=""
            )

            result = service.git_pull(Path("/tmp/repo"))

            assert result["success"] is False
            assert "file.py" in result["conflicts"]

    def test_git_fetch_success(self, service):
        """Test fetch from remote."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="From github.com:user/repo\n * branch master -> FETCH_HEAD",
                stderr=""
            )

            result = service.git_fetch(Path("/tmp/repo"))

            assert result["success"] is True
            assert isinstance(result["fetched_refs"], list)


class TestGitRecovery:
    """Test F5: Git Recovery Operations."""

    def test_git_reset_soft(self, service):
        """Test soft reset (does not require token)."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_reset(
                Path("/tmp/repo"),
                mode="soft",
                commit_hash="HEAD~1"
            )

            assert result["success"] is True
            assert result["reset_mode"] == "soft"
            assert result["target_commit"] == "HEAD~1"

    def test_git_reset_mixed(self, service):
        """Test mixed reset (does not require token)."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_reset(
                Path("/tmp/repo"),
                mode="mixed",
                commit_hash="abc1234"
            )

            assert result["success"] is True
            assert result["reset_mode"] == "mixed"

    def test_git_reset_hard_requires_token(self, service):
        """Test hard reset requires confirmation token."""
        pass  # Use service fixture

        result = service.git_reset(
            Path("/tmp/repo"),
            mode="hard",
            commit_hash="HEAD~1"
        )

        assert result["requires_confirmation"] is True
        assert "token" in result
        assert len(result["token"]) == 6

    def test_git_reset_hard_with_invalid_token(self, service):
        """Test hard reset with invalid token."""
        pass  # Use service fixture

        with pytest.raises(ValueError) as exc_info:
            service.git_reset(
                Path("/tmp/repo"),
                mode="hard",
                commit_hash="HEAD~1",
                confirmation_token="INVALID"
            )

        assert "Invalid or expired" in str(exc_info.value)

    def test_git_reset_hard_with_valid_token(self, service):
        """Test hard reset with valid confirmation token."""
        pass  # Use service fixture

        # First, generate a token
        result1 = service.git_reset(
            Path("/tmp/repo"),
            mode="hard",
            commit_hash="HEAD~1"
        )
        token = result1["token"]

        # Then use the token
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="HEAD is now at abc1234",
                stderr=""
            )

            result2 = service.git_reset(
                Path("/tmp/repo"),
                mode="hard",
                commit_hash="HEAD~1",
                confirmation_token=token
            )

            assert result2["success"] is True
            assert result2["reset_mode"] == "hard"

    def test_git_clean_requires_token(self, service):
        """Test git clean requires confirmation token."""
        pass  # Use service fixture

        result = service.git_clean(Path("/tmp/repo"))

        assert result["requires_confirmation"] is True
        assert "token" in result
        assert len(result["token"]) == 6

    def test_git_clean_with_valid_token(self, service):
        """Test git clean with valid confirmation token."""
        pass  # Use service fixture

        # Generate token
        result1 = service.git_clean(Path("/tmp/repo"))
        token = result1["token"]

        # Use token
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Removing untracked_file.py\nRemoving temp_dir/",
                stderr=""
            )

            result2 = service.git_clean(
                Path("/tmp/repo"),
                confirmation_token=token
            )

            assert result2["success"] is True
            assert "untracked_file.py" in result2["removed_files"]

    def test_git_merge_abort(self, service):
        """Test aborting a merge."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_merge_abort(Path("/tmp/repo"))

            assert result["success"] is True
            assert result["aborted"] is True

    def test_git_checkout_file(self, service):
        """Test checking out (restoring) a file."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_checkout_file(
                Path("/tmp/repo"),
                file_path="modified_file.py"
            )

            assert result["success"] is True
            assert result["restored_file"] == "modified_file.py"


class TestGitBranchManagement:
    """Test F6: Git Branch Management Operations."""

    def test_git_branch_list(self, service):
        """Test listing all branches."""
        pass  # Use service fixture

        branch_output = """* master
  feature-branch
  remotes/origin/master
  remotes/origin/develop"""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=branch_output,
                stderr=""
            )

            result = service.git_branch_list(Path("/tmp/repo"))

            assert result["current"] == "master"
            assert "master" in result["local"]
            assert "feature-branch" in result["local"]
            assert "origin/master" in result["remote"]
            assert "origin/develop" in result["remote"]

    def test_git_branch_create(self, service):
        """Test creating a new branch."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="",
                stderr=""
            )

            result = service.git_branch_create(
                Path("/tmp/repo"),
                branch_name="new-feature"
            )

            assert result["success"] is True
            assert result["created_branch"] == "new-feature"

    def test_git_branch_switch(self, service):
        """Test switching branches."""
        pass  # Use service fixture

        # Mock two calls: one to get current branch, one to switch
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = [
                Mock(returncode=0, stdout="master", stderr=""),  # Current branch
                Mock(returncode=0, stdout="Switched to branch 'feature'", stderr="")  # Switch
            ]

            result = service.git_branch_switch(
                Path("/tmp/repo"),
                branch_name="feature"
            )

            assert result["success"] is True
            assert result["current_branch"] == "feature"
            assert result["previous_branch"] == "master"

    def test_git_branch_delete_requires_token(self, service):
        """Test branch deletion requires confirmation token."""
        pass  # Use service fixture

        result = service.git_branch_delete(
            Path("/tmp/repo"),
            branch_name="old-feature"
        )

        assert result["requires_confirmation"] is True
        assert "token" in result
        assert len(result["token"]) == 6

    def test_git_branch_delete_with_valid_token(self, service):
        """Test branch deletion with valid confirmation token."""
        pass  # Use service fixture

        # Generate token
        result1 = service.git_branch_delete(
            Path("/tmp/repo"),
            branch_name="old-feature"
        )
        token = result1["token"]

        # Use token
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Deleted branch old-feature",
                stderr=""
            )

            result2 = service.git_branch_delete(
                Path("/tmp/repo"),
                branch_name="old-feature",
                confirmation_token=token
            )

            assert result2["success"] is True
            assert result2["deleted_branch"] == "old-feature"


class TestConfirmationTokenSystem:
    """Test confirmation token generation and validation."""

    def test_confirmation_token_generation(self, service):
        """Test token generation produces unique tokens."""
        pass  # Use service fixture

        tokens = set()
        for _ in range(10):
            token = service._generate_confirmation_token("test_operation")
            assert len(token) == 6
            assert token.isalnum()
            tokens.add(token)

        # All tokens should be unique (highly probable with 6-char random)
        assert len(tokens) == 10

    def test_confirmation_token_validation(self, service):
        """Test token validation logic."""
        pass  # Use service fixture

        # Generate token
        token = service._generate_confirmation_token("test_op")

        # Valid token should work once
        assert service._validate_confirmation_token("test_op", token) is True

        # Same token should fail on second use (single-use)
        assert service._validate_confirmation_token("test_op", token) is False

    def test_confirmation_token_wrong_operation(self, service):
        """Test token is operation-specific."""
        pass  # Use service fixture

        token = service._generate_confirmation_token("operation_a")

        # Token should not work for different operation
        assert service._validate_confirmation_token("operation_b", token) is False

    def test_confirmation_token_expiration(self, service):
        """Test token expiration after TTL."""
        import time
        from cachetools import TTLCache

        pass  # Use service fixture

        # Use short TTL for fast testing (1 second instead of 5 minutes)
        service._tokens = TTLCache(maxsize=10000, ttl=1, timer=time.time)

        token = service._generate_confirmation_token("test_op")

        # Wait for token to expire
        time.sleep(1.5)

        # Trigger lazy expiration by accessing cache
        _ = list(service._tokens.keys())

        # Token should be expired
        assert service._validate_confirmation_token("test_op", token) is False


class TestErrorHandling:
    """Test error handling across all operations."""

    def test_git_command_error_with_stderr(self, service):
        """Test GitCommandError captures stderr."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["git", "status"],
                stderr="fatal: not a git repository"
            )

            with pytest.raises(GitCommandError) as exc_info:
                service.git_status(Path("/tmp/not-a-repo"))

            assert "not a git repository" in exc_info.value.stderr

    def test_invalid_branch_error(self, service):
        """Test error when switching to non-existent branch."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["git", "checkout", "nonexistent"],
                stderr="error: pathspec 'nonexistent' did not match any file(s) known to git"
            )

            with pytest.raises(GitCommandError) as exc_info:
                service.git_branch_switch(Path("/tmp/repo"), "nonexistent")

            assert "did not match" in exc_info.value.stderr

    def test_timeout_error(self, service):
        """Test timeout on long-running operations."""
        pass  # Use service fixture

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "push"],
                timeout=30
            )

            with pytest.raises(GitCommandError):
                service.git_push(Path("/tmp/repo"))


# Integration Tests (Real Git Operations)

class TestGitIntegration:
    """Integration tests with real git operations on test repositories."""

    @pytest.fixture
    def test_repo(self, service):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=repo_path,
                check=True,
                capture_output=True
            )

            # Configure git user
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True
            )

            yield repo_path

    def test_git_workflow_integration(self, test_repo):
        """Test complete workflow: stage, commit, status."""
        # Create service with real ConfigManager
        config_path = test_repo / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_manager = ConfigManager(config_path)
        service = GitOperationsService(config_manager)

        # Create a test file
        test_file = test_repo / "test.py"
        test_file.write_text("print('hello')")

        # Check status (should show untracked)
        status = service.git_status(test_repo)
        assert "test.py" in status["untracked"]

        # Stage the file
        result = service.git_stage(test_repo, ["test.py"])
        assert result["success"] is True

        # Commit the file with dual attribution
        result = service.git_commit(
            test_repo,
            "Initial commit",
            user_email="testuser@example.com",
            user_name="Test User"
        )
        assert result["success"] is True
        assert "commit_hash" in result
        assert result["author"] == "testuser@example.com"
        assert result["committer"] == "cidx-service@example.com"

        # Check status (should be clean)
        status = service.git_status(test_repo)
        assert status["staged"] == []
        assert status["unstaged"] == []
        assert status["untracked"] == []

    def test_git_commit_attribution_integration(self, test_repo):
        """Test dual attribution in real commit (author != committer)."""
        # Create service with real ConfigManager
        config_path = test_repo / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_manager = ConfigManager(config_path)
        service = GitOperationsService(config_manager)

        # Create and stage a test file
        test_file = test_repo / "attribution_test.py"
        test_file.write_text("# Test file for attribution")
        service.git_stage(test_repo, ["attribution_test.py"])

        # Commit with dual attribution
        result = service.git_commit(
            test_repo,
            "Test dual attribution",
            user_email="claude@claude.ai",
            user_name="Claude AI"
        )

        assert result["success"] is True
        commit_hash = result["commit_hash"]

        # Verify attribution using git log
        git_log_result = subprocess.run(
            ["git", "log", "-1", "--format=%an|%ae|%cn|%ce|%B", commit_hash],
            cwd=test_repo,
            capture_output=True,
            text=True,
            check=True
        )

        output = git_log_result.stdout.strip()
        lines = output.split("|")
        author_name = lines[0]
        author_email = lines[1]
        committer_name = lines[2]
        committer_email = lines[3]
        commit_message = lines[4]

        # Verify dual attribution
        assert author_name == "Claude AI"
        assert author_email == "claude@claude.ai"
        assert committer_name == "CIDX Service"
        assert committer_email == "cidx-service@example.com"
        assert author_email != committer_email

        # Verify commit message format (Git trailers format)
        assert "Actual-Author: claude@claude.ai" in commit_message
        assert "Test dual attribution" in commit_message
        assert "Committed-Via: CIDX API" in commit_message

    def test_git_branch_workflow(self, test_repo):
        """Test branch workflow: create, switch, delete."""
        # Create service with real ConfigManager
        config_path = test_repo / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_manager = ConfigManager(config_path)
        service = GitOperationsService(config_manager)

        # Create initial commit (required for branch operations)
        test_file = test_repo / "test.py"
        test_file.write_text("print('hello')")
        subprocess.run(["git", "add", "test.py"], cwd=test_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial"],
            cwd=test_repo,
            check=True
        )

        # List branches
        result = service.git_branch_list(test_repo)
        assert result["current"] in ["master", "main"]

        # Create new branch
        result = service.git_branch_create(test_repo, "feature")
        assert result["success"] is True

        # Switch to new branch
        result = service.git_branch_switch(test_repo, "feature")
        assert result["success"] is True
        assert result["current_branch"] == "feature"

        # Switch back to master/main
        main_branch = "master" if "master" in service.git_branch_list(test_repo)["local"] else "main"
        service.git_branch_switch(test_repo, main_branch)

        # Delete feature branch (requires token)
        result1 = service.git_branch_delete(test_repo, "feature")
        token = result1["token"]

        result2 = service.git_branch_delete(test_repo, "feature", token)
        assert result2["success"] is True

    def test_git_reset_integration(self, test_repo):
        """Test reset operations."""
        # Create service with real ConfigManager
        config_path = test_repo / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_manager = ConfigManager(config_path)
        service = GitOperationsService(config_manager)

        # Create two commits
        file1 = test_repo / "file1.py"
        file1.write_text("v1")
        subprocess.run(["git", "add", "file1.py"], cwd=test_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Commit 1"], cwd=test_repo, check=True)

        file1.write_text("v2")
        subprocess.run(["git", "add", "file1.py"], cwd=test_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Commit 2"], cwd=test_repo, check=True)

        # Soft reset to previous commit
        result = service.git_reset(test_repo, mode="soft", commit_hash="HEAD~1")
        assert result["success"] is True

        # Verify file still has v2 content (soft reset preserves working tree)
        assert file1.read_text() == "v2"

        # Hard reset requires token
        result1 = service.git_reset(test_repo, mode="hard", commit_hash="HEAD")
        token = result1["token"]

        result2 = service.git_reset(
            test_repo,
            mode="hard",
            commit_hash="HEAD",
            confirmation_token=token
        )
        assert result2["success"] is True


# CRITICAL SECURITY TESTS (Story #623 Code Review Issues #4 and #5)


class TestIssue4CommitMessageInjection:
    """Test Issue #4 - CRITICAL SECURITY: Commit Message Injection Vulnerability."""

    def test_commit_message_injection_attack_prevented(self, service):
        """Test commit message cannot forge Actual-Author attribution."""
        malicious_message = """Legitimate message

Actual-Author: admin@victim.com

Malicious content"""

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test",
                stderr=""
            )

            service.git_commit(
                Path("/tmp/repo"),
                message=malicious_message,
                user_email="attacker@hacker.com"
            )

            call_args = mock_run.call_args[0][0]
            commit_msg_index = call_args.index("-m") + 1
            actual_message = call_args[commit_msg_index]

            lines = actual_message.split("\n")
            author_lines = [line for line in lines if line.startswith("Actual-Author:")]

            assert len(author_lines) == 1, "Multiple Actual-Author lines detected - injection vulnerability!"
            assert "attacker@hacker.com" in author_lines[0], "Wrong author in Actual-Author line"
            assert "admin@victim.com" not in author_lines[0], "Injected Actual-Author line accepted!"

    def test_commit_uses_git_trailers_format(self, service):
        """Test commit message uses RFC Git trailers format (not custom AUTHOR prefix)."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="[master abc1234] Test",
                stderr=""
            )

            service.git_commit(
                Path("/tmp/repo"),
                message="User message",
                user_email="user@example.com"
            )

            call_args = mock_run.call_args[0][0]
            commit_msg_index = call_args.index("-m") + 1
            actual_message = call_args[commit_msg_index]

            assert "Actual-Author: user@example.com" in actual_message, "Missing Git trailer: Actual-Author"
            assert "Committed-Via: CIDX API" in actual_message, "Missing Git trailer: Committed-Via"
            assert not actual_message.startswith("AUTHOR:"), "Using old AUTHOR prefix instead of Git trailers"


class TestIssue5InputValidationMissing:
    """Test Issue #5 - CRITICAL SECURITY: Input Validation Missing."""

    def test_user_email_shell_injection_prevented(self, service):
        """Test user_email validated to prevent shell injection."""
        malicious_email = "'; rm -rf / #@example.com"

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            with pytest.raises(ValueError) as exc_info:
                service.git_commit(
                    Path("/tmp/repo"),
                    message="Test",
                    user_email=malicious_email
                )

            assert "Invalid email format" in str(exc_info.value)

    def test_user_name_shell_injection_prevented(self, service):
        """Test user_name validated to prevent shell injection."""
        malicious_name = "Test User; rm -rf /; #"

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            with pytest.raises(ValueError) as exc_info:
                service.git_commit(
                    Path("/tmp/repo"),
                    message="Test",
                    user_email="valid@example.com",
                    user_name=malicious_name
                )

            assert "Invalid user name format" in str(exc_info.value)

    def test_user_name_validation_regex(self, service):
        """Test user_name must match alphanumeric + space/hyphen/underscore only."""
        valid_names = [
            "John Doe",
            "test-user",
            "user_name",
            "User123",
            "Test-User_123"
        ]

        invalid_names = [
            "User; rm -rf /",
            "User$(whoami)",
            "User`whoami`",
            "User&& ls",
            "User|cat /etc/passwd",
        ]

        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            for name in valid_names:
                try:
                    service.git_commit(
                        Path("/tmp/repo"),
                        message="Test",
                        user_email="valid@example.com",
                        user_name=name
                    )
                except ValueError:
                    pytest.fail(f"Valid name rejected: {name}")

            for name in invalid_names:
                with pytest.raises(ValueError, match="Invalid user name format"):
                    service.git_commit(
                        Path("/tmp/repo"),
                        message="Test",
                        user_email="valid@example.com",
                        user_name=name
                    )


class TestIssue3EmailValidationInsufficient:
    """Test Issue #3 - CRITICAL SECURITY: Email Validation Insufficient."""

    def test_email_validation_rejects_multiple_at_signs(self, service):
        """Test email validation rejects multiple @ signs."""
        invalid_emails = [
            "user@domain@second.com",
            "user@@domain.com",
            "@user@domain.com"
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                GitServiceConfig(service_committer_email=email)

    def test_email_validation_rejects_consecutive_dots(self, service):
        """Test email validation rejects consecutive dots in domain."""
        invalid_emails = [
            "user@domain..com",
            "user@..domain.com",
            "user@domain.com.."
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                GitServiceConfig(service_committer_email=email)

    def test_email_validation_rejects_leading_trailing_dots(self, service):
        """Test email validation rejects leading/trailing dots in domain."""
        invalid_emails = [
            "user@.domain.com",
            "user@domain.com.",
            "user@.domain.com."
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                GitServiceConfig(service_committer_email=email)

    def test_email_validation_requires_tld_minimum_length(self, service):
        """Test email validation requires TLD >= 2 characters."""
        invalid_emails = [
            "user@domain.c",
            "user@domain.a",
        ]

        valid_emails = [
            "user@domain.co",
            "user@domain.com",
        ]

        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                GitServiceConfig(service_committer_email=email)

        for email in valid_emails:
            config = GitServiceConfig(service_committer_email=email)
            assert config.service_committer_email == email

    def test_email_validation_rfc5322_compliant(self, service):
        """Test email validation is RFC 5322 compliant."""
        valid_emails = [
            "simple@example.com",
            "very.common@example.com",
            "disposable.style.email.with+symbol@example.com",
            "other.email-with-hyphen@example.com",
            "fully-qualified-domain@example.com",
            "user.name+tag+sorting@example.com",
            "x@example.com",
            "example-indeed@strange-example.com",
            "test/test@test.com",
        ]

        invalid_emails = [
            "user@.com",
            "user@domain@second.com",
            "@example.com",
            "user@",
            "user name@example.com",
            "user@domain",
        ]

        for email in valid_emails:
            config = GitServiceConfig(service_committer_email=email)
            assert config.service_committer_email == email

        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                GitServiceConfig(service_committer_email=email)


class TestIssue1ThreadSafetyMissing:
    """Test Issue #1 - CRITICAL RELIABILITY: Thread-Safety Missing."""

    def test_token_generation_thread_safe(self, service):
        """Test concurrent token generation is thread-safe."""
        num_threads = CONCURRENT_THREADS_MEDIUM
        tokens = []
        errors = []

        def generate_token():
            try:
                token = service._generate_confirmation_token("test_op")
                tokens.append(token)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=generate_token)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread-safety errors: {errors}"
        assert len(tokens) == num_threads, "Lost tokens due to race condition"
        assert len(set(tokens)) == num_threads, "Duplicate tokens generated (race condition)"

    def test_token_validation_thread_safe(self, service):
        """Test concurrent token validation is thread-safe (exactly 1 succeeds)."""
        token = service._generate_confirmation_token("test_op")

        validation_results = []
        errors = []

        def validate_token():
            try:
                result = service._validate_confirmation_token("test_op", token)
                validation_results.append(result)
            except Exception as e:
                errors.append(e)

        num_threads = CONCURRENT_THREADS_SMALL
        threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=validate_token)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread-safety errors: {errors}"
        assert len(validation_results) == num_threads
        assert sum(validation_results) == 1, f"Expected 1 success, got {sum(validation_results)} (race condition)"

    def test_token_dict_concurrent_access_no_corruption(self, service):
        """Test concurrent token operations don't corrupt internal state."""
        num_operations = CONCURRENT_OPERATIONS_MEDIUM
        errors = []
        successful_validations = []

        def mixed_operations(op_id):
            try:
                if op_id % 3 == 0:
                    service._generate_confirmation_token(f"op_{op_id}")
                elif op_id % 3 == 1:
                    result = service._validate_confirmation_token(f"op_{op_id}", "FAKE")
                    if result:
                        successful_validations.append(op_id)
                else:
                    token = service._generate_confirmation_token(f"op_{op_id}")
                    result = service._validate_confirmation_token(f"op_{op_id}", token)
                    if result:
                        successful_validations.append(op_id)
            except Exception as e:
                errors.append((op_id, e))

        with ThreadPoolExecutor(max_workers=CONCURRENT_THREADS_MEDIUM) as executor:
            futures = [executor.submit(mixed_operations, i) for i in range(num_operations)]
            for future in futures:
                future.result()

        assert len(errors) == 0, f"Thread-safety errors: {errors}"
        # Check token storage is TTLCache (not corrupted)
        from cachetools import TTLCache
        assert isinstance(service._tokens, TTLCache), "Token storage corrupted"


class TestIssue2MemoryLeakInTokens:
    """Test Issue #2 - CRITICAL RELIABILITY: Memory Leak in Tokens."""

    def test_expired_tokens_cleaned_up_automatically(self, service):
        """Test expired tokens are automatically removed from memory."""
        # Use short TTL for fast testing (1 second instead of 5 minutes)
        from cachetools import TTLCache
        service._tokens = TTLCache(maxsize=10000, ttl=1, timer=time.time)

        tokens = []
        for i in range(10):
            token = service._generate_confirmation_token(f"op_{i}")
            tokens.append(token)

        assert len(service._tokens) == 10

        # Wait for tokens to expire (1 second + buffer)
        time.sleep(1.5)

        # Trigger lazy expiration by accessing cache (TTLCache expires items on access)
        _ = list(service._tokens.keys())

        assert len(service._tokens) == 0, f"Memory leak: {len(service._tokens)} expired tokens not cleaned up"

    def test_token_storage_uses_ttl_cache(self, service):
        """Test token storage uses cachetools.TTLCache for auto-expiration."""
        try:
            from cachetools import TTLCache
            assert isinstance(service._tokens, TTLCache), "Token storage must use TTLCache to prevent memory leak"
        except ImportError:
            pytest.fail("cachetools library not installed (required for TTLCache)")

    def test_tokens_automatically_expire_without_manual_cleanup(self, service):
        """Test tokens expire automatically without requiring manual cleanup."""
        # Use short TTL for fast testing (1 second instead of 5 minutes)
        from cachetools import TTLCache
        service._tokens = TTLCache(maxsize=10000, ttl=1, timer=time.time)

        token = service._generate_confirmation_token("test_op")

        assert len(service._tokens) > 0

        # Wait for token to expire (1 second + buffer)
        time.sleep(1.5)

        # Trigger lazy expiration by accessing cache
        _ = list(service._tokens.keys())

        assert len(service._tokens) == 0, "Expired tokens not automatically removed (memory leak)"


class TestIssue7InsufficientErrorContext:
    """Test Issue #7 - HIGH PRIORITY: Insufficient Error Context."""

    def test_git_command_error_includes_command(self, service):
        """Test GitCommandError captures the command that failed."""
        error = GitCommandError(
            message="Command failed",
            stderr="fatal: error",
            returncode=1,
            command=["git", "status"],
            cwd=Path("/tmp/repo")
        )

        assert hasattr(error, "command"), "GitCommandError missing 'command' attribute"
        assert hasattr(error, "cwd"), "GitCommandError missing 'cwd' attribute"
        assert error.command == ["git", "status"]
        assert error.cwd == Path("/tmp/repo")

    def test_git_command_error_includes_cwd(self, service):
        """Test GitCommandError captures working directory."""
        error = GitCommandError(
            message="Command failed",
            stderr="fatal: not a git repository",
            returncode=128,
            command=["git", "log"],
            cwd=Path("/invalid/path")
        )

        assert error.cwd == Path("/invalid/path")

    def test_git_command_error_str_shows_full_context(self, service):
        """Test GitCommandError.__str__ shows command and cwd."""
        error = GitCommandError(
            message="git status failed",
            stderr="fatal: not a git repository",
            returncode=128,
            command=["git", "status"],
            cwd=Path("/tmp/not-a-repo")
        )

        error_str = str(error)

        assert "git status" in error_str, "Error message missing command"
        assert "/tmp/not-a-repo" in error_str, "Error message missing cwd"
        assert "fatal: not a git repository" in error_str, "Error message missing stderr"
        assert "128" in error_str, "Error message missing return code"

    def test_git_operations_raise_error_with_full_context(self, service):
        """Test git operations include command and cwd in raised errors."""
        with patch("code_indexer.utils.git_runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=128,
                cmd=["git", "status"],
                stderr="fatal: not a git repository"
            )

            with pytest.raises(GitCommandError) as exc_info:
                service.git_status(Path("/tmp/invalid-repo"))

            error = exc_info.value
            assert hasattr(error, "command"), "Raised GitCommandError missing command context"
            assert hasattr(error, "cwd"), "Raised GitCommandError missing cwd context"
            assert error.cwd == Path("/tmp/invalid-repo")


class TestRESTWrapperMethods:
    """Test REST API wrapper methods that resolve repo_alias to repo_path."""

    @pytest.fixture
    def mock_activated_repo_manager(self):
        """Mock ActivatedRepoManager for testing wrapper methods."""
        with patch("code_indexer.server.repositories.activated_repo_manager.ActivatedRepoManager") as mock_manager_class:
            mock_instance = Mock()
            mock_manager_class.return_value = mock_instance
            yield mock_instance

    # F3: Staging/Commit Wrapper Methods

    def test_stage_files_wrapper(self, service, mock_activated_repo_manager):
        """Test stage_files wrapper resolves alias and calls git_stage."""
        # Setup mocks
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_stage') as mock_git_stage:
            mock_git_stage.return_value = {
                "success": True,
                "staged_files": ["file1.py", "file2.py"]
            }

            # Call wrapper method
            result = service.stage_files(
                repo_alias="test-repo",
                username="testuser",
                file_paths=["file1.py", "file2.py"]
            )

            # Verify alias resolution
            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            # Verify git_stage called with correct parameters
            mock_git_stage.assert_called_once_with(
                Path("/path/to/repo"),
                file_paths=["file1.py", "file2.py"]
            )

            # Verify success field added
            assert result["success"] is True
            assert result["staged_files"] == ["file1.py", "file2.py"]

    def test_unstage_files_wrapper(self, service, mock_activated_repo_manager):
        """Test unstage_files wrapper resolves alias and calls git_unstage."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_unstage') as mock_git_unstage:
            mock_git_unstage.return_value = {
                "success": True,
                "unstaged_files": ["file1.py"]
            }

            result = service.unstage_files(
                repo_alias="test-repo",
                username="testuser",
                file_paths=["file1.py"]
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_unstage.assert_called_once_with(
                Path("/path/to/repo"),
                file_paths=["file1.py"]
            )

            assert result["success"] is True
            assert result["unstaged_files"] == ["file1.py"]

    def test_create_commit_wrapper(self, service, mock_activated_repo_manager):
        """Test create_commit wrapper resolves alias and calls git_commit."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_commit') as mock_git_commit:
            mock_git_commit.return_value = {
                "success": True,
                "commit_hash": "abc123",
                "message": "Test commit",
                "author": "test@example.com",
                "committer": "cidx@example.com"
            }

            result = service.create_commit(
                repo_alias="test-repo",
                username="testuser",
                message="Test commit",
                user_email="test@example.com",
                user_name="Test User"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_commit.assert_called_once_with(
                Path("/path/to/repo"),
                message="Test commit",
                user_email="test@example.com",
                user_name="Test User"
            )

            assert result["success"] is True
            assert result["commit_hash"] == "abc123"

    # F4: Remote Operations Wrapper Methods

    def test_push_to_remote_wrapper(self, service, mock_activated_repo_manager):
        """Test push_to_remote wrapper resolves alias and calls git_push."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_push') as mock_git_push:
            mock_git_push.return_value = {
                "success": True,
                "pushed_commits": 2
            }

            result = service.push_to_remote(
                repo_alias="test-repo",
                username="testuser",
                remote="origin",
                branch="main"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_push.assert_called_once_with(
                Path("/path/to/repo"),
                remote="origin",
                branch="main"
            )

            assert result["success"] is True
            assert result["pushed_commits"] == 2

    def test_pull_from_remote_wrapper(self, service, mock_activated_repo_manager):
        """Test pull_from_remote wrapper resolves alias and calls git_pull."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_pull') as mock_git_pull:
            mock_git_pull.return_value = {
                "success": True,
                "updated_files": 3,
                "conflicts": []
            }

            result = service.pull_from_remote(
                repo_alias="test-repo",
                username="testuser",
                remote="origin",
                branch="main"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_pull.assert_called_once_with(
                Path("/path/to/repo"),
                remote="origin",
                branch="main"
            )

            assert result["success"] is True
            assert result["updated_files"] == 3

    def test_fetch_from_remote_wrapper(self, service, mock_activated_repo_manager):
        """Test fetch_from_remote wrapper resolves alias and calls git_fetch."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_fetch') as mock_git_fetch:
            mock_git_fetch.return_value = {
                "success": True,
                "fetched_refs": ["origin/main"]
            }

            result = service.fetch_from_remote(
                repo_alias="test-repo",
                username="testuser",
                remote="origin"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_fetch.assert_called_once_with(
                Path("/path/to/repo"),
                remote="origin"
            )

            assert result["success"] is True
            assert result["fetched_refs"] == ["origin/main"]

    # F5: Recovery Operations Wrapper Methods

    def test_reset_repository_wrapper_hard_requires_token(self, service, mock_activated_repo_manager):
        """Test reset_repository wrapper handles confirmation token for hard reset."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_reset') as mock_git_reset:
            mock_git_reset.return_value = {
                "requires_confirmation": True,
                "token": "ABC123"
            }

            result = service.reset_repository(
                repo_alias="test-repo",
                username="testuser",
                mode="hard"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_reset.assert_called_once_with(
                Path("/path/to/repo"),
                mode="hard",
                commit_hash=None,
                confirmation_token=None
            )

            assert result["requires_confirmation"] is True
            assert "token" in result

    def test_reset_repository_wrapper_hard_with_token(self, service, mock_activated_repo_manager):
        """Test reset_repository wrapper passes confirmation token to git_reset."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_reset') as mock_git_reset:
            mock_git_reset.return_value = {
                "success": True,
                "reset_mode": "hard",
                "target_commit": "HEAD"
            }

            result = service.reset_repository(
                repo_alias="test-repo",
                username="testuser",
                mode="hard",
                confirmation_token="ABC123"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_reset.assert_called_once_with(
                Path("/path/to/repo"),
                mode="hard",
                commit_hash=None,
                confirmation_token="ABC123"
            )

            assert result["success"] is True
            assert result["reset_mode"] == "hard"

    def test_clean_repository_wrapper_requires_token(self, service, mock_activated_repo_manager):
        """Test clean_repository wrapper handles confirmation token requirement."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_clean') as mock_git_clean:
            mock_git_clean.return_value = {
                "requires_confirmation": True,
                "token": "XYZ789"
            }

            result = service.clean_repository(
                repo_alias="test-repo",
                username="testuser"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_clean.assert_called_once_with(
                Path("/path/to/repo"),
                confirmation_token=None
            )

            assert result["requires_confirmation"] is True
            assert "token" in result

    def test_clean_repository_wrapper_with_token(self, service, mock_activated_repo_manager):
        """Test clean_repository wrapper passes confirmation token to git_clean."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_clean') as mock_git_clean:
            mock_git_clean.return_value = {
                "success": True,
                "removed_files": ["temp.txt"]
            }

            result = service.clean_repository(
                repo_alias="test-repo",
                username="testuser",
                confirmation_token="XYZ789"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_clean.assert_called_once_with(
                Path("/path/to/repo"),
                confirmation_token="XYZ789"
            )

            assert result["success"] is True
            assert result["removed_files"] == ["temp.txt"]

    def test_abort_merge_wrapper(self, service, mock_activated_repo_manager):
        """Test abort_merge wrapper resolves alias and calls git_merge_abort."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_merge_abort') as mock_git_merge_abort:
            mock_git_merge_abort.return_value = {
                "success": True,
                "aborted": True
            }

            result = service.abort_merge(
                repo_alias="test-repo",
                username="testuser"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_merge_abort.assert_called_once_with(
                Path("/path/to/repo")
            )

            assert result["success"] is True
            assert result["aborted"] is True

    def test_checkout_file_wrapper(self, service, mock_activated_repo_manager):
        """Test checkout_file wrapper resolves alias and calls git_checkout_file."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_checkout_file') as mock_git_checkout_file:
            mock_git_checkout_file.return_value = {
                "success": True,
                "restored_file": "file1.py"
            }

            result = service.checkout_file(
                repo_alias="test-repo",
                username="testuser",
                file_paths=["file1.py"]
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_checkout_file.assert_called_once_with(
                Path("/path/to/repo"),
                file_path="file1.py"
            )

            assert result["success"] is True
            assert result["restored_file"] == "file1.py"

    # F6: Branch Management Wrapper Methods

    def test_list_branches_wrapper(self, service, mock_activated_repo_manager):
        """Test list_branches wrapper resolves alias and calls git_branch_list."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_branch_list') as mock_git_branch_list:
            mock_git_branch_list.return_value = {
                "current": "main",
                "local": ["main", "feature"],
                "remote": ["origin/main"]
            }

            result = service.list_branches(
                repo_alias="test-repo",
                username="testuser"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_branch_list.assert_called_once_with(
                Path("/path/to/repo")
            )

            assert result["success"] is True
            assert result["current"] == "main"

    def test_create_branch_wrapper(self, service, mock_activated_repo_manager):
        """Test create_branch wrapper resolves alias and calls git_branch_create."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_branch_create') as mock_git_branch_create:
            mock_git_branch_create.return_value = {
                "success": True,
                "created_branch": "feature-branch"
            }

            result = service.create_branch(
                repo_alias="test-repo",
                username="testuser",
                branch_name="feature-branch"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_branch_create.assert_called_once_with(
                Path("/path/to/repo"),
                branch_name="feature-branch"
            )

            assert result["success"] is True
            assert result["created_branch"] == "feature-branch"

    def test_switch_branch_wrapper(self, service, mock_activated_repo_manager):
        """Test switch_branch wrapper resolves alias and calls git_branch_switch."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_branch_switch') as mock_git_branch_switch:
            mock_git_branch_switch.return_value = {
                "success": True,
                "current_branch": "feature-branch",
                "previous_branch": "main"
            }

            result = service.switch_branch(
                repo_alias="test-repo",
                username="testuser",
                branch_name="feature-branch"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_branch_switch.assert_called_once_with(
                Path("/path/to/repo"),
                branch_name="feature-branch"
            )

            assert result["success"] is True
            assert result["current_branch"] == "feature-branch"

    def test_delete_branch_wrapper_requires_token(self, service, mock_activated_repo_manager):
        """Test delete_branch wrapper handles confirmation token requirement."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_branch_delete') as mock_git_branch_delete:
            mock_git_branch_delete.return_value = {
                "requires_confirmation": True,
                "token": "DEL123"
            }

            result = service.delete_branch(
                repo_alias="test-repo",
                username="testuser",
                branch_name="old-feature"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_branch_delete.assert_called_once_with(
                Path("/path/to/repo"),
                branch_name="old-feature",
                confirmation_token=None
            )

            assert result["requires_confirmation"] is True
            assert "token" in result

    def test_delete_branch_wrapper_with_token(self, service, mock_activated_repo_manager):
        """Test delete_branch wrapper passes confirmation token to git_branch_delete."""
        service.activated_repo_manager = mock_activated_repo_manager
        mock_activated_repo_manager.get_activated_repo_path.return_value = "/path/to/repo"

        with patch.object(service, 'git_branch_delete') as mock_git_branch_delete:
            mock_git_branch_delete.return_value = {
                "success": True,
                "deleted_branch": "old-feature"
            }

            result = service.delete_branch(
                repo_alias="test-repo",
                username="testuser",
                branch_name="old-feature",
                confirmation_token="DEL123"
            )

            mock_activated_repo_manager.get_activated_repo_path.assert_called_once_with(
                username="testuser",
                user_alias="test-repo"
            )

            mock_git_branch_delete.assert_called_once_with(
                Path("/path/to/repo"),
                branch_name="old-feature",
                confirmation_token="DEL123"
            )

            assert result["success"] is True
            assert result["deleted_branch"] == "old-feature"
