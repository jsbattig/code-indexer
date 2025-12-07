"""
Test query parameter parity across CLI, REST API, and MCP API.

Phase 4 of Story #503: Automated validation that all query parameters are consistently
available across all interfaces (CLI, REST, MCP).

These tests enforce 100% query parameter parity by:
1. Verifying all 23 parameters exist in each interface
2. Checking parameter name consistency
3. Validating parameter type compatibility
4. Detecting any missing or extra parameters

Test Methodology:
- CLI parameters extracted from --help output parsing
- REST parameters extracted from SemanticQueryRequest Pydantic model
- MCP parameters extracted from search_code tool schema

CRITICAL: These tests prevent future parity regressions. If any test fails, it indicates
a parameter was added/removed from one interface without updating others.
"""

import subprocess
import re
from typing import Set
import pytest

from code_indexer.server.app import SemanticQueryRequest
from code_indexer.server.mcp.tools import TOOL_REGISTRY


# Complete parameter inventory (24 parameters)
# Based on Phases 1-3 completion: all parameters now present in REST/MCP
# CLI has subset (19 parameters - missing some API-only temporal params)

# All parameters across all interfaces
ALL_PARAMETERS = {
    # Core parameters (present from initial implementation)
    "query",  # query_text in REST/MCP
    "limit",
    "min_score",
    "file_extensions",
    # Language/path filtering
    "language",
    "path_filter",
    # Exclusion filters (Phase 1)
    "exclude_language",
    "exclude_path",
    # Accuracy profile (Phase 1)
    "accuracy",
    # Search mode selection
    "search_mode",  # semantic/fts/hybrid
    # FTS-specific parameters (Phase 2)
    "case_sensitive",
    "fuzzy",
    "edit_distance",
    "snippet_lines",
    "regex",
    # Temporal query parameters (Story #446)
    "time_range",
    "time_range_all",
    "at_commit",
    "include_removed",
    "show_evolution",
    "evolution_limit",
    # Temporal filtering parameters (Phase 3)
    "diff_type",
    "author",
    "chunk_type",
    # Omni-search parameters (Story #521)
    "aggregation_mode",
    "exclude_patterns",
}

# CLI-specific: subset of parameters (some temporal params are API-only)
CLI_EXPECTED_PARAMETERS = ALL_PARAMETERS - {
    "at_commit",  # API-only: not exposed in CLI
    "include_removed",  # API-only: not exposed in CLI
    "show_evolution",  # API-only: not exposed in CLI
    "evolution_limit",  # API-only: not exposed in CLI
    "file_extensions",  # API-only: REST/MCP use this, CLI doesn't have --file-extensions
    "aggregation_mode",  # API-only: omni-search aggregation mode
    "exclude_patterns",  # API-only: omni-search repository exclusion
}

# REST/MCP: full parameter set
API_EXPECTED_PARAMETERS = ALL_PARAMETERS


def get_cli_parameters() -> Set[str]:
    """
    Extract query parameters from CLI --help output.

    Returns:
        Set of parameter names (without -- prefix)
    """
    # Run CLI help command
    result = subprocess.run(
        ["python3", "-m", "code_indexer.cli", "query", "--help"],
        capture_output=True,
        text=True,
        cwd="/home/jsbattig/Dev/code-indexer",
    )

    if result.returncode != 0:
        pytest.fail(f"CLI help command failed: {result.stderr}")

    help_output = result.stdout

    # Parse parameter names from help output
    # Format: "  -l, --limit INTEGER" or "  --language TEXT"
    param_pattern = re.compile(r"^\s*(?:-\w,\s*)?--([a-z_-]+)\s+", re.MULTILINE)
    matches = param_pattern.findall(help_output)

    # Convert to set and normalize names (replace hyphens with underscores)
    cli_params = {name.replace("-", "_") for name in matches}

    # Remove non-query parameters (help, quiet, remote mode flags)
    cli_params.discard("help")
    cli_params.discard("quiet")
    cli_params.discard("remote")

    # Normalize parameter name differences between interfaces
    # CLI uses 'query' as positional arg (QUERY in help), REST/MCP use 'query_text'
    # For parity purposes, treat them as equivalent

    return cli_params


def get_rest_parameters() -> Set[str]:
    """
    Extract query parameters from REST API SemanticQueryRequest model.

    Returns:
        Set of parameter names from Pydantic model fields
    """
    # Get model fields
    model_fields = SemanticQueryRequest.model_fields

    # Extract field names
    rest_params = set(model_fields.keys())

    # Remove non-query parameters (request-specific fields)
    rest_params.discard("repository_alias")  # Target selection, not query parameter
    rest_params.discard("async_query")  # Execution mode, not query parameter

    return rest_params


def get_mcp_parameters() -> Set[str]:
    """
    Extract query parameters from MCP API search_code tool schema.

    Returns:
        Set of parameter names from MCP tool input schema
    """
    # Get search_code tool schema
    search_tool = TOOL_REGISTRY.get("search_code")
    if not search_tool:
        pytest.fail("search_code tool not found in MCP registry")

    input_schema = search_tool["inputSchema"]
    properties = input_schema.get("properties", {})

    # Extract property names
    mcp_params = set(properties.keys())

    # Remove non-query parameters
    mcp_params.discard("repository_alias")  # Target selection, not query parameter

    return mcp_params


class TestQueryParameterParity:
    """Test suite for query parameter parity across all interfaces."""

    def test_total_parameter_count(self):
        """Verify total number of expected query parameters."""
        # Should have exactly 26 query parameters (excluding repository_alias, async_query)
        # Updated from 24 to 26 after adding omni-search parameters (aggregation_mode, exclude_patterns)
        assert (
            len(ALL_PARAMETERS) == 26
        ), f"Expected 26 parameters, got {len(ALL_PARAMETERS)}: {sorted(ALL_PARAMETERS)}"

        # CLI should have 19 parameters (subset of all parameters)
        # Unchanged - omni-search parameters are API-only
        assert (
            len(CLI_EXPECTED_PARAMETERS) == 19
        ), f"Expected 19 CLI parameters, got {len(CLI_EXPECTED_PARAMETERS)}: {sorted(CLI_EXPECTED_PARAMETERS)}"

        # REST/MCP should have all 26 parameters
        # Updated from 24 to 26 after adding omni-search parameters
        assert (
            len(API_EXPECTED_PARAMETERS) == 26
        ), f"Expected 26 API parameters, got {len(API_EXPECTED_PARAMETERS)}: {sorted(API_EXPECTED_PARAMETERS)}"

    def test_cli_has_all_parameters(self):
        """Verify CLI exposes all 19 expected query parameters (updated from 18 after adding time_range_all)."""
        cli_params = get_cli_parameters()

        missing = CLI_EXPECTED_PARAMETERS - cli_params

        # Account for CLI-specific naming: query is positional (not --query)
        # Remove 'query' and 'query_text' from missing check since CLI uses positional arg
        missing.discard("query")
        missing.discard("query_text")

        # CLI uses --fts/--semantic flags instead of --search-mode
        # This is a design difference: CLI has separate flags, REST/MCP have enum field
        missing.discard("search_mode")

        assert not missing, f"CLI missing parameters: {sorted(missing)}"

    def test_rest_has_all_parameters(self):
        """Verify REST API exposes all 23 query parameters."""
        rest_params = get_rest_parameters()

        missing = API_EXPECTED_PARAMETERS - rest_params

        # Normalize: REST uses 'query_text' instead of 'query'
        if "query_text" in rest_params:
            missing.discard("query")

        assert not missing, f"REST API missing parameters: {sorted(missing)}"

    def test_mcp_has_all_parameters(self):
        """Verify MCP API exposes all 23 query parameters."""
        mcp_params = get_mcp_parameters()

        missing = API_EXPECTED_PARAMETERS - mcp_params

        # Normalize: MCP uses 'query_text' instead of 'query'
        if "query_text" in mcp_params:
            missing.discard("query")

        assert not missing, f"MCP API missing parameters: {sorted(missing)}"

    def test_no_extra_cli_parameters(self):
        """Verify CLI doesn't expose unexpected query parameters."""
        cli_params = get_cli_parameters()

        # Normalize for comparison
        normalized_expected = CLI_EXPECTED_PARAMETERS.copy()
        normalized_expected.discard("query")
        normalized_expected.add("fts")  # CLI has --fts flag
        normalized_expected.add("semantic")  # CLI has --semantic flag
        normalized_expected.discard("search_mode")  # CLI uses --fts/--semantic instead

        # Add CLI-specific flags that are acceptable
        normalized_expected.add("time_range_all")  # Shortcut for full temporal range
        normalized_expected.add("case_insensitive")  # Inverse of case_sensitive
        normalized_expected.add("repo")  # Story #521: Global repo query via --repo flag

        extra = cli_params - normalized_expected

        assert not extra, f"CLI has unexpected parameters: {sorted(extra)}"

    def test_no_extra_rest_parameters(self):
        """Verify REST API doesn't expose unexpected query parameters."""
        rest_params = get_rest_parameters()

        # Normalize: REST uses query_text instead of query
        normalized_expected = API_EXPECTED_PARAMETERS.copy()
        normalized_expected.discard("query")
        normalized_expected.add("query_text")

        extra = rest_params - normalized_expected

        assert not extra, f"REST API has unexpected parameters: {sorted(extra)}"

    def test_no_extra_mcp_parameters(self):
        """Verify MCP API doesn't expose unexpected query parameters."""
        mcp_params = get_mcp_parameters()

        # Normalize: MCP uses query_text instead of query
        normalized_expected = API_EXPECTED_PARAMETERS.copy()
        normalized_expected.discard("query")
        normalized_expected.add("query_text")

        # MCP-only parameters (not in REST, but intentionally MCP-only)
        # response_format: Story #582 - omni-search result grouping (flat vs grouped)
        normalized_expected.add("response_format")

        extra = mcp_params - normalized_expected

        assert not extra, f"MCP API has unexpected parameters: {sorted(extra)}"

    def test_parameter_name_consistency_rest_mcp(self):
        """Verify parameter names are consistent between REST and MCP."""
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        # MCP-only parameters that are intentionally not in REST
        # response_format: Story #582 - omni-search result grouping
        mcp_only_params = {"response_format"}

        # REST and MCP should have identical parameter names
        # (except for documented MCP-only parameters)

        rest_only = rest_params - mcp_params
        mcp_only = mcp_params - rest_params - mcp_only_params

        assert not rest_only, f"Parameters only in REST: {sorted(rest_only)}"
        assert (
            not mcp_only
        ), f"Parameters only in MCP (excluding documented MCP-only): {sorted(mcp_only)}"

    def test_core_parameters_exist(self):
        """Verify core query parameters exist in all interfaces."""

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        # CLI should have limit and min_score (query is positional)
        assert "limit" in cli_params
        assert "min_score" in cli_params

        # REST should have query_text, limit, min_score
        assert "query_text" in rest_params
        assert "limit" in rest_params
        assert "min_score" in rest_params

        # MCP should have query_text, limit, min_score
        assert "query_text" in mcp_params
        assert "limit" in mcp_params
        assert "min_score" in mcp_params

    def test_phase1_parameters_exist(self):
        """Verify Phase 1 parameters exist in all interfaces (Story #503)."""
        phase1_params = {"exclude_language", "exclude_path", "accuracy", "regex"}

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        missing_cli = phase1_params - cli_params
        missing_rest = phase1_params - rest_params
        missing_mcp = phase1_params - mcp_params

        assert (
            not missing_cli
        ), f"Phase 1 parameters missing from CLI: {sorted(missing_cli)}"
        assert (
            not missing_rest
        ), f"Phase 1 parameters missing from REST: {sorted(missing_rest)}"
        assert (
            not missing_mcp
        ), f"Phase 1 parameters missing from MCP: {sorted(missing_mcp)}"

    def test_phase2_fts_parameters_exist(self):
        """Verify Phase 2 FTS parameters exist in all interfaces (Story #503)."""
        phase2_params = {"case_sensitive", "fuzzy", "edit_distance", "snippet_lines"}

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        missing_cli = phase2_params - cli_params
        missing_rest = phase2_params - rest_params
        missing_mcp = phase2_params - mcp_params

        assert (
            not missing_cli
        ), f"Phase 2 FTS parameters missing from CLI: {sorted(missing_cli)}"
        assert (
            not missing_rest
        ), f"Phase 2 FTS parameters missing from REST: {sorted(missing_rest)}"
        assert (
            not missing_mcp
        ), f"Phase 2 FTS parameters missing from MCP: {sorted(missing_mcp)}"

    def test_phase3_temporal_filtering_parameters_exist(self):
        """Verify Phase 3 temporal filtering parameters exist in all interfaces (Story #503)."""
        phase3_params = {"diff_type", "author", "chunk_type"}

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        missing_cli = phase3_params - cli_params
        missing_rest = phase3_params - rest_params
        missing_mcp = phase3_params - mcp_params

        assert (
            not missing_cli
        ), f"Phase 3 temporal parameters missing from CLI: {sorted(missing_cli)}"
        assert (
            not missing_rest
        ), f"Phase 3 temporal parameters missing from REST: {sorted(missing_rest)}"
        assert (
            not missing_mcp
        ), f"Phase 3 temporal parameters missing from MCP: {sorted(missing_mcp)}"

    def test_temporal_parameters_exist(self):
        """Verify temporal query parameters exist in interfaces (Story #446)."""
        # All temporal params
        all_temporal_params = {
            "time_range",
            "at_commit",
            "include_removed",
            "show_evolution",
            "evolution_limit",
        }

        # CLI only has time_range (others are API-only)
        cli_temporal_params = {"time_range"}

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        missing_cli = cli_temporal_params - cli_params
        missing_rest = all_temporal_params - rest_params
        missing_mcp = all_temporal_params - mcp_params

        assert (
            not missing_cli
        ), f"Temporal parameters missing from CLI: {sorted(missing_cli)}"
        assert (
            not missing_rest
        ), f"Temporal parameters missing from REST: {sorted(missing_rest)}"
        assert (
            not missing_mcp
        ), f"Temporal parameters missing from MCP: {sorted(missing_mcp)}"

    def test_language_path_filters_exist(self):
        """Verify language and path filtering parameters exist in all interfaces."""
        filter_params = {"language", "path_filter", "exclude_language", "exclude_path"}

        cli_params = get_cli_parameters()
        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        missing_cli = filter_params - cli_params
        missing_rest = filter_params - rest_params
        missing_mcp = filter_params - mcp_params

        assert (
            not missing_cli
        ), f"Filter parameters missing from CLI: {sorted(missing_cli)}"
        assert (
            not missing_rest
        ), f"Filter parameters missing from REST: {sorted(missing_rest)}"
        assert (
            not missing_mcp
        ), f"Filter parameters missing from MCP: {sorted(missing_mcp)}"

    def test_search_mode_parameters_exist(self):
        """Verify search mode selection parameters exist in REST and MCP."""
        # CLI uses --fts and --semantic flags instead of search_mode enum
        # REST and MCP use search_mode enum field

        rest_params = get_rest_parameters()
        mcp_params = get_mcp_parameters()

        assert "search_mode" in rest_params, "search_mode missing from REST API"
        assert "search_mode" in mcp_params, "search_mode missing from MCP API"

    def test_rest_parameter_types(self):
        """Verify REST API parameter types are correct."""
        model_fields = SemanticQueryRequest.model_fields

        # Check specific parameter types
        # Basic types
        assert model_fields["query_text"].annotation is str
        assert model_fields["limit"].annotation is int
        assert model_fields["case_sensitive"].annotation is bool
        assert model_fields["fuzzy"].annotation is bool
        assert model_fields["edit_distance"].annotation is int
        assert model_fields["snippet_lines"].annotation is int
        assert model_fields["regex"].annotation is bool

        # Optional types - just check they exist and have default None
        assert "min_score" in model_fields
        assert model_fields["min_score"].default is None

    def test_mcp_parameter_types(self):
        """Verify MCP API parameter types are correct."""
        search_tool = TOOL_REGISTRY["search_code"]
        properties = search_tool["inputSchema"]["properties"]

        # Check specific parameter types
        assert properties["query_text"]["type"] == "string"
        assert properties["limit"]["type"] == "integer"
        assert properties["min_score"]["type"] == "number"
        assert properties["accuracy"]["type"] == "string"
        assert properties["accuracy"]["enum"] == ["fast", "balanced", "high"]
        assert properties["case_sensitive"]["type"] == "boolean"
        assert properties["fuzzy"]["type"] == "boolean"
        assert properties["edit_distance"]["type"] == "integer"
        assert properties["snippet_lines"]["type"] == "integer"
        assert properties["regex"]["type"] == "boolean"

    def test_parameter_defaults_consistency(self):
        """Verify parameter default values are consistent across REST and MCP."""
        rest_fields = SemanticQueryRequest.model_fields
        search_tool = TOOL_REGISTRY["search_code"]
        mcp_properties = search_tool["inputSchema"]["properties"]

        # Check default value consistency for parameters with defaults
        # limit: 10 in both
        assert rest_fields["limit"].default == 10
        assert mcp_properties["limit"]["default"] == 10

        # accuracy: 'balanced' in both
        assert rest_fields["accuracy"].default == "balanced"
        assert mcp_properties["accuracy"]["default"] == "balanced"

        # case_sensitive: False in both
        assert rest_fields["case_sensitive"].default is False
        assert mcp_properties["case_sensitive"]["default"] is False

        # fuzzy: False in both
        assert rest_fields["fuzzy"].default is False
        assert mcp_properties["fuzzy"]["default"] is False

        # edit_distance: 0 in both
        assert rest_fields["edit_distance"].default == 0
        assert mcp_properties["edit_distance"]["default"] == 0

        # snippet_lines: 5 in both
        assert rest_fields["snippet_lines"].default == 5
        assert mcp_properties["snippet_lines"]["default"] == 5

        # regex: False in both
        assert rest_fields["regex"].default is False
        assert mcp_properties["regex"]["default"] is False
