"""
Unit tests for File CRUD MCP handlers.

Tests the three MCP handlers (create_file, edit_file, delete_file) with mocked
FileCRUDService and ActivatedRepoManager dependencies.

Test Strategy:
- Mock FileCRUDService methods to isolate handler logic
- Mock ActivatedRepoManager.get_activated_repo_path for repository resolution
- Validate MCP response format (_mcp_response wrapper)
- Test error handling (validation, repository not found, service errors)
- Test success paths with proper parameter passing
"""

import pytest
from unittest.mock import patch
from code_indexer.server.auth.user_manager import User, UserRole


# Test fixtures
@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        username="testuser",
        password_hash="$2b$12$test_hash",  # Required field
        api_key="test_api_key",
        role=UserRole.ADMIN,
        created_at="2025-01-01T00:00:00Z",
    )


@pytest.fixture
def mock_file_crud_service():
    """Mock FileCRUDService global instance."""
    with patch(
        "code_indexer.server.services.file_crud_service.file_crud_service"
    ) as mock_service:
        yield mock_service


class TestCreateFileHandler:
    """Tests for create_file MCP handler."""

    @pytest.mark.asyncio
    async def test_create_file_success(self, test_user, mock_file_crud_service):
        """Test successful file creation."""
        from code_indexer.server.mcp.handlers import create_file
        import json

        # Setup mock service response
        mock_file_crud_service.create_file.return_value = {
            "success": True,
            "file_path": "test/file.txt",
            "content_hash": "abc123def456",
            "size_bytes": 100,
            "created_at": "2025-01-01T12:00:00Z",
        }

        # Call handler
        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "content": "Test content",
        }
        result = await create_file(params, test_user)

        # Validate MCP response format
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse inner response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["file_path"] == "test/file.txt"
        assert response_data["content_hash"] == "abc123def456"
        assert response_data["size_bytes"] == 100

        # Verify service called with correct params
        mock_file_crud_service.create_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="test/file.txt",
            content="Test content",
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_create_file_missing_params(self, test_user):
        """Test create_file with missing required parameters."""
        from code_indexer.server.mcp.handlers import create_file
        import json

        # Missing file_path
        params = {"repository_alias": "test-repo", "content": "Test"}
        result = await create_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "error" in response_data
        assert "file_path" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_create_file_already_exists(self, test_user, mock_file_crud_service):
        """Test create_file when file already exists."""
        from code_indexer.server.mcp.handlers import create_file
        import json

        # Setup mock to raise FileExistsError
        mock_file_crud_service.create_file.side_effect = FileExistsError(
            "File already exists: test/file.txt"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "content": "Test",
        }
        result = await create_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "already exists" in response_data["error"]

    @pytest.mark.asyncio
    async def test_create_file_permission_error_git_path(
        self, test_user, mock_file_crud_service
    ):
        """Test create_file with .git/ path (should be blocked)."""
        from code_indexer.server.mcp.handlers import create_file
        import json

        # Setup mock to raise PermissionError
        mock_file_crud_service.create_file.side_effect = PermissionError(
            "create_file blocked: Access to .git/ directory is forbidden"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": ".git/config",
            "content": "Test",
        }
        result = await create_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert ".git/" in response_data["error"]


class TestEditFileHandler:
    """Tests for edit_file MCP handler."""

    @pytest.mark.asyncio
    async def test_edit_file_success(self, test_user, mock_file_crud_service):
        """Test successful file edit."""
        from code_indexer.server.mcp.handlers import edit_file
        import json

        # Setup mock service response
        mock_file_crud_service.edit_file.return_value = {
            "success": True,
            "file_path": "test/file.txt",
            "content_hash": "newdef789ghi",
            "modified_at": "2025-01-01T12:30:00Z",
            "changes_made": 1,
        }

        # Call handler
        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "old_string": "old text",
            "new_string": "new text",
            "content_hash": "abc123def456",
            "replace_all": False,
        }
        result = await edit_file(params, test_user)

        # Validate MCP response format
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["file_path"] == "test/file.txt"
        assert response_data["content_hash"] == "newdef789ghi"
        assert response_data["changes_made"] == 1

        # Verify service called with correct params
        mock_file_crud_service.edit_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="test/file.txt",
            old_string="old text",
            new_string="new text",
            content_hash="abc123def456",
            replace_all=False,
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_edit_file_hash_mismatch(self, test_user, mock_file_crud_service):
        """Test edit_file with hash mismatch (concurrent modification)."""
        from code_indexer.server.mcp.handlers import edit_file
        from code_indexer.server.services.file_crud_service import HashMismatchError
        import json

        # Setup mock to raise HashMismatchError
        mock_file_crud_service.edit_file.side_effect = HashMismatchError(
            "Content hash mismatch for 'test/file.txt'. "
            "Expected abc123, got def456. "
            "File may have been modified by another process."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "old_string": "old",
            "new_string": "new",
            "content_hash": "abc123",
            "replace_all": False,
        }
        result = await edit_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "hash mismatch" in response_data["error"].lower()
        assert "abc123" in response_data["error"]
        assert "def456" in response_data["error"]

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, test_user, mock_file_crud_service):
        """Test edit_file when file doesn't exist."""
        from code_indexer.server.mcp.handlers import edit_file
        import json

        # Setup mock to raise FileNotFoundError
        mock_file_crud_service.edit_file.side_effect = FileNotFoundError(
            "File not found: test/missing.txt"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/missing.txt",
            "old_string": "old",
            "new_string": "new",
            "content_hash": "abc123",
            "replace_all": False,
        }
        result = await edit_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "not found" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_edit_file_not_unique_without_replace_all(
        self, test_user, mock_file_crud_service
    ):
        """Test edit_file when old_string is not unique and replace_all=False."""
        from code_indexer.server.mcp.handlers import edit_file
        import json

        # Setup mock to raise ValueError
        mock_file_crud_service.edit_file.side_effect = ValueError(
            "String 'test' appears 3 times in 'file.txt'. "
            "Not unique - use replace_all=True to replace all occurrences."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "old_string": "test",
            "new_string": "TEST",
            "content_hash": "abc123",
            "replace_all": False,
        }
        result = await edit_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "not unique" in response_data["error"].lower()


class TestDeleteFileHandler:
    """Tests for delete_file MCP handler."""

    @pytest.mark.asyncio
    async def test_delete_file_success(self, test_user, mock_file_crud_service):
        """Test successful file deletion."""
        from code_indexer.server.mcp.handlers import delete_file
        import json

        # Setup mock service response
        mock_file_crud_service.delete_file.return_value = {
            "success": True,
            "file_path": "test/file.txt",
            "deleted_at": "2025-01-01T13:00:00Z",
        }

        # Call handler
        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "content_hash": "abc123def456",
        }
        result = await delete_file(params, test_user)

        # Validate MCP response format
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["file_path"] == "test/file.txt"
        assert "deleted_at" in response_data

        # Verify service called with correct params
        mock_file_crud_service.delete_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="test/file.txt",
            content_hash="abc123def456",
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_delete_file_without_hash(self, test_user, mock_file_crud_service):
        """Test delete_file without content_hash (optional parameter)."""
        from code_indexer.server.mcp.handlers import delete_file
        import json

        # Setup mock service response
        mock_file_crud_service.delete_file.return_value = {
            "success": True,
            "file_path": "test/file.txt",
            "deleted_at": "2025-01-01T13:00:00Z",
        }

        # Call handler without content_hash
        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
        }
        result = await delete_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True

        # Verify service called with content_hash=None
        mock_file_crud_service.delete_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="test/file.txt",
            content_hash=None,
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, test_user, mock_file_crud_service):
        """Test delete_file when file doesn't exist."""
        from code_indexer.server.mcp.handlers import delete_file
        import json

        # Setup mock to raise FileNotFoundError
        mock_file_crud_service.delete_file.side_effect = FileNotFoundError(
            "File not found: test/missing.txt"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/missing.txt",
        }
        result = await delete_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "not found" in response_data["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_file_hash_mismatch(self, test_user, mock_file_crud_service):
        """Test delete_file with hash mismatch."""
        from code_indexer.server.mcp.handlers import delete_file
        from code_indexer.server.services.file_crud_service import HashMismatchError
        import json

        # Setup mock to raise HashMismatchError
        mock_file_crud_service.delete_file.side_effect = HashMismatchError(
            "Content hash mismatch for 'test/file.txt'. "
            "Expected abc123, got def456. "
            "File may have been modified since hash was computed."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "test/file.txt",
            "content_hash": "abc123",
        }
        result = await delete_file(params, test_user)

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is False
        assert "hash mismatch" in response_data["error"].lower()
