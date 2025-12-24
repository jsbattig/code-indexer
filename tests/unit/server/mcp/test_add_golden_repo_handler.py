"""Unit tests for add_golden_repo MCP handler parameter mapping."""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.mcp.handlers import add_golden_repo
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing."""
    user = Mock(spec=User)
    user.username = "admin"
    user.role = UserRole.ADMIN
    user.has_permission = Mock(return_value=True)
    return user


@pytest.mark.asyncio
class TestAddGoldenRepoParameterMapping:
    """Test add_golden_repo handler parameter mapping to golden_repo_manager.add_golden_repo()."""

    async def test_handler_calls_manager_with_correct_parameters(self, mock_admin_user):
        """Test that handler maps MCP parameters to manager method correctly."""
        mcp_params = {
            "url": "https://github.com/user/repo.git",
            "alias": "my-golden-repo",
            "branch": "develop",
        }

        with patch("code_indexer.server.app.golden_repo_manager") as mock_manager:
            # Mock the add_golden_repo method to return job_id (async behavior)
            mock_manager.add_golden_repo = Mock(return_value="test-job-id-12345")

            result = await add_golden_repo(mcp_params, mock_admin_user)

            # Verify the handler called the manager with correct parameter names
            mock_manager.add_golden_repo.assert_called_once_with(
                repo_url="https://github.com/user/repo.git",
                alias="my-golden-repo",
                default_branch="develop",
                enable_temporal=False,
                temporal_options=None,
                submitter_username="admin",
            )

            # Verify the handler returned success with job_id
            assert result["content"][0]["type"] == "text"
            response_content = result["content"][0]["text"]
            import json

            response_data = json.loads(response_content)
            assert response_data["success"] is True
            assert response_data["job_id"] == "test-job-id-12345"
            assert "addition started" in response_data["message"]
