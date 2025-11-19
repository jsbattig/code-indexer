"""Unit tests for golden repository MCP handlers parameter mapping and audit trail."""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import (
    add_golden_repo,
    remove_golden_repo,
    refresh_golden_repo,
)
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing."""
    user = Mock(spec=User)
    user.username = "admin"
    user.role = UserRole.ADMIN
    user.has_permission = Mock(return_value=True)
    return user


@pytest.fixture
def mock_regular_user():
    """Create a mock regular user for testing."""
    user = Mock(spec=User)
    user.username = "alice"
    user.role = UserRole.USER
    user.has_permission = Mock(return_value=False)
    return user


@pytest.mark.asyncio
class TestAddGoldenRepoHandler:
    """Test add_golden_repo handler parameter mapping and audit trail."""

    async def test_handler_passes_actual_username(self, mock_admin_user):
        """Test that handler passes actual user username (not hardcoded 'admin')."""
        mcp_params = {
            "url": "https://github.com/user/repo.git",
            "alias": "my-golden-repo",
            "branch": "develop",
        }

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.add_golden_repo = Mock(return_value="test-job-id-12345")

            result = await add_golden_repo(mcp_params, mock_admin_user)

            # Verify the handler called the manager with actual username
            mock_manager.add_golden_repo.assert_called_once_with(
                repo_url="https://github.com/user/repo.git",
                alias="my-golden-repo",
                default_branch="develop",
                submitter_username="admin",  # Actual username from user object
            )

            # Verify success response
            assert result["content"][0]["type"] == "text"
            import json
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "test-job-id-12345"

    async def test_handler_passes_different_username(self):
        """Test that handler passes different usernames correctly."""
        # Create user with different username
        user = Mock(spec=User)
        user.username = "bob"
        user.role = UserRole.ADMIN

        mcp_params = {
            "url": "https://github.com/user/repo.git",
            "alias": "my-golden-repo",
            "branch": "main",
        }

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.add_golden_repo = Mock(return_value="job-123")

            await add_golden_repo(mcp_params, user)

            # Verify correct username passed
            call_kwargs = mock_manager.add_golden_repo.call_args[1]
            assert call_kwargs["submitter_username"] == "bob"


@pytest.mark.asyncio
class TestRemoveGoldenRepoHandler:
    """Test remove_golden_repo handler parameter mapping and audit trail."""

    async def test_handler_passes_actual_username(self, mock_admin_user):
        """Test that handler passes actual user username to remove operation."""
        mcp_params = {"alias": "test-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.remove_golden_repo = Mock(return_value="test-job-id-67890")

            result = await remove_golden_repo(mcp_params, mock_admin_user)

            # Verify the handler called the manager with actual username
            mock_manager.remove_golden_repo.assert_called_once_with(
                "test-repo",
                submitter_username="admin",  # Actual username from user object
            )

            # Verify success response
            assert result["content"][0]["type"] == "text"
            import json
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "test-job-id-67890"

    async def test_handler_passes_different_username(self):
        """Test that handler passes different usernames correctly."""
        # Create user with different username
        user = Mock(spec=User)
        user.username = "charlie"
        user.role = UserRole.ADMIN

        mcp_params = {"alias": "test-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.remove_golden_repo = Mock(return_value="job-456")

            await remove_golden_repo(mcp_params, user)

            # Verify correct username passed
            mock_manager.remove_golden_repo.assert_called_once_with(
                "test-repo",
                submitter_username="charlie",  # Username from charlie's user object
            )


@pytest.mark.asyncio
class TestRefreshGoldenRepoHandler:
    """Test refresh_golden_repo handler parameter mapping and audit trail."""

    async def test_handler_passes_actual_username(self, mock_admin_user):
        """Test that handler passes actual user username to refresh operation."""
        mcp_params = {"alias": "test-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.refresh_golden_repo = Mock(return_value="test-job-id-11111")

            result = await refresh_golden_repo(mcp_params, mock_admin_user)

            # Verify the handler called the manager with actual username
            mock_manager.refresh_golden_repo.assert_called_once_with(
                "test-repo",
                submitter_username="admin",  # Actual username from user object
            )

            # Verify success response
            assert result["content"][0]["type"] == "text"
            import json
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "test-job-id-11111"

    async def test_handler_passes_different_username(self):
        """Test that handler passes different usernames correctly."""
        # Create user with different username
        user = Mock(spec=User)
        user.username = "dave"
        user.role = UserRole.ADMIN

        mcp_params = {"alias": "test-repo"}

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            mock_manager.refresh_golden_repo = Mock(return_value="job-789")

            await refresh_golden_repo(mcp_params, user)

            # Verify correct username passed
            mock_manager.refresh_golden_repo.assert_called_once_with(
                "test-repo",
                submitter_username="dave",  # Username from dave's user object
            )
