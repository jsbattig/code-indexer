"""
Unit tests for get_file_content MCP handler pagination support (Story #638).

Tests AC9-10:
- AC9: Invalid Offset - offset=0 or negative returns error
- AC10: Invalid Limit - limit=0 or negative returns error

Also tests:
- Parameter extraction from params dict
- Default values when parameters omitted
- Proper forwarding of valid offset/limit to FileService
- Both global and activated repository code paths
"""

import json
from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest

from code_indexer.server.auth.user_manager import User, UserRole


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
def mock_file_service():
    """Create mock FileListingService."""
    with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
        mock_service = MagicMock()
        mock_app.file_service = mock_service
        yield mock_service


def _extract_response_data(mcp_response: dict) -> dict:
    """Extract actual response data from MCP wrapper."""
    # MCP response format: {"content": [{"type": "text", "text": "..."}], ...}
    if "content" in mcp_response and len(mcp_response["content"]) > 0:
        content = mcp_response["content"][0]
        if "text" in content:
            try:
                return json.loads(content["text"])
            except json.JSONDecodeError:
                # If not JSON, return raw text
                return {"text": content["text"]}
    return mcp_response


class TestGetFileContentPaginationParameters:
    """Test get_file_content handler parameter extraction and validation."""

    @pytest.mark.asyncio
    async def test_offset_and_limit_forwarded_to_service(
        self, mock_user, mock_file_service
    ):
        """Test that offset and limit parameters are forwarded to FileService."""
        from code_indexer.server.mcp import handlers

        # Mock FileService response
        mock_file_service.get_file_content.return_value = {
            "content": "# Line 100\n# Line 101\n",
            "metadata": {
                "size": 200,
                "modified_at": "2025-12-29T12:00:00Z",
                "language": "python",
                "path": "test.py",
                "total_lines": 5000,
                "returned_lines": 2,
                "offset": 100,
                "limit": 2,
                "has_more": True,
            },
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": 100,
            "limit": 2,
        }

        # Execute handler
        mcp_response = await handlers.get_file_content(params, mock_user)

        # Verify service was called with pagination parameters
        mock_file_service.get_file_content.assert_called_once_with(
            repository_alias="test-repo",
            file_path="test.py",
            username="testuser",
            offset=100,
            limit=2,
        )

        # Verify response includes metadata
        # MCP response wraps everything in JSON content blocks
        data = _extract_response_data(mcp_response)
        assert "metadata" in data
        metadata = data["metadata"]
        assert metadata["total_lines"] == 5000
        assert metadata["returned_lines"] == 2
        assert metadata["offset"] == 100
        assert metadata["limit"] == 2
        assert metadata["has_more"] is True

    @pytest.mark.asyncio
    async def test_no_pagination_params_defaults_to_full_file(
        self, mock_user, mock_file_service
    ):
        """Test that omitting offset/limit returns full file (backward compatibility)."""
        from code_indexer.server.mcp import handlers

        # Mock FileService response (full file)
        mock_file_service.get_file_content.return_value = {
            "content": "Full file content\n",
            "metadata": {
                "size": 200,
                "modified_at": "2025-12-29T12:00:00Z",
                "language": "python",
                "path": "test.py",
                "total_lines": 1,
                "returned_lines": 1,
                "offset": 1,
                "limit": None,
                "has_more": False,
            },
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            # No offset or limit
        }

        # Execute handler
        await handlers.get_file_content(params, mock_user)

        # Verify service was called without pagination parameters (defaults to None)
        call_args = mock_file_service.get_file_content.call_args
        assert call_args[1]["repository_alias"] == "test-repo"
        assert call_args[1]["file_path"] == "test.py"
        # offset and limit should be None (or not passed if using positional args)

    @pytest.mark.asyncio
    async def test_limit_only_no_offset(self, mock_user, mock_file_service):
        """Test using limit without offset (offset defaults to 1)."""
        from code_indexer.server.mcp import handlers

        # Mock FileService response
        mock_file_service.get_file_content.return_value = {
            "content": "# Line 1\n# Line 2\n",
            "metadata": {
                "size": 200,
                "modified_at": "2025-12-29T12:00:00Z",
                "language": "python",
                "path": "test.py",
                "total_lines": 5000,
                "returned_lines": 2,
                "offset": 1,
                "limit": 2,
                "has_more": True,
            },
        }

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "limit": 2,  # No offset specified
        }

        # Execute handler
        await handlers.get_file_content(params, mock_user)

        # Verify service was called with limit only
        call_args = mock_file_service.get_file_content.call_args
        assert call_args[1]["limit"] == 2


class TestGetFileContentInvalidParameters:
    """Test AC9-10: Invalid offset/limit parameter validation."""

    @pytest.mark.asyncio
    async def test_invalid_offset_zero(self, mock_user, mock_file_service):
        """AC9: offset=0 returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": 0,
            "limit": 100,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract response data
        # For error responses, check both the direct response and content blocks
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "offset must be" in error_msg or "offset" in error_msg.lower()
        assert ">= 1" in error_msg or "positive" in error_msg.lower()

        # Service should NOT be called with invalid parameters
        mock_file_service.get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_offset_negative(self, mock_user, mock_file_service):
        """AC9: offset=-5 returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": -5,
            "limit": 100,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract error
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "offset must be" in error_msg or "offset" in error_msg.lower()

        mock_file_service.get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_limit_zero(self, mock_user, mock_file_service):
        """AC10: limit=0 returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": 1,
            "limit": 0,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract error
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "limit must be" in error_msg or "limit" in error_msg.lower()
        assert ">= 1" in error_msg or "positive" in error_msg.lower()

        mock_file_service.get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_limit_negative(self, mock_user, mock_file_service):
        """AC10: limit=-10 returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": 1,
            "limit": -10,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract error
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "limit must be" in error_msg or "limit" in error_msg.lower()

        mock_file_service.get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_integer_offset(self, mock_user, mock_file_service):
        """Test that non-integer offset returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": "not-a-number",
            "limit": 100,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract error
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "offset must be" in error_msg or "integer" in error_msg.lower()

        mock_file_service.get_file_content.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_integer_limit(self, mock_user, mock_file_service):
        """Test that non-integer limit returns error."""
        from code_indexer.server.mcp import handlers

        params = {
            "repository_alias": "test-repo",
            "file_path": "test.py",
            "offset": 1,
            "limit": 3.14,
        }

        mcp_response = await handlers.get_file_content(params, mock_user)

        # Extract error
        if "error" in mcp_response:
            error_msg = mcp_response["error"]
        else:
            data = _extract_response_data(mcp_response)
            error_msg = data.get("error", "")

        assert "limit must be" in error_msg or "integer" in error_msg.lower()

        mock_file_service.get_file_content.assert_not_called()


class TestGetFileContentGlobalRepositories:
    """Test pagination with global repositories (uses get_file_content_by_path)."""

    @pytest.mark.asyncio
    async def test_global_repo_pagination(self, mock_user, mock_file_service):
        """Test that pagination works with global repositories."""
        from code_indexer.server.mcp import handlers

        # Mock global repo lookup
        # AliasManager is imported inside the function, so patch it at the import location
        with (
            patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry"
            ) as mock_registry_class,
            patch(
                "code_indexer.global_repos.alias_manager.AliasManager"
            ) as mock_alias_manager_class,
            patch(
                "code_indexer.server.mcp.handlers._get_golden_repos_dir"
            ) as mock_get_golden_dir,
        ):

            mock_get_golden_dir.return_value = "/fake/golden/repos"

            # Mock registry
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = [
                {"alias_name": "test-repo-global", "target_path": "/fake/repo"}
            ]
            mock_registry_class.return_value = mock_registry

            # Mock alias manager
            mock_alias_manager = MagicMock()
            mock_alias_manager.read_alias.return_value = "/fake/repo"
            mock_alias_manager_class.return_value = mock_alias_manager

            # Mock FileService response
            mock_file_service.get_file_content_by_path.return_value = {
                "content": "# Line 50\n",
                "metadata": {
                    "size": 100,
                    "modified_at": "2025-12-29T12:00:00Z",
                    "language": "python",
                    "path": "test.py",
                    "total_lines": 1000,
                    "returned_lines": 1,
                    "offset": 50,
                    "limit": 1,
                    "has_more": True,
                },
            }

            params = {
                "repository_alias": "test-repo-global",
                "file_path": "test.py",
                "offset": 50,
                "limit": 1,
            }

            # Execute handler
            mcp_response = await handlers.get_file_content(params, mock_user)

            # Verify get_file_content_by_path was called with pagination params
            mock_file_service.get_file_content_by_path.assert_called_once()
            call_args = mock_file_service.get_file_content_by_path.call_args
            assert call_args[1]["offset"] == 50
            assert call_args[1]["limit"] == 1

            # Verify response includes pagination metadata
            # MCP response wraps everything in JSON content blocks
            data = _extract_response_data(mcp_response)
            assert "metadata" in data
            metadata = data["metadata"]
            assert metadata["offset"] == 50
            assert metadata["limit"] == 1
            assert metadata["has_more"] is True
