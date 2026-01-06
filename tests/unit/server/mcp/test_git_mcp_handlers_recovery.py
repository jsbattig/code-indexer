"""
Unit tests for Git MCP Handlers - F5: Recovery Operations (Story #626).

Tests F5: Recovery Operations:
- git_reset: Reset working tree
- git_clean: Remove untracked files
- git_merge_abort: Abort merge in progress
- git_checkout_file: Restore file from HEAD

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
from code_indexer.server.mcp import handlers


@pytest.fixture
def mock_user():
    """Create mock user for testing."""
    return User(
        username="testuser",
        role=UserRole.NORMAL_USER,
        password_hash="dummy_hash",
        created_at=datetime.now(),
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


class TestGitResetHandler:
    """Test git_reset MCP handler (F5: Recovery Operations)."""

    @pytest.mark.asyncio
    async def test_git_reset_soft_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git reset --soft operation."""
        mock_git_service.git_reset.return_value = {
            "success": True,
            "mode": "soft",
            "target": "HEAD~1",
        }

        params = {
            "repository_alias": "test-repo",
            "mode": "soft",
            "target": "HEAD~1",
        }

        mcp_response = await handlers.git_reset(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["mode"] == "soft"
        mock_git_service.git_reset.assert_called_once_with(
            Path("/tmp/test-repo"),
            mode="soft",
            target="HEAD~1",
            confirmation_token=None,
        )

    @pytest.mark.asyncio
    async def test_git_reset_hard_requires_confirmation(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git reset --hard requires confirmation token."""
        # Without confirmation token, should get token requirement error
        mock_git_service.git_reset.side_effect = ValueError(
            "Confirmation token required for hard reset"
        )
        # Mock generate_confirmation_token to return a string
        mock_git_service.generate_confirmation_token.return_value = "TEST123"

        params = {
            "repository_alias": "test-repo",
            "mode": "hard",
            "target": "HEAD",
        }

        mcp_response = await handlers.git_reset(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "confirmation_token_required" in data
        assert data["confirmation_token_required"]["token"] == "TEST123"

    @pytest.mark.asyncio
    async def test_git_reset_hard_with_valid_token(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git reset --hard with valid confirmation token."""
        mock_git_service.git_reset.return_value = {
            "success": True,
            "mode": "hard",
            "target": "HEAD",
        }

        params = {
            "repository_alias": "test-repo",
            "mode": "hard",
            "target": "HEAD",
            "confirmation_token": "ABC123",
        }

        mcp_response = await handlers.git_reset(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["mode"] == "hard"
        mock_git_service.git_reset.assert_called_once_with(
            Path("/tmp/test-repo"),
            mode="hard",
            target="HEAD",
            confirmation_token="ABC123",
        )

    @pytest.mark.asyncio
    async def test_git_reset_missing_repository(self, mock_user):
        """Test git reset with missing repository_alias parameter."""
        params = {"mode": "soft"}  # Missing repository_alias

        mcp_response = await handlers.git_reset(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitCleanHandler:
    """Test git_clean MCP handler (F5: Recovery Operations)."""

    @pytest.mark.asyncio
    async def test_git_clean_requires_confirmation(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git clean requires confirmation token."""
        mock_git_service.git_clean.side_effect = ValueError(
            "Confirmation token required for git clean"
        )
        # Mock generate_confirmation_token to return a string
        mock_git_service.generate_confirmation_token.return_value = "CLEAN456"

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_clean(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "confirmation_token_required" in data
        assert data["confirmation_token_required"]["token"] == "CLEAN456"

    @pytest.mark.asyncio
    async def test_git_clean_with_valid_token(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git clean with valid confirmation token."""
        mock_git_service.git_clean.return_value = {
            "success": True,
            "removed_files": ["build/", "temp.txt"],
        }

        params = {
            "repository_alias": "test-repo",
            "confirmation_token": "XYZ789",
        }

        mcp_response = await handlers.git_clean(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert len(data["removed_files"]) == 2
        mock_git_service.git_clean.assert_called_once_with(
            Path("/tmp/test-repo"), confirmation_token="XYZ789"
        )

    @pytest.mark.asyncio
    async def test_git_clean_missing_repository(self, mock_user):
        """Test git clean with missing repository_alias parameter."""
        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_clean(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitMergeAbortHandler:
    """Test git_merge_abort MCP handler (F5: Recovery Operations)."""

    @pytest.mark.asyncio
    async def test_git_merge_abort_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git merge --abort operation."""
        mock_git_service.git_merge_abort.return_value = {
            "success": True,
            "message": "Merge aborted successfully",
        }

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_merge_abort(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert "aborted" in data["message"].lower()
        mock_git_service.git_merge_abort.assert_called_once_with(Path("/tmp/test-repo"))

    @pytest.mark.asyncio
    async def test_git_merge_abort_no_merge_in_progress(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git merge abort when no merge is in progress."""
        error = GitCommandError(
            message="git merge --abort failed",
            stderr="fatal: There is no merge in progress (MERGE_HEAD missing).",
            returncode=128,
            command=["git", "merge", "--abort"],
        )
        mock_git_service.git_merge_abort.side_effect = error

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_merge_abort(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "no merge in progress" in data["stderr"].lower()

    @pytest.mark.asyncio
    async def test_git_merge_abort_missing_repository(self, mock_user):
        """Test git merge abort with missing repository_alias parameter."""
        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_merge_abort(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitCheckoutFileHandler:
    """Test git_checkout_file MCP handler (F5: Recovery Operations)."""

    @pytest.mark.asyncio
    async def test_git_checkout_file_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git checkout file operation."""
        mock_git_service.git_checkout_file.return_value = {
            "success": True,
            "restored_file": "src/main.py",
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/main.py",
        }

        mcp_response = await handlers.git_checkout_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["restored_file"] == "src/main.py"
        mock_git_service.git_checkout_file.assert_called_once_with(
            Path("/tmp/test-repo"), "src/main.py"
        )

    @pytest.mark.asyncio
    async def test_git_checkout_file_nonexistent(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git checkout file for nonexistent file."""
        error = GitCommandError(
            message="git checkout failed",
            stderr="error: pathspec 'nonexistent.py' did not match any file(s) known to git",
            returncode=1,
            command=["git", "checkout", "HEAD", "--", "nonexistent.py"],
        )
        mock_git_service.git_checkout_file.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "file_path": "nonexistent.py",
        }

        mcp_response = await handlers.git_checkout_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "did not match" in data["stderr"]

    @pytest.mark.asyncio
    async def test_git_checkout_file_missing_parameters(self, mock_user):
        """Test git checkout file with missing required parameters."""
        # Missing repository_alias
        params = {"file_path": "test.py"}
        mcp_response = await handlers.git_checkout_file(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

        # Missing file_path
        params = {"repository_alias": "test-repo"}
        mcp_response = await handlers.git_checkout_file(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: file_path" in data["error"]
