"""Unit tests for MCP re-indexing handlers."""

import pytest
from unittest.mock import Mock, patch
from code_indexer.server.auth.user_manager import User, UserRole
import json


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


@pytest.mark.asyncio
class TestTriggerReindexHandler:
    """Test trigger_reindex handler."""

    async def test_trigger_reindex_success(self, mock_user):
        """Test successful reindex job creation."""
        from code_indexer.server.mcp.handlers import trigger_reindex

        params = {
            "repository_alias": "my-repo",
            "index_types": ["semantic", "fts"],
            "clear": False,
        }

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.trigger_reindex.return_value = "job-123"
            MockManager.return_value = mock_manager

            result = await trigger_reindex(params, mock_user)

            # Parse MCP response
            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["job_id"] == "job-123"
            assert data["status"] == "queued"
            assert data["index_types"] == ["semantic", "fts"]
            assert "started_at" in data
            assert "estimated_duration_minutes" in data

            # Verify service call
            mock_manager.trigger_reindex.assert_called_once_with(
                repo_alias="my-repo",
                index_types=["semantic", "fts"],
                clear=False,
                username="testuser",
            )

    async def test_trigger_reindex_invalid_index_type(self, mock_user):
        """Test reindex with invalid index type."""
        from code_indexer.server.mcp.handlers import trigger_reindex

        params = {
            "repository_alias": "my-repo",
            "index_types": ["semantic", "invalid_type"],
            "clear": False,
        }

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.trigger_reindex.side_effect = ValueError(
                "Invalid index type(s): invalid_type. Valid types: semantic, fts, temporal, scip"
            )
            MockManager.return_value = mock_manager

            result = await trigger_reindex(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "Invalid index type" in data["error"]

    async def test_trigger_reindex_repo_not_found(self, mock_user):
        """Test reindex with repository not found."""
        from code_indexer.server.mcp.handlers import trigger_reindex

        params = {
            "repository_alias": "nonexistent-repo",
            "index_types": ["semantic"],
            "clear": False,
        }

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.trigger_reindex.side_effect = FileNotFoundError(
                "Repository 'nonexistent-repo' not found for user 'testuser'"
            )
            MockManager.return_value = mock_manager

            result = await trigger_reindex(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "not found" in data["error"]


@pytest.mark.asyncio
class TestGetIndexStatusHandler:
    """Test get_index_status handler."""

    async def test_get_index_status_success(self, mock_user):
        """Test successful index status query."""
        from code_indexer.server.mcp.handlers import get_index_status

        params = {"repository_alias": "my-repo"}

        status_data = {
            "semantic": {
                "last_indexed": "2025-01-15T10:30:00Z",
                "file_count": 1234,
                "index_size_mb": 45.2,
                "status": "up_to_date",
            },
            "fts": {
                "last_updated": "2025-01-15T10:30:00Z",
                "document_count": 1234,
                "index_health": "healthy",
                "status": "up_to_date",
            },
            "temporal": {
                "last_indexed": "2025-01-15T09:00:00Z",
                "commit_count": 567,
                "date_range": {"start": "2024-01-01", "end": "2025-01-15"},
                "status": "up_to_date",
            },
            "scip": {
                "status": "SUCCESS",
                "project_count": 3,
                "last_generated": "2025-01-15T10:00:00Z",
                "projects": ["backend/", "frontend/", "shared/"],
            },
        }

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.get_index_status.return_value = status_data
            MockManager.return_value = mock_manager

            result = await get_index_status(params, mock_user)

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["repository_alias"] == "my-repo"
            assert data["semantic"]["status"] == "up_to_date"
            assert data["fts"]["index_health"] == "healthy"
            assert data["temporal"]["commit_count"] == 567
            assert data["scip"]["status"] == "SUCCESS"

            mock_manager.get_index_status.assert_called_once_with(
                repo_alias="my-repo", username="testuser"
            )

    async def test_get_index_status_repo_not_found(self, mock_user):
        """Test status query with repository not found."""
        from code_indexer.server.mcp.handlers import get_index_status

        params = {"repository_alias": "nonexistent-repo"}

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.get_index_status.side_effect = FileNotFoundError(
                "Repository 'nonexistent-repo' not found for user 'testuser'"
            )
            MockManager.return_value = mock_manager

            result = await get_index_status(params, mock_user)

            data = json.loads(result["content"][0]["text"])
            assert data["success"] is False
            assert "not found" in data["error"]

    async def test_get_index_status_not_indexed(self, mock_user):
        """Test status query for repository with no indexes."""
        from code_indexer.server.mcp.handlers import get_index_status

        params = {"repository_alias": "new-repo"}

        with patch(
            "code_indexer.server.services.activated_repo_index_manager.ActivatedRepoIndexManager"
        ) as MockManager:
            mock_manager = Mock()
            mock_manager.get_index_status.return_value = {
                "semantic": {"status": "not_indexed"},
                "fts": {"status": "not_indexed"},
                "temporal": {"status": "not_indexed"},
                "scip": {"status": "not_indexed", "project_count": 0},
            }
            MockManager.return_value = mock_manager

            result = await get_index_status(params, mock_user)

            data = json.loads(result["content"][0]["text"])

            assert data["success"] is True
            assert data["semantic"]["status"] == "not_indexed"
            assert data["fts"]["status"] == "not_indexed"
            assert data["temporal"]["status"] == "not_indexed"
            assert data["scip"]["status"] == "not_indexed"
