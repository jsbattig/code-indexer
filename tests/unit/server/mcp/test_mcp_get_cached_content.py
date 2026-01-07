"""Unit tests for MCP get_cached_content tool.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC5: MCP get_cached_content Tool

These tests follow TDD methodology - written BEFORE implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


class TestGetCachedContentToolDefinition:
    """Tests for get_cached_content tool definition in tools.py (AC5)."""

    def test_tool_definition_exists_in_registry(self):
        """Test that get_cached_content tool is defined in TOOL_REGISTRY."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        assert "get_cached_content" in TOOL_REGISTRY

    def test_tool_has_required_properties(self):
        """Test that tool definition has name, description, inputSchema."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["get_cached_content"]
        assert tool["name"] == "get_cached_content"
        assert "description" in tool
        assert "inputSchema" in tool

    def test_input_schema_has_handle_parameter(self):
        """Test that inputSchema requires handle parameter."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["get_cached_content"]
        schema = tool["inputSchema"]
        assert "handle" in schema["properties"]
        assert "handle" in schema["required"]

    def test_input_schema_has_page_parameter(self):
        """Test that inputSchema has optional page parameter with default 0."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY["get_cached_content"]
        schema = tool["inputSchema"]
        assert "page" in schema["properties"]
        # page should not be required (defaults to 0)
        assert "page" not in schema.get("required", [])


class TestGetCachedContentHandler:
    """Tests for handle_get_cached_content handler function (AC5)."""

    def test_handler_registered_in_handler_registry(self):
        """Test that handler is registered in HANDLER_REGISTRY."""
        from code_indexer.server.mcp.handlers import HANDLER_REGISTRY

        assert "get_cached_content" in HANDLER_REGISTRY

    @pytest.mark.asyncio
    async def test_handler_returns_content_for_valid_handle(self, mock_user):
        """Test handler returns content when cache handle is valid."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content
        from code_indexer.server.cache.payload_cache import CacheRetrievalResult

        mock_cache = AsyncMock()
        mock_cache.retrieve = AsyncMock(
            return_value=CacheRetrievalResult(
                content="Cached content page 0",
                page=0,
                total_pages=2,
                has_more=True,
            )
        )

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_cache

            result = await handle_get_cached_content(
                {"handle": "test-uuid-handle", "page": 0}, mock_user
            )

        # MCP responses wrap data in content array
        assert "content" in result
        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is True
        assert data["content"] == "Cached content page 0"
        assert data["page"] == 0
        assert data["total_pages"] == 2
        assert data["has_more"] is True

    @pytest.mark.asyncio
    async def test_handler_returns_error_for_invalid_handle(self, mock_user):
        """Test handler returns error when cache handle is not found."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content
        from code_indexer.server.cache.payload_cache import CacheNotFoundError

        mock_cache = AsyncMock()
        mock_cache.retrieve = AsyncMock(
            side_effect=CacheNotFoundError("Cache handle not found: invalid-handle")
        )

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_cache

            result = await handle_get_cached_content(
                {"handle": "invalid-handle", "page": 0}, mock_user
            )

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data
        assert "cache_expired" in data["error"] or "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_handler_defaults_page_to_zero(self, mock_user):
        """Test handler defaults page to 0 when not provided."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content
        from code_indexer.server.cache.payload_cache import CacheRetrievalResult

        mock_cache = AsyncMock()
        mock_cache.retrieve = AsyncMock(
            return_value=CacheRetrievalResult(
                content="Content",
                page=0,
                total_pages=1,
                has_more=False,
            )
        )

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            mock_state.payload_cache = mock_cache

            # Call without page parameter
            result = await handle_get_cached_content(
                {"handle": "test-handle"}, mock_user
            )

        # Verify retrieve was called with page=0
        mock_cache.retrieve.assert_called_once_with("test-handle", page=0)

    @pytest.mark.asyncio
    async def test_handler_returns_error_when_cache_unavailable(self, mock_user):
        """Test handler returns error when payload_cache not initialized."""
        from code_indexer.server.mcp.handlers import handle_get_cached_content

        with patch(
            "code_indexer.server.mcp.handlers.app_module.app.state"
        ) as mock_state:
            # payload_cache is None
            mock_state.payload_cache = None

            result = await handle_get_cached_content(
                {"handle": "test-handle", "page": 0}, mock_user
            )

        import json

        data = json.loads(result["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data
        assert "unavailable" in data["error"].lower() or "not available" in data["error"].lower()
