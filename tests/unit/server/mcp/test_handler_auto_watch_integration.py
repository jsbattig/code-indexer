"""
Unit tests for auto-watch integration in file CRUD handlers.

Tests verify that file CRUD handlers trigger auto-watch functionality
when files are created, edited, or deleted.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from code_indexer.server.auth.user_manager import User


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    return user


@pytest.fixture
def mock_auto_watch_manager():
    """Create a mock AutoWatchManager for testing."""
    mock = Mock()
    mock.start_watch = Mock()
    mock.reset_timeout = Mock()
    mock.is_watching = Mock(return_value=False)
    return mock


@pytest.fixture
def mock_file_crud_service():
    """Create a mock FileCRUDService for testing."""
    mock = Mock()
    mock.create_file = Mock(
        return_value={
            "success": True,
            "file_path": "test.py",
            "content_hash": "abc123",
            "size_bytes": 100,
            "created_at": "2025-01-01T00:00:00Z",
        }
    )
    mock.edit_file = Mock(
        return_value={
            "success": True,
            "file_path": "test.py",
            "content_hash": "def456",
            "old_content_hash": "abc123",
            "size_bytes": 150,
            "modified_at": "2025-01-01T00:01:00Z",
        }
    )
    mock.delete_file = Mock(
        return_value={
            "success": True,
            "file_path": "test.py",
            "deleted_at": "2025-01-01T00:02:00Z",
        }
    )
    return mock


@pytest.fixture
def mock_activated_repo_manager():
    """Create a mock ActivatedRepoManager for testing."""
    mock = Mock()
    mock.get_activated_repo_path = Mock(return_value=Path("/tmp/test-repo"))
    return mock


class TestHandleCreateFileAutoWatch:
    """Tests for auto-watch integration in handle_create_file."""

    @pytest.mark.asyncio
    async def test_create_file_starts_auto_watch(
        self, mock_user, mock_auto_watch_manager, mock_file_crud_service, mock_activated_repo_manager
    ):
        """Test that creating a file triggers auto-watch start."""
        from code_indexer.server.mcp.handlers import handle_create_file

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "content": "print('hello')",
        }

        # Patch dependencies
        with patch(
            "code_indexer.server.mcp.handlers.auto_watch_manager", mock_auto_watch_manager
        ), patch(
            "code_indexer.server.services.file_crud_service.file_crud_service",
            mock_file_crud_service,
        ), patch(
            "code_indexer.server.services.file_crud_service.FileCRUDService.activated_repo_manager",
            mock_activated_repo_manager,
        ):
            result = await handle_create_file(params, mock_user)

        # Verify auto-watch was started with repository path
        mock_auto_watch_manager.start_watch.assert_called_once()
        call_args = mock_auto_watch_manager.start_watch.call_args[0]
        assert call_args[0] == Path("/tmp/test-repo")

        # Verify file was created
        mock_file_crud_service.create_file.assert_called_once()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_create_file_auto_watch_called_before_creation(
        self, mock_user, mock_auto_watch_manager, mock_file_crud_service, mock_activated_repo_manager
    ):
        """Test that auto-watch is started BEFORE file creation."""
        from code_indexer.server.mcp.handlers import handle_create_file

        call_order = []

        def track_auto_watch(*args, **kwargs):
            call_order.append("auto_watch")

        def track_create(*args, **kwargs):
            call_order.append("create_file")
            return {
                "success": True,
                "file_path": "test.py",
                "content_hash": "abc123",
                "size_bytes": 100,
                "created_at": "2025-01-01T00:00:00Z",
            }

        mock_auto_watch_manager.start_watch.side_effect = track_auto_watch
        mock_file_crud_service.create_file.side_effect = track_create

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "content": "print('hello')",
        }

        with patch(
            "code_indexer.server.mcp.handlers.auto_watch_manager", mock_auto_watch_manager
        ), patch(
            "code_indexer.server.services.file_crud_service.file_crud_service",
            mock_file_crud_service,
        ), patch(
            "code_indexer.server.services.file_crud_service.FileCRUDService.activated_repo_manager",
            mock_activated_repo_manager,
        ):
            await handle_create_file(params, mock_user)

        # Verify auto-watch was called BEFORE create_file
        assert call_order == ["auto_watch", "create_file"]


class TestHandleEditFileAutoWatch:
    """Tests for auto-watch integration in handle_edit_file."""

    @pytest.mark.asyncio
    async def test_edit_file_starts_auto_watch(
        self, mock_user, mock_auto_watch_manager, mock_file_crud_service, mock_activated_repo_manager
    ):
        """Test that editing a file triggers auto-watch start."""
        from code_indexer.server.mcp.handlers import handle_edit_file

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "old_string": "hello",
            "new_string": "goodbye",
            "content_hash": "abc123",
        }

        with patch(
            "code_indexer.server.mcp.handlers.auto_watch_manager", mock_auto_watch_manager
        ), patch(
            "code_indexer.server.services.file_crud_service.file_crud_service",
            mock_file_crud_service,
        ), patch(
            "code_indexer.server.services.file_crud_service.FileCRUDService.activated_repo_manager",
            mock_activated_repo_manager,
        ):
            result = await handle_edit_file(params, mock_user)

        # Verify auto-watch was started
        mock_auto_watch_manager.start_watch.assert_called_once()
        call_args = mock_auto_watch_manager.start_watch.call_args[0]
        assert call_args[0] == Path("/tmp/test-repo")

        # Verify file was edited
        mock_file_crud_service.edit_file.assert_called_once()
        assert result["success"] is True


class TestHandleDeleteFileAutoWatch:
    """Tests for auto-watch integration in handle_delete_file."""

    @pytest.mark.asyncio
    async def test_delete_file_starts_auto_watch(
        self, mock_user, mock_auto_watch_manager, mock_file_crud_service, mock_activated_repo_manager
    ):
        """Test that deleting a file triggers auto-watch start."""
        from code_indexer.server.mcp.handlers import handle_delete_file

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
        }

        with patch(
            "code_indexer.server.mcp.handlers.auto_watch_manager", mock_auto_watch_manager
        ), patch(
            "code_indexer.server.services.file_crud_service.file_crud_service",
            mock_file_crud_service,
        ), patch(
            "code_indexer.server.services.file_crud_service.FileCRUDService.activated_repo_manager",
            mock_activated_repo_manager,
        ):
            result = await handle_delete_file(params, mock_user)

        # Verify auto-watch was started
        mock_auto_watch_manager.start_watch.assert_called_once()
        call_args = mock_auto_watch_manager.start_watch.call_args[0]
        assert call_args[0] == Path("/tmp/test-repo")

        # Verify file was deleted
        mock_file_crud_service.delete_file.assert_called_once()
        assert result["success"] is True


class TestAutoWatchMultipleOperations:
    """Tests for auto-watch timeout reset on multiple operations."""

    @pytest.mark.asyncio
    async def test_multiple_file_operations_reset_timeout(
        self, mock_user, mock_auto_watch_manager, mock_file_crud_service, mock_activated_repo_manager
    ):
        """Test that multiple file operations reset auto-watch timeout."""
        from code_indexer.server.mcp.handlers import handle_create_file, handle_edit_file

        # Configure mock to show watching after first operation
        mock_auto_watch_manager.is_watching = Mock(side_effect=[False, True])

        # First operation: create file
        create_params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "content": "print('hello')",
        }

        with patch(
            "code_indexer.server.mcp.handlers.auto_watch_manager", mock_auto_watch_manager
        ), patch(
            "code_indexer.server.services.file_crud_service.file_crud_service",
            mock_file_crud_service,
        ), patch(
            "code_indexer.server.services.file_crud_service.FileCRUDService.activated_repo_manager",
            mock_activated_repo_manager,
        ):
            await handle_create_file(create_params, mock_user)

            # Second operation: edit file
            edit_params = {
                "repository_alias": "test-repo",
                "file_path": "test.py",
                "old_string": "hello",
                "new_string": "goodbye",
                "content_hash": "abc123",
            }
            await handle_edit_file(edit_params, mock_user)

        # Verify start_watch was called for both operations
        assert mock_auto_watch_manager.start_watch.call_count == 2
