"""
Test MCP/REST parameter schema parity.

Verifies that MCP inputSchema matches REST request models for all operations.
"""

import pytest
from pydantic import BaseModel


def normalize_mcp_params(mcp_schema: dict) -> set:
    """
    Extract parameter names from MCP inputSchema.

    Handles protocol differences:
    - MCP has repository_alias in body
    - REST has it in path
    """
    if "properties" not in mcp_schema:
        return set()

    params = set(mcp_schema["properties"].keys())

    # Remove repository_alias if present (it's in path for REST)
    params.discard("repository_alias")

    return params


def normalize_rest_params(model_class: BaseModel, include_path_params: list = None) -> set:
    """
    Extract parameter names from Pydantic model.

    Args:
        model_class: Pydantic model class
        include_path_params: List of path parameters to include (e.g., ['file_path'])
    """
    if model_class is None:
        params = set()
    else:
        schema = model_class.schema()
        params = set(schema.get("properties", {}).keys())

    # Add path parameters
    if include_path_params:
        params.update(include_path_params)

    return params


def assert_schema_parity(mcp_tool: str, mcp_schema: dict, rest_model: BaseModel,
                          path_params: list = None, optional_in_rest: list = None,
                          rest_params_explicit: list = None):
    """
    Assert that MCP and REST schemas have matching parameters.

    Args:
        mcp_tool: Name of MCP tool
        mcp_schema: MCP inputSchema dict
        rest_model: Pydantic REST request model class (or None for Query-param endpoints)
        path_params: Path parameters in REST (not in body)
        optional_in_rest: Parameters that are optional in REST (query params, etc.) - DEPRECATED when using rest_params_explicit
        rest_params_explicit: Explicit list of REST parameters (for Query-param endpoints without Pydantic models)
    """
    mcp_params = normalize_mcp_params(mcp_schema)

    # Use explicit REST params if provided (for Query-param endpoints)
    if rest_params_explicit is not None:
        rest_params = set(rest_params_explicit)
    else:
        rest_params = normalize_rest_params(rest_model, path_params or [])

    # Remove parameters that are optional in REST (query params, defaults, etc.)
    # This is deprecated when using rest_params_explicit
    if optional_in_rest and rest_params_explicit is None:
        for param in optional_in_rest:
            rest_params.discard(param)

    mcp_only = mcp_params - rest_params
    rest_only = rest_params - mcp_params

    assert mcp_only == set() and rest_only == set(), (
        f"{mcp_tool} parameter mismatch:\n"
        f"  MCP only: {mcp_only}\n"
        f"  REST only: {rest_only}\n"
        f"  MCP params: {sorted(mcp_params)}\n"
        f"  REST params: {sorted(rest_params)}"
    )


# File CRUD Operations


def test_create_file_parameter_parity(mcp_tool_registry):
    """Verify create_file has same parameters in MCP and REST."""
    from code_indexer.server.routers.files import CreateFileRequest

    mcp_schema = mcp_tool_registry["create_file"]["inputSchema"]

    assert_schema_parity(
        "create_file",
        mcp_schema,
        CreateFileRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_edit_file_parameter_parity(mcp_tool_registry):
    """Verify edit_file has same parameters in MCP and REST."""
    from code_indexer.server.routers.files import EditFileRequest

    mcp_schema = mcp_tool_registry["edit_file"]["inputSchema"]

    assert_schema_parity(
        "edit_file",
        mcp_schema,
        EditFileRequest,
        path_params=["file_path"],
        optional_in_rest=[]
    )


def test_delete_file_parameter_parity(mcp_tool_registry):
    """Verify delete_file has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["delete_file"]["inputSchema"]

    # DELETE with file_path in path, content_hash in query (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "delete_file",
        mcp_schema,
        None,
        rest_params_explicit=["file_path", "content_hash"]
    )


# Git Status/Inspection Operations


def test_git_status_parameter_parity(mcp_tool_registry):
    """Verify git_status has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_status"]["inputSchema"]

    # GET request with no body
    assert_schema_parity(
        "git_status",
        mcp_schema,
        None,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_diff_parameter_parity(mcp_tool_registry):
    """Verify git_diff has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_diff"]["inputSchema"]

    # GET request with query params (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "git_diff",
        mcp_schema,
        None,
        rest_params_explicit=["context_lines", "from_revision", "to_revision", "path", "stat_only"]
    )


def test_git_log_parameter_parity(mcp_tool_registry):
    """Verify git_log has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_log"]["inputSchema"]

    # GET request with query params (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "git_log",
        mcp_schema,
        None,
        rest_params_explicit=["limit", "path", "author", "since", "until", "branch", "aggregation_mode", "response_format"]
    )


# Git Staging/Commit Operations


def test_git_stage_parameter_parity(mcp_tool_registry):
    """Verify git_stage has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitStageRequest

    mcp_schema = mcp_tool_registry["git_stage"]["inputSchema"]

    assert_schema_parity(
        "git_stage",
        mcp_schema,
        GitStageRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_unstage_parameter_parity(mcp_tool_registry):
    """Verify git_unstage has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitUnstageRequest

    mcp_schema = mcp_tool_registry["git_unstage"]["inputSchema"]

    assert_schema_parity(
        "git_unstage",
        mcp_schema,
        GitUnstageRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_commit_parameter_parity(mcp_tool_registry):
    """Verify git_commit has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitCommitRequest

    mcp_schema = mcp_tool_registry["git_commit"]["inputSchema"]

    assert_schema_parity(
        "git_commit",
        mcp_schema,
        GitCommitRequest,
        path_params=[],
        optional_in_rest=[]
    )


# Git Remote Operations


def test_git_push_parameter_parity(mcp_tool_registry):
    """Verify git_push has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitPushRequest

    mcp_schema = mcp_tool_registry["git_push"]["inputSchema"]

    assert_schema_parity(
        "git_push",
        mcp_schema,
        GitPushRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_pull_parameter_parity(mcp_tool_registry):
    """Verify git_pull has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitPullRequest

    mcp_schema = mcp_tool_registry["git_pull"]["inputSchema"]

    assert_schema_parity(
        "git_pull",
        mcp_schema,
        GitPullRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_fetch_parameter_parity(mcp_tool_registry):
    """Verify git_fetch has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitFetchRequest

    mcp_schema = mcp_tool_registry["git_fetch"]["inputSchema"]

    assert_schema_parity(
        "git_fetch",
        mcp_schema,
        GitFetchRequest,
        path_params=[],
        optional_in_rest=[]
    )


# Git Recovery Operations


def test_git_reset_parameter_parity(mcp_tool_registry):
    """Verify git_reset has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitResetRequest

    mcp_schema = mcp_tool_registry["git_reset"]["inputSchema"]

    assert_schema_parity(
        "git_reset",
        mcp_schema,
        GitResetRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_clean_parameter_parity(mcp_tool_registry):
    """Verify git_clean has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitCleanRequest

    mcp_schema = mcp_tool_registry["git_clean"]["inputSchema"]

    assert_schema_parity(
        "git_clean",
        mcp_schema,
        GitCleanRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_merge_abort_parameter_parity(mcp_tool_registry):
    """Verify git_merge_abort has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_merge_abort"]["inputSchema"]

    # POST with no body (no request model)
    assert_schema_parity(
        "git_merge_abort",
        mcp_schema,
        None,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_checkout_file_parameter_parity(mcp_tool_registry):
    """Verify git_checkout_file has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitCheckoutFileRequest

    mcp_schema = mcp_tool_registry["git_checkout_file"]["inputSchema"]

    assert_schema_parity(
        "git_checkout_file",
        mcp_schema,
        GitCheckoutFileRequest,
        path_params=[],
        optional_in_rest=[]
    )


# Git Branch Operations


def test_git_branch_list_parameter_parity(mcp_tool_registry):
    """Verify git_branch_list has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_branch_list"]["inputSchema"]

    # GET with no parameters
    assert_schema_parity(
        "git_branch_list",
        mcp_schema,
        None,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_branch_create_parameter_parity(mcp_tool_registry):
    """Verify git_branch_create has same parameters in MCP and REST."""
    from code_indexer.server.routers.git_models import GitBranchCreateRequest

    mcp_schema = mcp_tool_registry["git_branch_create"]["inputSchema"]

    assert_schema_parity(
        "git_branch_create",
        mcp_schema,
        GitBranchCreateRequest,
        path_params=[],
        optional_in_rest=[]
    )


def test_git_branch_switch_parameter_parity(mcp_tool_registry):
    """Verify git_branch_switch has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_branch_switch"]["inputSchema"]

    # POST with branch name in path
    assert_schema_parity(
        "git_branch_switch",
        mcp_schema,
        None,
        path_params=["branch_name"],
        optional_in_rest=[]
    )


def test_git_branch_delete_parameter_parity(mcp_tool_registry):
    """Verify git_branch_delete has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["git_branch_delete"]["inputSchema"]

    # DELETE with branch name in path, confirmation_token in query (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "git_branch_delete",
        mcp_schema,
        None,
        rest_params_explicit=["branch_name", "confirmation_token"]
    )


# SCIP Operations


def test_scip_definition_parameter_parity(mcp_tool_registry):
    """Verify scip_definition has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["scip_definition"]["inputSchema"]

    # GET request with query params (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "scip_definition",
        mcp_schema,
        None,
        rest_params_explicit=["symbol", "exact", "project"]
    )


def test_scip_references_parameter_parity(mcp_tool_registry):
    """Verify scip_references has same parameters in MCP and REST."""
    mcp_schema = mcp_tool_registry["scip_references"]["inputSchema"]

    # GET request with query params (explicit REST params for Query-based endpoint)
    assert_schema_parity(
        "scip_references",
        mcp_schema,
        None,
        rest_params_explicit=["symbol", "limit", "exact", "project"]
    )
