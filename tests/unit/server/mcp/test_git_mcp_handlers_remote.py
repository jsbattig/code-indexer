"""
Unit tests for Git MCP Handlers - F4: Remote Operations (Story #626).

Tests F4: Remote Operations:
- git_push: Push commits to remote
- git_pull: Pull updates from remote (detect merge conflicts)
- git_fetch: Fetch refs from remote

All tests use mocked GitOperationsService to avoid real git operations.
"""

import json
from datetime import datetime
from pathlib import Path
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
    with patch(
        "code_indexer.server.mcp.handlers.ActivatedRepoManager"
    ) as MockClass:
        mock_instance = MockClass.return_value
        mock_instance.get_activated_repo_path.return_value = Path("/tmp/test-repo")
        yield mock_instance


def _extract_response_data(mcp_response: dict) -> dict:
    """Extract actual response data from MCP wrapper."""
    content = mcp_response["content"][0]
    return json.loads(content["text"])


class TestGitPushHandler:
    """Test git_push MCP handler (F4: Remote Operations)."""

    @pytest.mark.asyncio
    async def test_git_push_success(self, mock_user, mock_git_service, mock_repo_manager):
        """Test successful git push operation."""
        # Bug #639: Mock wrapper method instead of low-level git_push
        mock_git_service.push_to_remote.return_value = {
            "success": True,
            "pushed_commits": 3,
            "remote": "origin",
            "branch": "main",
        }

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_push(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["pushed_commits"] == 3
        assert data["remote"] == "origin"
        mock_git_service.push_to_remote.assert_called_once_with(
            repo_alias="test-repo",
            username="testuser",
            remote="origin",
            branch="main"
        )

    @pytest.mark.asyncio
    async def test_git_push_authentication_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git push with authentication error."""
        error = GitCommandError(
            message="git push failed",
            stderr="fatal: Authentication failed for 'https://github.com/user/repo.git'",
            returncode=128,
            command=["git", "push", "origin", "main"],
        )
        # Bug #639: Mock wrapper method instead of low-level git_push
        mock_git_service.push_to_remote.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_push(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "Authentication failed" in data["stderr"]

    @pytest.mark.asyncio
    async def test_git_push_network_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git push with network connectivity error."""
        error = GitCommandError(
            message="git push failed",
            stderr="fatal: unable to access 'https://github.com/user/repo.git/': Could not resolve host",
            returncode=128,
            command=["git", "push", "origin", "main"],
        )
        # Bug #639: Mock wrapper method instead of low-level git_push
        mock_git_service.push_to_remote.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_push(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "unable to access" in data["stderr"]


class TestGitPullHandler:
    """Test git_pull MCP handler (F4: Remote Operations)."""

    @pytest.mark.asyncio
    async def test_git_pull_success(self, mock_user, mock_git_service, mock_repo_manager):
        """Test successful git pull operation."""
        # Bug #639: Mock wrapper method instead of low-level git_pull
        mock_git_service.pull_from_remote.return_value = {
            "success": True,
            "fetched_commits": 2,
            "remote": "origin",
            "branch": "main",
        }

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_pull(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["fetched_commits"] == 2
        mock_git_service.pull_from_remote.assert_called_once_with(
            repo_alias="test-repo",
            username="testuser",
            remote="origin",
            branch="main"
        )

    @pytest.mark.asyncio
    async def test_git_pull_merge_conflicts(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git pull with merge conflicts detected."""
        # Bug #639: Mock wrapper method instead of low-level git_pull
        mock_git_service.pull_from_remote.return_value = {
            "success": True,
            "conflicts": ["file1.py", "file2.py"],
            "message": "Merge conflicts detected",
        }

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_pull(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert "conflicts" in data
        assert data["conflicts"] == ["file1.py", "file2.py"]

    @pytest.mark.asyncio
    async def test_git_pull_network_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git pull with network error."""
        error = GitCommandError(
            message="git pull failed",
            stderr="fatal: unable to access 'https://github.com/user/repo.git/': Operation timed out",
            returncode=128,
            command=["git", "pull", "origin", "main"],
        )
        # Bug #639: Mock wrapper method instead of low-level git_pull
        mock_git_service.pull_from_remote.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
            "branch": "main",
        }

        mcp_response = await handlers.git_pull(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "unable to access" in data["stderr"]


class TestGitFetchHandler:
    """Test git_fetch MCP handler (F4: Remote Operations)."""

    @pytest.mark.asyncio
    async def test_git_fetch_success(self, mock_user, mock_git_service, mock_repo_manager):
        """Test successful git fetch operation."""
        # Bug #639: Mock wrapper method instead of low-level git_fetch
        mock_git_service.fetch_from_remote.return_value = {
            "success": True,
            "remote": "origin",
            "refs_updated": 5,
        }

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
        }

        mcp_response = await handlers.git_fetch(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["refs_updated"] == 5
        mock_git_service.fetch_from_remote.assert_called_once_with(
            repo_alias="test-repo",
            username="testuser",
            remote="origin"
        )

    @pytest.mark.asyncio
    async def test_git_fetch_network_error(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git fetch with network error."""
        error = GitCommandError(
            message="git fetch failed",
            stderr="fatal: unable to access 'https://github.com/user/repo.git/': Connection refused",
            returncode=128,
            command=["git", "fetch", "origin"],
        )
        # Bug #639: Mock wrapper method instead of low-level git_fetch
        mock_git_service.fetch_from_remote.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "remote": "origin",
        }

        mcp_response = await handlers.git_fetch(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "unable to access" in data["stderr"]
