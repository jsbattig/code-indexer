"""Tests for file CRUD MCP tool definitions.

Story #628: MCP Tool Definitions
Tests the 3 file CRUD tool definitions:
- create_file
- edit_file
- delete_file
"""

import pytest
from jsonschema import validate, ValidationError

from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestCreateFileTool:
    """Test create_file tool definition."""

    def test_tool_exists(self):
        """Verify create_file tool is registered."""
        assert "create_file" in TOOL_REGISTRY

    def test_schema_structure(self):
        """Verify create_file has all required fields."""
        tool = TOOL_REGISTRY["create_file"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "required_permission" in tool
        assert tool["name"] == "create_file"

    def test_schema_valid_input(self):
        """Verify create_file accepts valid parameters."""
        tool = TOOL_REGISTRY["create_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/new_file.py",
            "content": "print('hello')"
        }

        # Should not raise ValidationError
        validate(instance=valid_input, schema=schema)

    def test_schema_missing_required_field(self):
        """Verify create_file rejects missing required parameters."""
        tool = TOOL_REGISTRY["create_file"]
        schema = tool["inputSchema"]

        # Missing content
        invalid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/new_file.py"
        }

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_permission_level(self):
        """Verify create_file requires repository:write permission."""
        tool = TOOL_REGISTRY["create_file"]
        assert tool["required_permission"] == "repository:write"

    def test_description_not_empty(self):
        """Verify create_file has non-empty description."""
        tool = TOOL_REGISTRY["create_file"]
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) > 0


class TestEditFileTool:
    """Test edit_file tool definition."""

    def test_tool_exists(self):
        """Verify edit_file tool is registered."""
        assert "edit_file" in TOOL_REGISTRY

    def test_schema_structure(self):
        """Verify edit_file has all required fields."""
        tool = TOOL_REGISTRY["edit_file"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "required_permission" in tool
        assert tool["name"] == "edit_file"

    def test_schema_valid_input_with_optimistic_locking(self):
        """Verify edit_file accepts valid parameters with optimistic locking."""
        tool = TOOL_REGISTRY["edit_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/existing.py",
            "old_string": "def old_func():",
            "new_string": "def new_func():",
            "content_hash": "abc123def456"
        }

        validate(instance=valid_input, schema=schema)

    def test_schema_with_replace_all_option(self):
        """Verify edit_file accepts optional replace_all parameter."""
        tool = TOOL_REGISTRY["edit_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/existing.py",
            "old_string": "old_name",
            "new_string": "new_name",
            "content_hash": "abc123",
            "replace_all": True
        }

        validate(instance=valid_input, schema=schema)

    def test_schema_missing_content_hash(self):
        """Verify edit_file requires content_hash for optimistic locking."""
        tool = TOOL_REGISTRY["edit_file"]
        schema = tool["inputSchema"]

        invalid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/existing.py",
            "old_string": "old",
            "new_string": "new"
            # Missing content_hash
        }

        with pytest.raises(ValidationError):
            validate(instance=invalid_input, schema=schema)

    def test_permission_level(self):
        """Verify edit_file requires repository:write permission."""
        tool = TOOL_REGISTRY["edit_file"]
        assert tool["required_permission"] == "repository:write"

    def test_description_not_empty(self):
        """Verify edit_file has non-empty description."""
        tool = TOOL_REGISTRY["edit_file"]
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) > 0


class TestDeleteFileTool:
    """Test delete_file tool definition."""

    def test_tool_exists(self):
        """Verify delete_file tool is registered."""
        assert "delete_file" in TOOL_REGISTRY

    def test_schema_structure(self):
        """Verify delete_file has all required fields."""
        tool = TOOL_REGISTRY["delete_file"]
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert "required_permission" in tool
        assert tool["name"] == "delete_file"

    def test_schema_valid_input(self):
        """Verify delete_file accepts valid parameters."""
        tool = TOOL_REGISTRY["delete_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/old_file.py"
        }

        validate(instance=valid_input, schema=schema)

    def test_schema_with_optional_hash(self):
        """Verify delete_file accepts optional content_hash parameter."""
        tool = TOOL_REGISTRY["delete_file"]
        schema = tool["inputSchema"]

        valid_input = {
            "repository_alias": "test-repo",
            "file_path": "src/old_file.py",
            "content_hash": "xyz789"
        }

        validate(instance=valid_input, schema=schema)

    def test_permission_level(self):
        """Verify delete_file requires repository:write permission."""
        tool = TOOL_REGISTRY["delete_file"]
        assert tool["required_permission"] == "repository:write"

    def test_description_not_empty(self):
        """Verify delete_file has non-empty description."""
        tool = TOOL_REGISTRY["delete_file"]
        assert isinstance(tool["description"], str)
        assert len(tool["description"]) > 0
