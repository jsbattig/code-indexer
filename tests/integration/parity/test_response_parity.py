"""
Test MCP/REST response format parity.

Verifies that MCP and REST return identical JSON structures for critical operations.
"""


def extract_mcp_response_schema(output_schema: dict) -> dict:
    """
    Extract response schema from MCP outputSchema.

    Handles both direct properties and oneOf schemas (merges all properties from all options).
    """
    if "properties" in output_schema:
        return output_schema["properties"]
    elif "oneOf" in output_schema:
        # Merge properties from all oneOf options
        merged_props = {}
        for option in output_schema["oneOf"]:
            if "properties" in option:
                merged_props.update(option["properties"])
        return merged_props
    return {}


def extract_rest_response_schema(model_class) -> dict:
    """Extract response schema from Pydantic response model."""
    if model_class is None:
        return {}
    schema = model_class.schema()
    return schema.get("properties", {})


def assert_response_parity(mcp_tool: str, mcp_output_schema: dict, rest_model):
    """
    Assert that MCP and REST response schemas match.

    Args:
        mcp_tool: Name of MCP tool
        mcp_output_schema: MCP outputSchema dict
        rest_model: Pydantic REST response model class
    """
    mcp_props = set(extract_mcp_response_schema(mcp_output_schema).keys())
    rest_props = set(extract_rest_response_schema(rest_model).keys())

    mcp_only = mcp_props - rest_props
    rest_only = rest_props - mcp_props

    assert mcp_only == set() and rest_only == set(), (
        f"{mcp_tool} response mismatch:\n"
        f"  MCP only: {mcp_only}\n"
        f"  REST only: {rest_only}\n"
        f"  MCP fields: {sorted(mcp_props)}\n"
        f"  REST fields: {sorted(rest_props)}"
    )


# File CRUD Operations


def test_create_file_response_parity(mcp_tool_registry):
    """Verify create_file returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.files import CreateFileResponse

    mcp_output = mcp_tool_registry["create_file"].get("outputSchema", {})

    assert_response_parity("create_file", mcp_output, CreateFileResponse)


def test_edit_file_response_parity(mcp_tool_registry):
    """Verify edit_file returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.files import EditFileResponse

    mcp_output = mcp_tool_registry["edit_file"].get("outputSchema", {})

    assert_response_parity("edit_file", mcp_output, EditFileResponse)


def test_delete_file_response_parity(mcp_tool_registry):
    """Verify delete_file returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.files import DeleteFileResponse

    mcp_output = mcp_tool_registry["delete_file"].get("outputSchema", {})

    assert_response_parity("delete_file", mcp_output, DeleteFileResponse)


# Git Operations


def test_git_status_response_parity(mcp_tool_registry):
    """Verify git_status returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitStatusResponse

    mcp_output = mcp_tool_registry["git_status"].get("outputSchema", {})

    assert_response_parity("git_status", mcp_output, GitStatusResponse)


def test_git_commit_response_parity(mcp_tool_registry):
    """Verify git_commit returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitCommitResponse

    mcp_output = mcp_tool_registry["git_commit"].get("outputSchema", {})

    assert_response_parity("git_commit", mcp_output, GitCommitResponse)


def test_git_push_response_parity(mcp_tool_registry):
    """Verify git_push returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitPushResponse

    mcp_output = mcp_tool_registry["git_push"].get("outputSchema", {})

    assert_response_parity("git_push", mcp_output, GitPushResponse)


def test_git_reset_response_parity(mcp_tool_registry):
    """Verify git_reset returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitResetResponse

    mcp_output = mcp_tool_registry["git_reset"].get("outputSchema", {})

    assert_response_parity("git_reset", mcp_output, GitResetResponse)


def test_git_clean_response_parity(mcp_tool_registry):
    """Verify git_clean returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitCleanResponse

    mcp_output = mcp_tool_registry["git_clean"].get("outputSchema", {})

    assert_response_parity("git_clean", mcp_output, GitCleanResponse)


# Git Branch Operations


def test_git_branch_create_response_parity(mcp_tool_registry):
    """Verify git_branch_create returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitBranchCreateResponse

    mcp_output = mcp_tool_registry["git_branch_create"].get("outputSchema", {})

    assert_response_parity("git_branch_create", mcp_output, GitBranchCreateResponse)


def test_git_branch_list_response_parity(mcp_tool_registry):
    """Verify git_branch_list returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.git_models import GitBranchListResponse

    mcp_output = mcp_tool_registry["git_branch_list"].get("outputSchema", {})

    assert_response_parity("git_branch_list", mcp_output, GitBranchListResponse)


# Indexing Operations


def test_trigger_reindex_response_parity(mcp_tool_registry):
    """Verify trigger_reindex returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.indexing import TriggerReindexResponse

    mcp_output = mcp_tool_registry["trigger_reindex"].get("outputSchema", {})

    assert_response_parity("trigger_reindex", mcp_output, TriggerReindexResponse)


def test_get_index_status_response_parity(mcp_tool_registry):
    """Verify get_index_status returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.indexing import GetIndexStatusResponse

    mcp_output = mcp_tool_registry["get_index_status"].get("outputSchema", {})

    assert_response_parity("get_index_status", mcp_output, GetIndexStatusResponse)


# SCIP Operations


def test_scip_definition_response_parity(mcp_tool_registry):
    """Verify scip_definition returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.scip_queries import ScipDefinitionResponse

    mcp_output = mcp_tool_registry["scip_definition"].get("outputSchema", {})

    assert_response_parity("scip_definition", mcp_output, ScipDefinitionResponse)


def test_scip_references_response_parity(mcp_tool_registry):
    """Verify scip_references returns identical JSON in MCP and REST."""
    from code_indexer.server.routers.scip_queries import ScipReferencesResponse

    mcp_output = mcp_tool_registry["scip_references"].get("outputSchema", {})

    assert_response_parity("scip_references", mcp_output, ScipReferencesResponse)
