"""Test omni-list-files functionality (Story #571).

Tests polymorphic repository_alias parameter:
- String value routes to single-repo list_files
- Array value routes to omni-list-files across multiple repositories
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from code_indexer.server.mcp.handlers import list_files
from code_indexer.server.auth.user_manager import User, UserRole
from datetime import datetime


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return User(
        username="testuser",
        password_hash="hash",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_list_files_with_string_repository_alias(mock_user):
    """Test list_files with string repository_alias routes to single-repo handler."""
    params = {"repository_alias": "test-repo", "path": "src/"}

    # Mock the file_service to return a mock result
    mock_result = MagicMock()
    mock_result.files = [
        MagicMock(
            model_dump=lambda mode=None: {
                "path": "src/main.py",
                "size_bytes": 1024,
                "modified_at": "2025-01-01T00:00:00",
                "language": "python",
                "is_indexed": True,
            }
        )
    ]

    with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
        mock_app.file_service.list_files.return_value = mock_result

        result = await list_files(params, mock_user)

        # Verify single-repo handler was called
        mock_app.file_service.list_files.assert_called_once()

        # Verify result structure
        assert result["content"][0]["type"] == "text"
        response = json.loads(result["content"][0]["text"])
        assert response["success"] is True
        assert len(response["files"]) == 1
        assert response["files"][0]["path"] == "src/main.py"


@pytest.mark.asyncio
async def test_list_files_with_array_repository_alias(mock_user):
    """Test list_files with array repository_alias routes to omni-list-files.

    Tests placeholder implementation that returns empty results.
    """
    params = {
        "repository_alias": ["repo1-global", "repo2-global"],
        "path": "src/",
    }

    result = await list_files(params, mock_user)

    # Verify result structure for omni-list-files placeholder
    assert result["content"][0]["type"] == "text"
    response = json.loads(result["content"][0]["text"])
    assert response["success"] is True
    assert "files" in response
    assert "total_files" in response
    assert "repos_searched" in response
    assert "errors" in response
