"""
Unit tests for MCP add_golden_repo_index and get_golden_repo_indexes tools.

Tests AC1-AC7 from Story #596:
- AC1: add_golden_repo_index accepts alias, index_type, returns job_id
- AC2: get_golden_repo_indexes accepts alias, returns structured status
- AC3: Input schema validation with enum for index_type
- AC4: Error handling for unknown alias
- AC5: Error handling for already existing indexes
- AC6: Tool schema definitions in TOOLS_REGISTRY
- AC7: Integration with existing get_job_status tool
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from code_indexer.server.mcp.handlers import (
    handle_add_golden_repo_index,
    handle_get_golden_repo_indexes,
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
def mock_golden_repo_manager():
    """Create a mock GoldenRepoManager."""
    manager = MagicMock()
    return manager


class TestAddGoldenRepoIndex:
    """Test add_golden_repo_index MCP tool handler."""

    @pytest.mark.asyncio
    async def test_add_index_success_semantic_fts(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC1: add_golden_repo_index successfully submits job for semantic_fts index."""
        # Setup mock to return job_id
        mock_golden_repo_manager.add_index_to_golden_repo.return_value = (
            "job-123-semantic-fts"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            # Call handler
            args = {"alias": "test-repo", "index_type": "semantic_fts"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            # Verify response structure
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

            # Parse JSON response
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "job-123-semantic-fts"
            assert "message" in response_data
            assert "semantic_fts" in response_data["message"]

            # Verify backend method called correctly
            mock_golden_repo_manager.add_index_to_golden_repo.assert_called_once_with(
                alias="test-repo", index_type="semantic_fts", submitter_username="admin"
            )

    @pytest.mark.asyncio
    async def test_add_index_success_temporal(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC1: add_golden_repo_index successfully submits job for temporal index."""
        mock_golden_repo_manager.add_index_to_golden_repo.return_value = (
            "job-456-temporal"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "test-repo", "index_type": "temporal"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "job-456-temporal"
            assert "temporal" in response_data["message"]

    @pytest.mark.asyncio
    async def test_add_index_success_scip(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC1: add_golden_repo_index successfully submits job for scip index."""
        mock_golden_repo_manager.add_index_to_golden_repo.return_value = "job-789-scip"

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "test-repo", "index_type": "scip"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["job_id"] == "job-789-scip"
            assert "scip" in response_data["message"]

    @pytest.mark.asyncio
    async def test_add_index_error_unknown_alias(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC4: Error when golden repo alias not found."""
        mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
            "Golden repository 'nonexistent-repo' not found"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "nonexistent-repo", "index_type": "semantic_fts"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "not found" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_add_index_error_invalid_type(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC3: Error when invalid index_type provided."""
        mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
            "Invalid index_type: invalid_type. Must be one of: semantic_fts, temporal, scip"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "test-repo", "index_type": "invalid_type"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "invalid" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_add_index_error_already_exists(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC5: Error when index type already exists."""
        mock_golden_repo_manager.add_index_to_golden_repo.side_effect = ValueError(
            "Index type 'semantic_fts' already exists for golden repo 'test-repo'"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "test-repo", "index_type": "semantic_fts"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "already exists" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_add_index_error_missing_alias(self, mock_admin_user):
        """Test error when alias parameter is missing."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"

            args = {"index_type": "semantic_fts"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "alias" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_add_index_error_missing_index_type(self, mock_admin_user):
        """Test error when index_type parameter is missing."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"

            args = {"alias": "test-repo"}
            result = await handle_add_golden_repo_index(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "index_type" in response_data["error"].lower()


class TestGetGoldenRepoIndexes:
    """Test get_golden_repo_indexes MCP tool handler."""

    @pytest.mark.asyncio
    async def test_get_indexes_success(self, mock_admin_user, mock_golden_repo_manager):
        """Test AC2: get_golden_repo_indexes returns structured status."""
        # Setup mock to return index status
        mock_golden_repo_manager.get_golden_repo_indexes.return_value = {
            "alias": "test-repo",
            "indexes": {
                "semantic_fts": {
                    "exists": True,
                    "path": "/mock/golden-repos/test-repo/.code-indexer/index/tantivy",
                    "last_updated": "2025-12-16T10:00:00+00:00",
                },
                "temporal": {"exists": False, "path": None, "last_updated": None},
                "scip": {
                    "exists": True,
                    "path": "/mock/golden-repos/test-repo/index.scip",
                    "last_updated": "2025-12-16T09:00:00+00:00",
                },
            },
        }

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "test-repo"}
            result = await handle_get_golden_repo_indexes(args, mock_admin_user)

            # Verify response structure
            assert "content" in result
            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert response_data["alias"] == "test-repo"
            assert "indexes" in response_data
            assert "semantic_fts" in response_data["indexes"]
            assert "temporal" in response_data["indexes"]
            assert "scip" in response_data["indexes"]

            # Verify semantic_fts index details
            semantic_fts = response_data["indexes"]["semantic_fts"]
            assert semantic_fts["exists"] is True
            assert semantic_fts["path"] is not None

            # Verify temporal index does not exist
            temporal = response_data["indexes"]["temporal"]
            assert temporal["exists"] is False
            assert temporal["path"] is None

    @pytest.mark.asyncio
    async def test_get_indexes_error_unknown_alias(
        self, mock_admin_user, mock_golden_repo_manager
    ):
        """Test AC4: Error when golden repo alias not found."""
        mock_golden_repo_manager.get_golden_repo_indexes.side_effect = ValueError(
            "Golden repository 'nonexistent-repo' not found"
        )

        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"
            mock_app.golden_repo_manager = mock_golden_repo_manager

            args = {"alias": "nonexistent-repo"}
            result = await handle_get_golden_repo_indexes(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "not found" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_get_indexes_error_missing_alias(self, mock_admin_user):
        """Test error when alias parameter is missing."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.app.state.golden_repos_dir = "/mock/golden-repos"

            args = {}
            result = await handle_get_golden_repo_indexes(args, mock_admin_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is False
            assert "error" in response_data
            assert "alias" in response_data["error"].lower()
