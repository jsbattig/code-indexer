"""Test MCP tools protocol compliance - ensure only valid MCP fields are returned.

Bug: filter_tools_by_role() was returning tool definitions with non-MCP fields
(required_permission, outputSchema) which causes Claude.ai MCP client to reject tools.

MCP Protocol Spec: tools/list response must only contain:
- name: string
- description: string
- inputSchema: object

Internal fields like required_permission and outputSchema must be filtered out.
"""

import pytest
from datetime import datetime
from code_indexer.server.mcp.tools import filter_tools_by_role, TOOL_REGISTRY
from code_indexer.server.auth.user_manager import User


class TestMCPProtocolCompliance:
    """Test that filter_tools_by_role returns MCP-compliant tool definitions."""

    def test_filter_tools_by_role_returns_only_mcp_fields(self):
        """Test that filtered tools contain only MCP-valid fields (name, description, inputSchema).

        CRITICAL: MCP protocol spec defines tools/list response format.
        Each tool must have ONLY these fields:
        - name: string
        - description: string
        - inputSchema: object with type/properties

        Internal fields like required_permission and outputSchema must NOT be included
        as they violate the MCP protocol and cause client rejection.
        """
        # Create admin user with all permissions
        admin_user = User(
            username="admin",
            password_hash="fake",
            role="admin",
            created_at=datetime.now(),
        )

        # Get filtered tools
        filtered_tools = filter_tools_by_role(admin_user)

        # Verify we got tools back
        assert len(filtered_tools) > 0, "Should return at least one tool for admin"

        # Check EVERY tool for MCP compliance
        for tool in filtered_tools:
            tool_name = tool.get("name", "UNKNOWN")

            # MUST have these MCP-required fields
            assert "name" in tool, f"Tool {tool_name} missing required 'name' field"
            assert (
                "description" in tool
            ), f"Tool {tool_name} missing required 'description' field"
            assert (
                "inputSchema" in tool
            ), f"Tool {tool_name} missing required 'inputSchema' field"

            # MUST NOT have these internal fields (protocol violation)
            assert "required_permission" not in tool, (
                f"Tool {tool_name} contains 'required_permission' field - "
                f"this violates MCP protocol and causes client rejection"
            )
            assert "outputSchema" not in tool, (
                f"Tool {tool_name} contains 'outputSchema' field - "
                f"this violates MCP protocol and causes client rejection"
            )

            # Should have EXACTLY 3 fields (name, description, inputSchema)
            assert len(tool.keys()) == 3, (
                f"Tool {tool_name} has {len(tool.keys())} fields (expected 3). "
                f"Fields: {list(tool.keys())}"
            )

    def test_filter_tools_preserves_required_fields(self):
        """Test that MCP-required fields are preserved with correct structure."""
        admin_user = User(
            username="admin",
            password_hash="fake",
            role="admin",
            created_at=datetime.now(),
        )
        filtered_tools = filter_tools_by_role(admin_user)

        for tool in filtered_tools:
            # Validate field types
            assert isinstance(tool["name"], str), "name must be string"
            assert isinstance(tool["description"], str), "description must be string"
            assert isinstance(tool["inputSchema"], dict), "inputSchema must be dict"

            # Validate inputSchema structure (MCP requirement)
            schema = tool["inputSchema"]
            assert "type" in schema, "inputSchema must have 'type' field"
            assert "properties" in schema, "inputSchema must have 'properties' field"
            assert schema["type"] == "object", "inputSchema type must be 'object'"

    def test_original_tool_registry_has_internal_fields(self):
        """Verify that TOOL_REGISTRY contains internal fields that need filtering.

        This test documents the current state: TOOL_REGISTRY contains both
        MCP fields and internal fields. filter_tools_by_role() must filter
        out the internal fields before returning to MCP clients.
        """
        # Pick any tool from registry
        sample_tool_name = list(TOOL_REGISTRY.keys())[0]
        sample_tool = TOOL_REGISTRY[sample_tool_name]

        # TOOL_REGISTRY should have internal fields
        assert (
            "required_permission" in sample_tool
        ), "TOOL_REGISTRY should contain internal 'required_permission' field"
        assert (
            "outputSchema" in sample_tool
        ), "TOOL_REGISTRY should contain internal 'outputSchema' field"

        # But these must be filtered out before sending to MCP clients
        # (that's what filter_tools_by_role is supposed to do)

    def test_filter_respects_user_permissions(self):
        """Test that filtering still respects user role permissions."""
        # Create regular user (not admin)
        regular_user = User(
            username="user",
            password_hash="fake",
            role="normal_user",
            created_at=datetime.now(),
        )

        # Get tools for regular user
        user_tools = filter_tools_by_role(regular_user)

        # Get tools for admin
        admin_user = User(
            username="admin",
            password_hash="fake",
            role="admin",
            created_at=datetime.now(),
        )
        admin_tools = filter_tools_by_role(admin_user)

        # Admin should have more or equal tools than regular user
        assert len(admin_tools) >= len(
            user_tools
        ), "Admin should have at least as many tools as regular user"

        # All tools (regardless of role) should be MCP-compliant
        for tool in user_tools + admin_tools:
            assert "required_permission" not in tool
            assert "outputSchema" not in tool
            assert len(tool.keys()) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
