"""
Unit tests for Git MCP Handlers - F6: Branch Management (Story #626).

Tests F6: Branch Management:
- git_branch_list: List all branches
- git_branch_create: Create new branch
- git_branch_switch: Switch to existing branch
- git_branch_delete: Delete branch

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


class TestGitBranchListHandler:
    """Test git_branch_list MCP handler (F6: Branch Management)."""

    @pytest.mark.asyncio
    async def test_git_branch_list_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git branch list operation."""
        mock_git_service.git_branch_list.return_value = {
            "branches": [
                {"name": "main", "current": True},
                {"name": "feature-x", "current": False},
                {"name": "bugfix-y", "current": False},
            ]
        }

        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.git_branch_list(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert len(data["branches"]) == 3
        assert data["branches"][0]["current"] is True
        mock_git_service.git_branch_list.assert_called_once_with(
            Path("/tmp/test-repo")
        )

    @pytest.mark.asyncio
    async def test_git_branch_list_missing_repository(self, mock_user):
        """Test git branch list with missing repository_alias parameter."""
        params = {}  # Missing repository_alias

        mcp_response = await handlers.git_branch_list(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]


class TestGitBranchCreateHandler:
    """Test git_branch_create MCP handler (F6: Branch Management)."""

    @pytest.mark.asyncio
    async def test_git_branch_create_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git branch create operation."""
        mock_git_service.git_branch_create.return_value = {
            "success": True,
            "branch_name": "feature-new",
        }

        params = {
            "repository_alias": "test-repo",
            "branch_name": "feature-new",
        }

        mcp_response = await handlers.git_branch_create(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["branch_name"] == "feature-new"
        mock_git_service.git_branch_create.assert_called_once_with(
            Path("/tmp/test-repo"), "feature-new"
        )

    @pytest.mark.asyncio
    async def test_git_branch_create_already_exists(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git branch create when branch already exists."""
        error = GitCommandError(
            message="git branch failed",
            stderr="fatal: A branch named 'feature-new' already exists.",
            returncode=128,
            command=["git", "branch", "feature-new"],
        )
        mock_git_service.git_branch_create.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "branch_name": "feature-new",
        }

        mcp_response = await handlers.git_branch_create(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "already exists" in data["stderr"]

    @pytest.mark.asyncio
    async def test_git_branch_create_missing_parameters(self, mock_user):
        """Test git branch create with missing required parameters."""
        # Missing repository_alias
        params = {"branch_name": "new-branch"}
        mcp_response = await handlers.git_branch_create(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

        # Missing branch_name
        params = {"repository_alias": "test-repo"}
        mcp_response = await handlers.git_branch_create(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: branch_name" in data["error"]


class TestGitBranchSwitchHandler:
    """Test git_branch_switch MCP handler (F6: Branch Management)."""

    @pytest.mark.asyncio
    async def test_git_branch_switch_success(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test successful git branch switch operation."""
        mock_git_service.git_branch_switch.return_value = {
            "success": True,
            "branch_name": "feature-x",
        }

        params = {
            "repository_alias": "test-repo",
            "branch_name": "feature-x",
        }

        mcp_response = await handlers.git_branch_switch(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["branch_name"] == "feature-x"
        mock_git_service.git_branch_switch.assert_called_once_with(
            Path("/tmp/test-repo"), "feature-x"
        )

    @pytest.mark.asyncio
    async def test_git_branch_switch_nonexistent(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git branch switch to nonexistent branch."""
        error = GitCommandError(
            message="git switch failed",
            stderr="fatal: invalid reference: nonexistent-branch",
            returncode=128,
            command=["git", "switch", "nonexistent-branch"],
        )
        mock_git_service.git_branch_switch.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "branch_name": "nonexistent-branch",
        }

        mcp_response = await handlers.git_branch_switch(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "invalid reference" in data["stderr"]

    @pytest.mark.asyncio
    async def test_git_branch_switch_missing_parameters(self, mock_user):
        """Test git branch switch with missing required parameters."""
        # Missing repository_alias
        params = {"branch_name": "main"}
        mcp_response = await handlers.git_branch_switch(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

        # Missing branch_name
        params = {"repository_alias": "test-repo"}
        mcp_response = await handlers.git_branch_switch(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: branch_name" in data["error"]


class TestGitBranchDeleteHandler:
    """Test git_branch_delete MCP handler (F6: Branch Management)."""

    @pytest.mark.asyncio
    async def test_git_branch_delete_requires_confirmation(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git branch delete requires confirmation token."""
        mock_git_service.git_branch_delete.side_effect = ValueError(
            "Confirmation token required for branch deletion"
        )
        # Mock generate_confirmation_token to return a string
        mock_git_service.generate_confirmation_token.return_value = "DEL789"

        params = {
            "repository_alias": "test-repo",
            "branch_name": "old-feature",
        }

        mcp_response = await handlers.git_branch_delete(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "confirmation_token_required" in data
        assert data["confirmation_token_required"]["token"] == "DEL789"

    @pytest.mark.asyncio
    async def test_git_branch_delete_with_valid_token(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git branch delete with valid confirmation token."""
        mock_git_service.git_branch_delete.return_value = {
            "success": True,
            "deleted_branch": "old-feature",
        }

        params = {
            "repository_alias": "test-repo",
            "branch_name": "old-feature",
            "confirmation_token": "DEL123",
        }

        mcp_response = await handlers.git_branch_delete(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["deleted_branch"] == "old-feature"
        mock_git_service.git_branch_delete.assert_called_once_with(
            Path("/tmp/test-repo"), "old-feature", confirmation_token="DEL123"
        )

    @pytest.mark.asyncio
    async def test_git_branch_delete_current_branch(
        self, mock_user, mock_git_service, mock_repo_manager
    ):
        """Test git branch delete when trying to delete current branch."""
        error = GitCommandError(
            message="git branch delete failed",
            stderr="error: Cannot delete branch 'main' checked out at '/repo'",
            returncode=1,
            command=["git", "branch", "-d", "main"],
        )
        mock_git_service.git_branch_delete.side_effect = error

        params = {
            "repository_alias": "test-repo",
            "branch_name": "main",
            "confirmation_token": "ABC123",
        }

        mcp_response = await handlers.git_branch_delete(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert data["error_type"] == "GitCommandError"
        assert "cannot delete" in data["stderr"].lower()

    @pytest.mark.asyncio
    async def test_git_branch_delete_missing_parameters(self, mock_user):
        """Test git branch delete with missing required parameters."""
        # Missing repository_alias
        params = {"branch_name": "old-feature"}
        mcp_response = await handlers.git_branch_delete(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: repository_alias" in data["error"]

        # Missing branch_name
        params = {"repository_alias": "test-repo"}
        mcp_response = await handlers.git_branch_delete(params, mock_user)
        data = _extract_response_data(mcp_response)
        assert data["success"] is False
        assert "Missing required parameter: branch_name" in data["error"]
