"""
Unit tests for Git MCP Handlers (Story #626 - F2 & F3).

Tests F2: Status/Inspection operations:
- git_status: Get repository status (staged, unstaged, untracked)
- git_diff: Get diff output
- git_log: Get commit history

Tests F3: Staging/Commit operations:
- git_stage: Stage files for commit
- git_unstage: Unstage files
- git_commit: Create commit with dual attribution

All tests use mocked GitOperationsService to avoid real git operations.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import cast
from unittest.mock import patch
import pytest

from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.git_operations_service import GitCommandError


@pytest.fixture
def mock_user():
    """Create mock user for testing."""
    return User(
        username="testuser",
        role=UserRole.NORMAL_USER,
        password_hash="dummy_hash",
        created_at=datetime.now(),
        email="testuser@example.com",
    )


@pytest.fixture
def mock_git_service():
    """Create mock GitOperationsService."""
    with patch(
        "code_indexer.server.mcp.handlers.git_operations_service"
    ) as mock_service:
        yield mock_service


@pytest.fixture
def mock_repo_manager():
    """Create mock ActivatedRepoManager."""
    with patch("code_indexer.server.mcp.handlers.ActivatedRepoManager") as MockClass:
        mock_instance = MockClass.return_value
        mock_instance.get_activated_repo_path.return_value = Path("/tmp/test-repo")
        yield mock_instance


def _extract_response_data(mcp_response: dict) -> dict:
    """Extract actual response data from MCP wrapper."""
    content = mcp_response["content"][0]
    return cast(dict, json.loads(content["text"]))


class TestGitStatusHandler:
    """Test git_status MCP handler."""

    @pytest.mark.asyncio
    async def test_git_status_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git status operation."""
        from code_indexer.server.mcp import handlers

        # Mock GitOperationsService response
        mock_git_service.git_status.return_value = {
            "staged": ["file1.py"],
            "unstaged": ["file2.py"],
            "untracked": ["file3.py"],
        }

        params = {"repository_alias": "test-repo"}

        # Execute handler
        mcp_response = await handlers.git_status(params, mock_user)
        data = _extract_response_data(mcp_response)

        # Verify response
        assert data["success"] is True
        assert data["staged"] == ["file1.py"]
        assert data["unstaged"] == ["file2.py"]
        assert data["untracked"] == ["file3.py"]

        # Verify service was called correctly
        mock_git_service.git_status.assert_called_once_with(Path("/tmp/test-repo"))

    @pytest.mark.asyncio
    async def test_git_status_missing_repository(self, mock_user):
        """Test git status with missing repository_alias parameter."""
        from code_indexer.server.mcp import handlers

        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_status(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

    @pytest.mark.asyncio
    async def test_git_status_git_command_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git status with GitCommandError."""
        from code_indexer.server.mcp import handlers

        # Mock GitCommandError
        error = GitCommandError(
            message="git status failed",
            stderr="fatal: not a git repository",
            returncode=128,
            command=["git", "status"],
        )
        mock_git_service.git_status.side_effect = error

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_status(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert data["stderr"] == "fatal: not a git repository"
        assert data["command"] == ["git", "status"]


class TestGitDiffHandler:
    """Test git_diff MCP handler."""

    @pytest.mark.asyncio
    async def test_git_diff_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git diff operation."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_diff.return_value = {
            "diff_text": "diff --git a/file.py b/file.py\n...",
            "files_changed": 1,
        }

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_diff(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert "diff --git" in data["diff_text"]
        assert data["files_changed"] == 1

    @pytest.mark.asyncio
    async def test_git_diff_with_file_paths(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git diff with specific file paths."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_diff.return_value = {
            "diff_text": "diff --git a/specific.py b/specific.py\n...",
            "files_changed": 1,
        }

        params = {"repository_alias": "test-repo", "file_paths": ["specific.py"]}

        mcp_response = await handlers.git_diff(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        mock_git_service.git_diff.assert_called_once_with(
            Path("/tmp/test-repo"), file_paths=["specific.py"]
        )

    @pytest.mark.asyncio
    async def test_git_diff_missing_repository(self, mock_user):
        """Test git diff with missing repository_alias parameter."""
        from code_indexer.server.mcp import handlers

        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_diff(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitLogHandler:
    """Test git_log MCP handler."""

    @pytest.mark.asyncio
    async def test_git_log_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git log operation."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_log.return_value = {
            "commits": [
                {
                    "commit_hash": "abc123",
                    "author": "John Doe",
                    "date": "2025-01-01",
                    "message": "Initial commit",
                }
            ]
        }

        params = {"repository_alias": "test-repo", "limit": 10}

        mcp_response = await handlers.git_log(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert len(data["commits"]) == 1
        assert data["commits"][0]["commit_hash"] == "abc123"

    @pytest.mark.asyncio
    async def test_git_log_with_since_date(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git log with since_date filter."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_log.return_value = {"commits": []}

        params = {
            "repository_alias": "test-repo",
            "limit": 10,
            "since_date": "2025-01-10",
        }

        mcp_response = await handlers.git_log(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        mock_git_service.git_log.assert_called_once_with(
            Path("/tmp/test-repo"), limit=10, since_date="2025-01-10"
        )

    @pytest.mark.asyncio
    async def test_git_log_default_limit(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git log uses default limit when not specified."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_log.return_value = {"commits": []}

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_log(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        # Verify default limit (10) was used
        mock_git_service.git_log.assert_called_once_with(
            Path("/tmp/test-repo"), limit=10, since_date=None
        )

    @pytest.mark.asyncio
    async def test_git_log_missing_repository(self, mock_user):
        """Test git log with missing repository_alias parameter."""
        from code_indexer.server.mcp import handlers

        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_log(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitStageHandler:
    """Test git_stage MCP handler (F3: Staging/Commit)."""

    @pytest.mark.asyncio
    async def test_git_stage_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git stage operation."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_stage.return_value = {
            "success": True,
            "staged_files": ["file1.py", "file2.py"],
        }

        params = {
            "repository_alias": "test-repo",
            "file_paths": ["file1.py", "file2.py"],
        }

        mcp_response = await handlers.git_stage(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["staged_files"] == ["file1.py", "file2.py"]
        mock_git_service.git_stage.assert_called_once_with(
            Path("/tmp/test-repo"), ["file1.py", "file2.py"]
        )

    @pytest.mark.asyncio
    async def test_git_stage_missing_parameters(self, mock_user):
        """Test git stage with missing required parameters."""
        from code_indexer.server.mcp import handlers

        # Missing repository_alias
        params = {"file_paths": ["file1.py"]}
        mcp_response = await handlers.git_stage(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

        # Missing file_paths
        params = {"repository_alias": "test-repo"}
        mcp_response = await handlers.git_stage(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: file_paths" in data["error"]

    @pytest.mark.asyncio
    async def test_git_stage_git_command_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git stage with GitCommandError."""
        from code_indexer.server.mcp import handlers

        error = GitCommandError(
            message="git add failed",
            stderr="fatal: pathspec 'nonexistent.py' did not match any files",
            returncode=128,
            command=["git", "add", "nonexistent.py"],
        )
        mock_git_service.git_stage.side_effect = error

        params = {"repository_alias": "test-repo", "file_paths": ["nonexistent.py"]}

        mcp_response = await handlers.git_stage(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "pathspec" in data["stderr"]


class TestGitUnstageHandler:
    """Test git_unstage MCP handler (F3: Staging/Commit)."""

    @pytest.mark.asyncio
    async def test_git_unstage_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git unstage operation."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_unstage.return_value = {
            "success": True,
            "unstaged_files": ["file1.py"],
        }

        params = {"repository_alias": "test-repo", "file_paths": ["file1.py"]}

        mcp_response = await handlers.git_unstage(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["unstaged_files"] == ["file1.py"]
        mock_git_service.git_unstage.assert_called_once_with(
            Path("/tmp/test-repo"), ["file1.py"]
        )

    @pytest.mark.asyncio
    async def test_git_unstage_missing_parameters(self, mock_user):
        """Test git unstage with missing required parameters."""
        from code_indexer.server.mcp import handlers

        params = {}  # Missing both parameters
        mcp_response = await handlers.git_unstage(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter" in data["error"]

    @pytest.mark.asyncio
    async def test_git_unstage_git_command_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git unstage with GitCommandError."""
        from code_indexer.server.mcp import handlers

        error = GitCommandError(
            message="git reset failed",
            stderr="fatal: ambiguous argument 'HEAD'",
            returncode=128,
            command=["git", "reset", "HEAD", "file.py"],
        )
        mock_git_service.git_unstage.side_effect = error

        params = {"repository_alias": "test-repo", "file_paths": ["file.py"]}

        mcp_response = await handlers.git_unstage(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"


class TestGitCommitHandler:
    """Test git_commit MCP handler (F3: Staging/Commit)."""

    @pytest.mark.asyncio
    async def test_git_commit_success_with_email_extraction(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git commit with email extracted from User object."""
        from code_indexer.server.mcp import handlers

        mock_git_service.git_commit.return_value = {
            "success": True,
            "commit_hash": "abc123",
            "message": "Test commit",
            "author": "testuser@example.com",
            "committer": "service@cidx.local",
        }

        params = {"repository_alias": "test-repo", "message": "Test commit"}

        mcp_response = await handlers.git_commit(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["commit_hash"] == "abc123"
        assert data["author"] == "testuser@example.com"

        # Verify service was called with extracted email
        mock_git_service.git_commit.assert_called_once_with(
            Path("/tmp/test-repo"),
            "Test commit",
            "testuser@example.com",
            "testuser",  # Derived from username
        )

    @pytest.mark.asyncio
    async def test_git_commit_missing_parameters(self, mock_user):
        """Test git commit with missing required parameters."""
        from code_indexer.server.mcp import handlers

        params = {}  # Missing both parameters
        mcp_response = await handlers.git_commit(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter" in data["error"]

    @pytest.mark.asyncio
    async def test_git_commit_git_command_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git commit with GitCommandError."""
        from code_indexer.server.mcp import handlers

        error = GitCommandError(
            message="git commit failed",
            stderr="fatal: nothing to commit",
            returncode=1,
            command=["git", "commit", "-m", "Empty commit"],
        )
        mock_git_service.git_commit.side_effect = error

        params = {"repository_alias": "test-repo", "message": "Empty commit"}

        mcp_response = await handlers.git_commit(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "nothing to commit" in data["stderr"]
