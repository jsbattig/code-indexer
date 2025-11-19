"""Unit tests for MCP tool registry - comprehensive validation of all 22 tools."""

from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestToolRegistryStructure:
    """Test tool registry structure and schema validation."""

    def test_registry_contains_22_tools(self):
        """Test that TOOL_REGISTRY contains exactly 22 tools."""
        assert len(TOOL_REGISTRY) == 22, "Registry must contain exactly 22 tools"

    def test_all_tools_have_required_fields(self):
        """Test that all tools have required fields."""
        required_fields = {"name", "description", "inputSchema", "required_permission"}

        for tool_name, tool_def in TOOL_REGISTRY.items():
            assert required_fields.issubset(
                tool_def.keys()
            ), f"Tool {tool_name} missing required fields: {required_fields - set(tool_def.keys())}"
