#!/usr/bin/env python3
"""
Generate MCP/REST Parity Matrix Documentation.

Analyzes MCP TOOL_REGISTRY and FastAPI routes to produce a comprehensive
parity matrix showing which MCP tools have REST endpoints and their parity status.
"""

import sys
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from code_indexer.server.app import create_app
from code_indexer.server.mcp.tools import TOOL_REGISTRY


# MCP to REST mapping (from test_feature_parity.py)
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
    # SCIP operations
    "scip_definition": ("POST", "/api/v1/scip/definition"),
    "scip_references": ("POST", "/api/v1/scip/references"),
    "scip_dependencies": ("POST", "/api/v1/scip/dependencies"),
    "scip_dependents": ("POST", "/api/v1/scip/dependents"),
    "scip_callchain": ("POST", "/api/v1/scip/callchain"),
    "scip_impact": ("POST", "/api/v1/scip/impact"),
    "scip_context": ("POST", "/api/v1/scip/context"),
    # Indexing operations
    "trigger_reindex": ("POST", "/api/v1/repos/{alias}/index"),
    "get_index_status": ("GET", "/api/v1/repos/{alias}/index/status"),
    # SSH Key operations
    "cidx_ssh_key_create": ("POST", "/api/v1/ssh-keys"),
    "cidx_ssh_key_list": ("GET", "/api/v1/ssh-keys"),
    "cidx_ssh_key_delete": ("DELETE", "/api/v1/ssh-keys/{name}"),
    "cidx_ssh_key_show_public": ("GET", "/api/v1/ssh-keys/{name}/public"),
    "cidx_ssh_key_assign_host": ("POST", "/api/v1/ssh-keys/{name}/hosts"),
}


def normalize_path(path: str) -> str:
    """Normalize path by removing path parameter types."""
    return re.sub(r"\{([^:}]+):[^}]+\}", r"{\1}", path)


def categorize_tool(tool_name: str) -> str:
    """Categorize MCP tool by function."""
    if tool_name.startswith("git_"):
        if tool_name in [
            "git_branch_list",
            "git_branch_create",
            "git_branch_switch",
            "git_branch_delete",
        ]:
            return "Git Branches"
        elif tool_name in ["git_push", "git_pull", "git_fetch"]:
            return "Git Remote"
        elif tool_name in [
            "git_reset",
            "git_clean",
            "git_merge_abort",
            "git_checkout_file",
        ]:
            return "Git Recovery"
        elif tool_name in ["git_stage", "git_unstage", "git_commit"]:
            return "Git Staging"
        else:
            return "Git Inspection"
    elif tool_name.startswith("scip_"):
        return "SCIP"
    elif tool_name.startswith("cidx_ssh_key_"):
        return "SSH Keys"
    elif tool_name in ["create_file", "edit_file", "delete_file"]:
        return "File CRUD"
    elif tool_name in ["trigger_reindex", "get_index_status"]:
        return "Indexing"
    elif tool_name.startswith("search_") or tool_name == "regex_search":
        return "Search"
    elif "repo" in tool_name.lower():
        return "Repository Mgmt"
    elif "user" in tool_name.lower():
        return "User Mgmt"
    else:
        return "Other"


def collect_rest_endpoints(app):
    """Collect all REST endpoints from FastAPI app."""
    if not app or not hasattr(app, "routes"):
        raise ValueError("Invalid FastAPI app: missing routes")

    rest_endpoints = set()
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method != "OPTIONS":
                    normalized_path = normalize_path(route.path)
                    rest_endpoints.add((method, normalized_path))
    return rest_endpoints


def build_matrix_data(rest_endpoints):
    """Build matrix data for all MCP tools."""
    matrix_data = []
    for tool_name in sorted(TOOL_REGISTRY.keys()):
        tool_def = TOOL_REGISTRY[tool_name]
        category = categorize_tool(tool_name)

        # Check if tool has REST endpoint
        has_rest = "No"
        rest_endpoint = "-"
        if tool_name in MCP_TO_REST_MAPPING:
            method, path = MCP_TO_REST_MAPPING[tool_name]
            normalized = normalize_path(path)
            if (method, normalized) in rest_endpoints:
                has_rest = "Yes"
                rest_endpoint = f"{method} {path}"
            else:
                has_rest = "Missing"
                rest_endpoint = f"{method} {path} (expected)"

        # Check for schemas
        has_input_schema = "Yes" if tool_def.get("inputSchema") else "No"
        has_output_schema = "Yes" if tool_def.get("outputSchema") else "No"

        matrix_data.append(
            {
                "tool": tool_name,
                "category": category,
                "has_rest": has_rest,
                "rest_endpoint": rest_endpoint,
                "input_schema": has_input_schema,
                "output_schema": has_output_schema,
            }
        )
    return matrix_data


def generate_markdown_output(matrix_data):
    """Generate markdown output from matrix data."""
    output = []
    output.append("# MCP/REST Parity Matrix\n")
    output.append(f"**Generated:** {Path(__file__).name}\n")
    output.append(f"**Total MCP Tools:** {len(TOOL_REGISTRY)}\n")
    output.append(
        f"**Tools with REST Endpoints:** {sum(1 for d in matrix_data if d['has_rest'] == 'Yes')}\n"
    )
    output.append(
        f"**MCP-only Tools:** {sum(1 for d in matrix_data if d['has_rest'] == 'No')}\n"
    )
    output.append(
        f"**Missing REST Endpoints:** {sum(1 for d in matrix_data if d['has_rest'] == 'Missing')}\n\n"
    )

    # Group by category
    categories = {}
    for item in matrix_data:
        cat = item["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(item)

    # Generate table per category
    for category in sorted(categories.keys()):
        items = categories[category]
        output.append(f"## {category}\n")
        output.append("| MCP Tool | REST Endpoint | Input Schema | Output Schema |\n")
        output.append("|----------|---------------|--------------|---------------|\n")

        for item in items:
            status_icon = ""
            if item["has_rest"] == "Yes":
                status_icon = " ✓"
            elif item["has_rest"] == "Missing":
                status_icon = " ✗"

            output.append(
                f"| {item['tool']}{status_icon} | "
                f"{item['rest_endpoint']} | "
                f"{item['input_schema']} | "
                f"{item['output_schema']} |\n"
            )
        output.append("\n")

    # Add legend
    output.append("## Legend\n")
    output.append("- ✓ = REST endpoint exists\n")
    output.append("- ✗ = REST endpoint missing (expected to exist)\n")
    output.append("- No marker = MCP-only tool (no REST endpoint expected)\n")

    return "".join(output)


def generate_matrix():
    """Generate parity matrix markdown."""
    app = create_app()
    rest_endpoints = collect_rest_endpoints(app)
    matrix_data = build_matrix_data(rest_endpoints)
    return generate_markdown_output(matrix_data)


def main():
    """Main entry point."""
    try:
        print("Generating MCP/REST Parity Matrix...")

        matrix = generate_matrix()

        # Write to docs
        output_file = (
            Path(__file__).parent.parent / "docs" / "mcp-rest-parity-matrix.md"
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)

        output_file.write_text(matrix)
        print(f"✓ Generated: {output_file}")
        print(f"  Size: {len(matrix)} bytes")

    except ImportError as e:
        print(f"✗ Failed to import required modules: {e}")
        sys.exit(1)
    except IOError as e:
        print(f"✗ Failed to write output file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
