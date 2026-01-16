"""
Unit tests for set_session_impersonation MCP tool.

Story #722: Session Impersonation for Delegated Queries

Tests the MCP tool definition and handler for session impersonation.
"""


class TestSetSessionImpersonationToolDefinition:
    """Test the set_session_impersonation tool registry entry."""

    def test_tool_registered_in_registry(self):
        """Test that set_session_impersonation is in TOOL_REGISTRY."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        assert "set_session_impersonation" in TOOL_REGISTRY

    def test_tool_has_correct_schema(self):
        """Test that set_session_impersonation has correct inputSchema."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        tool_def = TOOL_REGISTRY["set_session_impersonation"]

        assert tool_def["name"] == "set_session_impersonation"
        assert "description" in tool_def
        assert "inputSchema" in tool_def

        schema = tool_def["inputSchema"]
        assert schema["type"] == "object"
        assert "username" in schema["properties"]
        # username can be string or null (to clear)
        assert "required_permission" in tool_def


class TestSetSessionImpersonationHandlerRegistration:
    """Test the set_session_impersonation handler registration."""

    def test_handler_registered_in_registry(self):
        """Test that set_session_impersonation handler is in HANDLER_REGISTRY."""
        from code_indexer.server.mcp.handlers import HANDLER_REGISTRY

        assert "set_session_impersonation" in HANDLER_REGISTRY

    def test_handler_is_callable(self):
        """Test that set_session_impersonation handler is a callable."""
        from code_indexer.server.mcp.handlers import HANDLER_REGISTRY

        handler = HANDLER_REGISTRY["set_session_impersonation"]
        assert callable(handler)
