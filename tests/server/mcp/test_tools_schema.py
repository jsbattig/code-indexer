"""
Tests for MCP tools.py schema definitions.

Validates that tool schemas are correctly defined and accept expected input types.
"""

import pytest
from code_indexer.server.mcp.tools import TOOL_REGISTRY


class TestSearchCodeSchema:
    """Test search_code tool schema definition."""

    def test_search_code_schema_exists(self):
        """search_code tool schema exists in registry."""
        assert "search_code" in TOOL_REGISTRY
        schema = TOOL_REGISTRY["search_code"]
        assert "inputSchema" in schema
        assert "properties" in schema["inputSchema"]

    def test_repository_alias_accepts_string(self):
        """repository_alias schema accepts string type."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        repo_alias_schema = schema["properties"]["repository_alias"]

        # Should have oneOf with string as first option
        assert "oneOf" in repo_alias_schema
        assert len(repo_alias_schema["oneOf"]) == 2
        assert repo_alias_schema["oneOf"][0]["type"] == "string"

    def test_repository_alias_accepts_array(self):
        """repository_alias schema accepts array type."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        repo_alias_schema = schema["properties"]["repository_alias"]

        # Should have oneOf with array as second option
        assert "oneOf" in repo_alias_schema
        assert repo_alias_schema["oneOf"][1]["type"] == "array"
        assert repo_alias_schema["oneOf"][1]["items"]["type"] == "string"

    def test_exclude_patterns_schema_definition(self):
        """exclude_patterns parameter is defined as array of strings."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        assert "exclude_patterns" in schema["properties"]

        exclude_patterns_schema = schema["properties"]["exclude_patterns"]
        assert exclude_patterns_schema["type"] == "array"
        assert exclude_patterns_schema["items"]["type"] == "string"

    def test_aggregation_mode_schema_definition(self):
        """aggregation_mode parameter is defined with correct enum values."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        assert "aggregation_mode" in schema["properties"]

        aggregation_mode_schema = schema["properties"]["aggregation_mode"]
        assert aggregation_mode_schema["type"] == "string"
        assert "enum" in aggregation_mode_schema
        assert set(aggregation_mode_schema["enum"]) == {"global", "per_repo"}
        assert aggregation_mode_schema["default"] == "global"

    def test_omni_search_parameters_have_descriptions(self):
        """Omni-search parameters have meaningful descriptions."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]

        # repository_alias should describe both modes
        repo_alias_schema = schema["properties"]["repository_alias"]
        assert "description" in repo_alias_schema
        assert "omni-search" in repo_alias_schema["description"].lower()

        # exclude_patterns should explain usage
        exclude_schema = schema["properties"]["exclude_patterns"]
        assert "description" in exclude_schema
        assert "regex" in exclude_schema["description"].lower()

        # aggregation_mode should explain modes
        agg_schema = schema["properties"]["aggregation_mode"]
        assert "description" in agg_schema
        assert "global" in agg_schema["description"]
        assert "per_repo" in agg_schema["description"]

    def test_required_fields_unchanged(self):
        """Required fields remain query_text only (backward compatible)."""
        schema = TOOL_REGISTRY["search_code"]["inputSchema"]
        assert "required" in schema
        assert schema["required"] == ["query_text"]

        # Omni-search parameters are optional
        assert "repository_alias" not in schema.get("required", [])
        assert "exclude_patterns" not in schema.get("required", [])
        assert "aggregation_mode" not in schema.get("required", [])
