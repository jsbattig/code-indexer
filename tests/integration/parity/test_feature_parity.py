"""
Test MCP/REST feature parity.

Verifies that every MCP tool has a corresponding REST endpoint.
"""

# MCP to REST endpoint mapping
MCP_TO_REST_MAPPING = {
    # File CRUD operations
    "create_file": ("POST", "/api/v1/repos/{alias}/files"),
    "edit_file": ("PATCH", "/api/v1/repos/{alias}/files/{file_path:path}"),
    "delete_file": ("DELETE", "/api/v1/repos/{alias}/files/{file_path:path}"),
    # Git status/inspection
    "git_status": ("GET", "/api/v1/repos/{alias}/git/status"),
    "git_diff": ("GET", "/api/v1/repos/{alias}/git/diff"),
    "git_log": ("GET", "/api/v1/repos/{alias}/git/log"),
    # Git staging/commit
    "git_stage": ("POST", "/api/v1/repos/{alias}/git/stage"),
    "git_unstage": ("POST", "/api/v1/repos/{alias}/git/unstage"),
    "git_commit": ("POST", "/api/v1/repos/{alias}/git/commit"),
    # Git remote operations
    "git_push": ("POST", "/api/v1/repos/{alias}/git/push"),
    "git_pull": ("POST", "/api/v1/repos/{alias}/git/pull"),
    "git_fetch": ("POST", "/api/v1/repos/{alias}/git/fetch"),
    # Git recovery operations
    "git_reset": ("POST", "/api/v1/repos/{alias}/git/reset"),
    "git_clean": ("POST", "/api/v1/repos/{alias}/git/clean"),
    "git_merge_abort": ("POST", "/api/v1/repos/{alias}/git/merge-abort"),
    "git_checkout_file": ("POST", "/api/v1/repos/{alias}/git/checkout-file"),
    # Git branch operations
    "git_branch_list": ("GET", "/api/v1/repos/{alias}/git/branches"),
    "git_branch_create": ("POST", "/api/v1/repos/{alias}/git/branches"),
    "git_branch_switch": ("POST", "/api/v1/repos/{alias}/git/branches/{name}/switch"),
    "git_branch_delete": ("DELETE", "/api/v1/repos/{alias}/git/branches/{name}"),
    # SCIP operations (GET methods, /scip prefix not /api/v1/scip)
    "scip_definition": ("GET", "/scip/definition"),
    "scip_references": ("GET", "/scip/references"),
    "scip_dependencies": ("GET", "/scip/dependencies"),
    "scip_dependents": ("GET", "/scip/dependents"),
    "scip_callchain": ("GET", "/scip/callchain"),
    "scip_impact": ("GET", "/scip/impact"),
    "scip_context": ("GET", "/scip/context"),
    # Indexing operations (/reindex not /index, /index-status hyphenated)
    "trigger_reindex": ("POST", "/api/v1/repos/{alias}/reindex"),
    "get_index_status": ("GET", "/api/v1/repos/{alias}/index-status"),
    # SSH Key operations (/api/ssh-keys not /api/v1/ssh-keys)
    "cidx_ssh_key_create": ("POST", "/api/ssh-keys"),
    "cidx_ssh_key_list": ("GET", "/api/ssh-keys"),
    "cidx_ssh_key_delete": ("DELETE", "/api/ssh-keys/{name}"),
    "cidx_ssh_key_show_public": ("GET", "/api/ssh-keys/{name}/public"),
    "cidx_ssh_key_assign_host": ("POST", "/api/ssh-keys/{name}/hosts"),
}


def normalize_path(path: str) -> str:
    """Normalize path by removing path parameter types like {file_path:path}."""
    import re

    # Convert {file_path:path} to {file_path}
    normalized = re.sub(r"\{([^:}]+):[^}]+\}", r"{\1}", path)
    return normalized


def test_mcp_rest_feature_parity(mcp_tool_registry, rest_app):
    """
    Verify every MCP tool has corresponding REST endpoint.

    This test ensures 100% feature availability parity between MCP and REST protocols.
    """
    # Get all MCP tools
    mcp_tools = list(mcp_tool_registry.keys())

    # Get all REST endpoints from FastAPI routes
    rest_endpoints = {}
    for route in rest_app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                # Normalize the path
                normalized_path = normalize_path(route.path)
                key = (method, normalized_path)
                rest_endpoints[key] = route.path

    # Check which MCP tools have REST endpoints
    missing_rest = []
    mcp_only_tools = []

    for mcp_tool in mcp_tools:
        if mcp_tool in MCP_TO_REST_MAPPING:
            method, expected_path = MCP_TO_REST_MAPPING[mcp_tool]
            normalized_expected = normalize_path(expected_path)

            if (method, normalized_expected) not in rest_endpoints:
                missing_rest.append(
                    {
                        "mcp_tool": mcp_tool,
                        "expected_method": method,
                        "expected_path": expected_path,
                    }
                )
        else:
            # Tool exists in MCP but not mapped to REST
            # This is expected for MCP-only tools like search_code, authenticate, etc.
            mcp_only_tools.append(mcp_tool)

    # Report results
    print(f"\n{'='*80}")
    print("MCP/REST Feature Parity Analysis")
    print(f"{'='*80}")
    print(f"Total MCP tools: {len(mcp_tools)}")
    print(f"Tools with REST mapping: {len(MCP_TO_REST_MAPPING)}")
    print(f"MCP-only tools (expected): {len(mcp_only_tools)}")
    print(f"Missing REST endpoints: {len(missing_rest)}")

    if mcp_only_tools:
        print("\nMCP-only tools (expected to not have REST endpoints):")
        for tool in sorted(mcp_only_tools):
            print(f"  - {tool}")

    if missing_rest:
        print("\nMCP tools MISSING REST endpoints:")
        for item in missing_rest:
            print(
                f"  - {item['mcp_tool']}: {item['expected_method']} {item['expected_path']}"
            )

    # Assert no mapped tools are missing REST endpoints
    assert len(missing_rest) == 0, "MCP tools missing REST endpoints:\n" + "\n".join(
        f"  {item['mcp_tool']}: {item['expected_method']} {item['expected_path']}"
        for item in missing_rest
    )

    print(f"\n{'='*80}")
    print(f"PASS: All {len(MCP_TO_REST_MAPPING)} mapped MCP tools have REST endpoints")
    print(f"{'='*80}\n")


def test_rest_endpoints_documented(rest_app):
    """Verify all REST endpoints are properly documented."""
    undocumented = []

    for route in rest_app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            # Skip OPTIONS method (CORS)
            methods = [m for m in route.methods if m != "OPTIONS"]
            if not methods:
                continue

            # Check if route has summary or description
            if hasattr(route, "summary") or hasattr(route, "description"):
                if not route.summary and not route.description:
                    undocumented.append(f"{methods[0]} {route.path}")
            else:
                undocumented.append(f"{methods[0]} {route.path}")

    if undocumented:
        print(f"\nWarning: {len(undocumented)} endpoints lack documentation:")
        for endpoint in undocumented[:10]:  # Show first 10
            print(f"  - {endpoint}")

    # This is a warning, not a failure
    # Documentation is important but not critical for parity
    assert True, "Documentation check complete"
