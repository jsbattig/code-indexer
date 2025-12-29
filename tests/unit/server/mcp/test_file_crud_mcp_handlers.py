"""
Unit tests for File CRUD MCP Handlers (Story #628).

Tests the three MCP handlers:
- handle_create_file: Create new file in activated repository
- handle_edit_file: Edit file with optimistic locking
- handle_delete_file: Delete file with optional hash validation

All tests use mocked FileCRUDService to avoid real file operations
and focus on MCP handler logic, parameter validation, and error handling.
"""

import json
from datetime import datetime
from unittest.mock import patch
import pytest

from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.services.file_crud_service import (
    HashMismatchError,
    CRUDOperationError,
)


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
def mock_file_crud_service():
    """Create mock FileCRUDService."""
    with patch(
        "code_indexer.server.services.file_crud_service.file_crud_service"
    ) as mock_service:
        yield mock_service


def _extract_response_data(mcp_response: dict) -> dict:
    """Extract actual response data from MCP wrapper."""
    content = mcp_response["content"][0]
    return json.loads(content["text"])


class TestHandleCreateFile:
    """Test handle_create_file MCP handler."""

    @pytest.mark.asyncio
    async def test_create_file_success(self, mock_user, mock_file_crud_service):
        """Test successful file creation."""
        from code_indexer.server.mcp import handlers

        # Mock FileCRUDService response
        mock_file_crud_service.create_file.return_value = {
            "success": True,
            "file_path": "src/new_module.py",
            "content_hash": "abc123def456",
            "size_bytes": 100,
            "created_at": "2025-12-29T12:00:00Z",
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/new_module.py",
            "content": "def hello():\n    return 'world'",
        }

        # Execute handler
        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        # Verify response
        assert data["success"] is True
        assert data["file_path"] == "src/new_module.py"
        assert data["content_hash"] == "abc123def456"
        assert data["size_bytes"] == 100
        assert data["created_at"] == "2025-12-29T12:00:00Z"

        # Verify service was called correctly
        mock_file_crud_service.create_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="src/new_module.py",
            content="def hello():\n    return 'world'",
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_create_file_missing_params(self, mock_user, mock_file_crud_service):
        """Test create_file with missing required parameters."""
        from code_indexer.server.mcp import handlers

        # Missing file_path and content
        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter" in data["error"]

    @pytest.mark.asyncio
    async def test_create_file_already_exists(self, mock_user, mock_file_crud_service):
        """Test create_file when file already exists."""
        from code_indexer.server.mcp import handlers

        # Mock service raising FileExistsError
        mock_file_crud_service.create_file.side_effect = FileExistsError(
            "File already exists: src/existing.py"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/existing.py",
            "content": "content",
        }

        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "File already exists" in data["error"]

    @pytest.mark.asyncio
    async def test_create_file_permission_denied(self, mock_user, mock_file_crud_service):
        """Test create_file with invalid path (security violation)."""
        from code_indexer.server.mcp import handlers

        # Mock service raising PermissionError for .git/ access
        mock_file_crud_service.create_file.side_effect = PermissionError(
            "create_file blocked: Access to .git/ directory is forbidden"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": ".git/hooks/pre-commit",
            "content": "#!/bin/bash",
        }

        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Permission" in data["error"] or ".git" in data["error"]

    @pytest.mark.asyncio
    async def test_create_file_crud_operation_error(self, mock_user, mock_file_crud_service):
        """Test create_file with general CRUD operation failure."""
        from code_indexer.server.mcp import handlers

        # Mock service raising CRUDOperationError
        mock_file_crud_service.create_file.side_effect = CRUDOperationError(
            "Failed to write file: disk full"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/new_file.py",
            "content": "content",
        }

        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Failed to write file" in data["error"]

    @pytest.mark.asyncio
    async def test_create_file_repository_not_activated(self, mock_user, mock_file_crud_service):
        """Test create_file when repository is not activated."""
        from code_indexer.server.mcp import handlers

        # Mock service raising ValueError (repository not found)
        mock_file_crud_service.create_file.side_effect = ValueError(
            "Repository 'unknown-repo' not activated for user 'testuser'"
        )

        params = {
            "repository_alias": "unknown-repo",
            "file_path": "src/new_file.py",
            "content": "content",
        }

        mcp_response = await handlers.handle_create_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "not activated" in data["error"]


class TestHandleEditFile:
    """Test handle_edit_file MCP handler."""

    @pytest.mark.asyncio
    async def test_edit_file_success(self, mock_user, mock_file_crud_service):
        """Test successful file edit with optimistic locking."""
        from code_indexer.server.mcp import handlers

        # Mock FileCRUDService response
        mock_file_crud_service.edit_file.return_value = {
            "success": True,
            "file_path": "src/module.py",
            "content_hash": "new_hash_xyz789",
            "modified_at": "2025-12-29T12:05:00Z",
            "changes_made": 1,
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "old_string": "def old_func():",
            "new_string": "def new_func():",
            "content_hash": "old_hash_abc123",
            "replace_all": False,
        }

        # Execute handler
        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        # Verify response
        assert data["success"] is True
        assert data["file_path"] == "src/module.py"
        assert data["content_hash"] == "new_hash_xyz789"
        assert data["modified_at"] == "2025-12-29T12:05:00Z"
        assert data["changes_made"] == 1

        # Verify service was called correctly
        mock_file_crud_service.edit_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="src/module.py",
            old_string="def old_func():",
            new_string="def new_func():",
            content_hash="old_hash_abc123",
            replace_all=False,
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_edit_file_replace_all(self, mock_user, mock_file_crud_service):
        """Test edit_file with replace_all=True."""
        from code_indexer.server.mcp import handlers

        # Mock service response with multiple replacements
        mock_file_crud_service.edit_file.return_value = {
            "success": True,
            "file_path": "src/module.py",
            "content_hash": "new_hash_xyz789",
            "modified_at": "2025-12-29T12:05:00Z",
            "changes_made": 3,  # Multiple replacements
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "old_string": "old_var",
            "new_string": "new_var",
            "content_hash": "old_hash_abc123",
            "replace_all": True,
        }

        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True
        assert data["changes_made"] == 3

    @pytest.mark.asyncio
    async def test_edit_file_missing_params(self, mock_user, mock_file_crud_service):
        """Test edit_file with missing required parameters."""
        from code_indexer.server.mcp import handlers

        # Missing content_hash
        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "old_string": "old",
            "new_string": "new",
        }

        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter" in data["error"]

    @pytest.mark.asyncio
    async def test_edit_file_hash_mismatch(self, mock_user, mock_file_crud_service):
        """Test edit_file when content hash doesn't match (concurrent modification)."""
        from code_indexer.server.mcp import handlers

        # Mock service raising HashMismatchError
        mock_file_crud_service.edit_file.side_effect = HashMismatchError(
            "Content hash mismatch for 'src/module.py'. Expected old_hash, got current_hash. "
            "File may have been modified by another process."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "old_string": "old",
            "new_string": "new",
            "content_hash": "old_hash",
            "replace_all": False,
        }

        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "hash mismatch" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_edit_file_not_found(self, mock_user, mock_file_crud_service):
        """Test edit_file when file doesn't exist."""
        from code_indexer.server.mcp import handlers

        # Mock service raising FileNotFoundError
        mock_file_crud_service.edit_file.side_effect = FileNotFoundError(
            "File not found: src/missing.py"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/missing.py",
            "old_string": "old",
            "new_string": "new",
            "content_hash": "hash",
            "replace_all": False,
        }

        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_edit_file_string_not_unique(self, mock_user, mock_file_crud_service):
        """Test edit_file when old_string appears multiple times and replace_all=False."""
        from code_indexer.server.mcp import handlers

        # Mock service raising ValueError for non-unique string
        mock_file_crud_service.edit_file.side_effect = ValueError(
            "String 'old' appears 3 times in 'src/module.py'. "
            "Not unique - use replace_all=True to replace all occurrences."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "old_string": "old",
            "new_string": "new",
            "content_hash": "hash",
            "replace_all": False,
        }

        mcp_response = await handlers.handle_edit_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "replace_all" in data["error"].lower()


class TestHandleDeleteFile:
    """Test handle_delete_file MCP handler."""

    @pytest.mark.asyncio
    async def test_delete_file_success_without_hash(self, mock_user, mock_file_crud_service):
        """Test successful file deletion without hash validation."""
        from code_indexer.server.mcp import handlers

        # Mock FileCRUDService response
        mock_file_crud_service.delete_file.return_value = {
            "success": True,
            "file_path": "src/old_module.py",
            "deleted_at": "2025-12-29T12:10:00Z",
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/old_module.py",
        }

        # Execute handler
        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        # Verify response
        assert data["success"] is True
        assert data["file_path"] == "src/old_module.py"
        assert data["deleted_at"] == "2025-12-29T12:10:00Z"

        # Verify service was called correctly (without content_hash)
        mock_file_crud_service.delete_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="src/old_module.py",
            content_hash=None,
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_delete_file_success_with_hash(self, mock_user, mock_file_crud_service):
        """Test successful file deletion with hash validation."""
        from code_indexer.server.mcp import handlers

        # Mock FileCRUDService response
        mock_file_crud_service.delete_file.return_value = {
            "success": True,
            "file_path": "src/old_module.py",
            "deleted_at": "2025-12-29T12:10:00Z",
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/old_module.py",
            "content_hash": "hash_xyz789",
        }

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is True

        # Verify service was called correctly (with content_hash)
        mock_file_crud_service.delete_file.assert_called_once_with(
            repo_alias="test-repo",
            file_path="src/old_module.py",
            content_hash="hash_xyz789",
            username="testuser",
        )

    @pytest.mark.asyncio
    async def test_delete_file_missing_params(self, mock_user, mock_file_crud_service):
        """Test delete_file with missing required parameters."""
        from code_indexer.server.mcp import handlers

        # Missing file_path
        params = {"repository_alias": "test-repo"}

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Missing required parameter" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, mock_user, mock_file_crud_service):
        """Test delete_file when file doesn't exist."""
        from code_indexer.server.mcp import handlers

        # Mock service raising FileNotFoundError
        mock_file_crud_service.delete_file.side_effect = FileNotFoundError(
            "File not found: src/missing.py"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/missing.py",
        }

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_file_hash_mismatch(self, mock_user, mock_file_crud_service):
        """Test delete_file when content hash doesn't match (safety check)."""
        from code_indexer.server.mcp import handlers

        # Mock service raising HashMismatchError
        mock_file_crud_service.delete_file.side_effect = HashMismatchError(
            "Content hash mismatch for 'src/module.py'. Expected old_hash, got current_hash. "
            "File may have been modified since hash was computed."
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/module.py",
            "content_hash": "old_hash",
        }

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "hash mismatch" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_delete_file_permission_denied(self, mock_user, mock_file_crud_service):
        """Test delete_file with invalid path (security violation)."""
        from code_indexer.server.mcp import handlers

        # Mock service raising PermissionError for .git/ access
        mock_file_crud_service.delete_file.side_effect = PermissionError(
            "delete_file blocked: Access to .git/ directory is forbidden"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": ".git/config",
        }

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Permission" in data["error"] or ".git" in data["error"]

    @pytest.mark.asyncio
    async def test_delete_file_crud_operation_error(self, mock_user, mock_file_crud_service):
        """Test delete_file with general CRUD operation failure."""
        from code_indexer.server.mcp import handlers

        # Mock service raising CRUDOperationError
        mock_file_crud_service.delete_file.side_effect = CRUDOperationError(
            "Failed to delete file: permission denied by OS"
        )

        params = {
            "repository_alias": "test-repo",
            "file_path": "src/locked_file.py",
        }

        mcp_response = await handlers.handle_delete_file(params, mock_user)
        data = _extract_response_data(mcp_response)

        assert data["success"] is False
        assert "Failed to delete file" in data["error"]
