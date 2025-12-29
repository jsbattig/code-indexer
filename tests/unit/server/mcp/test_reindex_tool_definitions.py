"""Tests for re-indexing MCP tool definitions.

Story #628: MCP Tool Definitions
Tests the 2 re-indexing tool definitions:
- trigger_reindex
- get_index_status
"""

import pytest
from jsonschema import validate, ValidationError, Draft7Validator

from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestTriggerReindexTool:
    """Test trigger_reindex tool definition."""

    def test_tool_exists(self):
        """Verify trigger_reindex tool is registered."""
        assert "trigger_reindex" in TOOL_REGISTRY

    def test_schema_structure(self):
        """Verify trigger_reindex has all required fields."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "required_permission" in tool
        assert tool["name"] == "trigger_reindex"

    def test_schema_valid_input(self):
        """Verify trigger_reindex accepts valid index types."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "index_types": ["semantic", "fts"]
        }
        validate(instance=valid_input, schema=schema)

    def test_schema_all_index_types(self):
        """Verify trigger_reindex accepts all valid index type enums."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "index_types": ["semantic", "fts", "temporal", "scip"]
        }
        validate(instance=valid_input, schema=schema)

    def test_schema_invalid_index_type(self):
        """Verify trigger_reindex rejects invalid index types."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        invalid_input = {
            "repository_alias": "test-repo",
            "index_types": ["semantic", "invalid_type"]
        }

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_schema_with_clear_flag(self):
        """Verify trigger_reindex accepts optional clear parameter."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "index_types": ["semantic"],
            "clear": True
        }
        validate(instance=valid_input, schema=schema)

    def test_schema_missing_required_field(self):
        """Verify trigger_reindex requires index_types."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        invalid_input = {
            "repository_alias": "test-repo"
            # Missing index_types
        }

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_permission_level(self):
        """Verify trigger_reindex requires repository:write permission."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        assert tool["required_permission"] == "repository:write"

    def test_description_not_empty(self):
        """Verify trigger_reindex has non-empty description."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) > 0

    def test_schema_is_valid_json_schema(self):
        """Verify trigger_reindex inputSchema is valid JSON schema."""
        tool = TOOL_REGISTRY["trigger_reindex"]
        schema = tool["inputSchema"]

        # Should not raise exception
        Draft7Validator.check_schema(schema)


class TestGetIndexStatusTool:
    """Test get_index_status tool definition."""

    def test_tool_exists(self):
        """Verify get_index_status tool is registered."""
        assert "get_index_status" in TOOL_REGISTRY

    def test_schema_structure(self):
        """Verify get_index_status has all required fields."""
        tool = TOOL_REGISTRY["get_index_status"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "required_permission" in tool
        assert tool["name"] == "get_index_status"

    def test_schema_valid_input(self):
        """Verify get_index_status accepts valid repository_alias."""
        tool = TOOL_REGISTRY["get_index_status"]
        schema = tool["inputSchema"]

        valid_input = {"repository_alias": "test-repo"}
        validate(instance=valid_input, schema=schema)

    def test_schema_missing_required_field(self):
        """Verify get_index_status requires repository_alias."""
        tool = TOOL_REGISTRY["get_index_status"]
        schema = tool["inputSchema"]

        invalid_input = {}

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_permission_level(self):
        """Verify get_index_status requires repository:read permission."""
        tool = TOOL_REGISTRY["get_index_status"]
        assert tool["required_permission"] == "repository:read"

    def test_description_not_empty(self):
        """Verify get_index_status has non-empty description."""
        tool = TOOL_REGISTRY["get_index_status"]
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) > 0

    def test_schema_is_valid_json_schema(self):
        """Verify get_index_status inputSchema is valid JSON schema."""
        tool = TOOL_REGISTRY["get_index_status"]
        schema = tool["inputSchema"]

        # Should not raise exception
        Draft7Validator.check_schema(schema)
