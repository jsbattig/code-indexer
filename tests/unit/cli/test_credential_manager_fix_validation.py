"""Elite TDD validation tests for ProjectCredentialManager fix.

This test module verifies that all CLI commands properly use project_root
instead of ProjectCredentialManager when calling load_encrypted_credentials.
"""

import ast
from pathlib import Path


def test_cli_credential_loading_fixed():
    """Test that all credential loading in CLI uses project_root, not credential_manager."""
    cli_path = (
        Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "cli.py"
    )

    with open(cli_path, "r") as f:
        cli_content = f.read()

    # Parse the AST to find all calls to load_encrypted_credentials
    tree = ast.parse(cli_content)

    errors = []

    class CredentialCallChecker(ast.NodeVisitor):
        def visit_Call(self, node):
            # Check if this is a call to load_encrypted_credentials
            if (
                isinstance(node.func, ast.Name)
                and node.func.id == "load_encrypted_credentials"
            ):
                # Check the argument
                if node.args:
                    arg = node.args[0]
                    # Check if argument is credential_manager (wrong) or project_root (correct)
                    if isinstance(arg, ast.Name):
                        if arg.id == "credential_manager":
                            errors.append(
                                f"Line {node.lineno}: Found incorrect usage of credential_manager"
                            )
                        elif arg.id != "project_root":
                            # Could be a different variable, let's track it
                            pass
            self.generic_visit(node)

    checker = CredentialCallChecker()
    checker.visit(tree)

    # Assert no errors found
    assert len(errors) == 0, "Found credential_manager usage errors:\n" + "\n".join(
        errors
    )


def test_all_admin_commands_have_cleanup():
    """Test that all admin commands properly close their API clients."""
    cli_path = (
        Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "cli.py"
    )

    with open(cli_path, "r") as f:
        cli_lines = f.readlines()

    # Find all AdminAPIClient instantiations
    admin_client_lines = []
    for i, line in enumerate(cli_lines, 1):
        if "AdminAPIClient(" in line and "admin_client = " in line:
            admin_client_lines.append(i)

    # For each instantiation, verify there's a corresponding close
    missing_cleanup = []
    for client_line in admin_client_lines:
        # Look for close() within reasonable distance (within 200 lines)
        found_close = False
        search_start = client_line
        search_end = min(client_line + 200, len(cli_lines))

        for i in range(search_start, search_end):
            line = cli_lines[i]
            if "admin_client.close()" in line or "await admin_client.close()" in line:
                found_close = True
                break

        if not found_close:
            # Check if it's within a context that has cleanup in finally block
            for i in range(max(0, client_line - 10), search_end):
                if i >= len(cli_lines):
                    break
                line = cli_lines[i]
                if "finally:" in line:
                    # Check if close is in finally block
                    for j in range(i + 1, min(i + 20, len(cli_lines))):
                        finally_line = cli_lines[j]
                        if "admin_client.close()" in finally_line:
                            found_close = True
                            break
                    if found_close:
                        break

        if not found_close:
            missing_cleanup.append(
                f"Line {client_line}: AdminAPIClient created but no close() found"
            )

    # All admin clients should have cleanup
    assert (
        len(missing_cleanup) == 0
    ), "Missing cleanup for admin clients:\n" + "\n".join(missing_cleanup)


def test_repos_api_client_cleanup():
    """Test that ReposAPIClient instances are properly cleaned up."""
    cli_path = (
        Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "cli.py"
    )

    with open(cli_path, "r") as f:
        cli_content = f.read()

    # Check for ReposAPIClient usage (excluding SyncReposAPIClient which doesn't need manual cleanup)
    if "ReposAPIClient(" in cli_content:
        # Find all instantiations
        lines = cli_content.split("\n")
        repos_client_lines = []

        for i, line in enumerate(lines, 1):
            # Only check async ReposAPIClient, not SyncReposAPIClient
            if "ReposAPIClient(" in line and "SyncReposAPIClient" not in line:
                repos_client_lines.append(i)

        # For each, verify cleanup exists
        missing_cleanup = []
        for client_line_num in repos_client_lines:
            # Look for corresponding close within reasonable range
            search_start = client_line_num - 1  # 0-indexed
            search_end = min(client_line_num + 100, len(lines))

            found_close = False
            for i in range(search_start, search_end):
                if i >= len(lines):
                    break
                line = lines[i]
                if ".close()" in line and (
                    "client" in line or "finally:" in lines[max(0, i - 5) : i]
                ):
                    found_close = True
                    break

            if not found_close:
                missing_cleanup.append(
                    f"Line {client_line_num}: ReposAPIClient created but no close() found"
                )

        assert (
            len(missing_cleanup) == 0
        ), "Missing cleanup for repos clients:\n" + "\n".join(missing_cleanup)


def test_no_invalid_credential_manager_usage():
    """Verify no remaining invalid uses of ProjectCredentialManager as path."""
    cli_path = (
        Path(__file__).parent.parent.parent.parent / "src" / "code_indexer" / "cli.py"
    )

    with open(cli_path, "r") as f:
        cli_content = f.read()

    # Should not find patterns like credential_manager being used as path
    invalid_patterns = [
        "load_encrypted_credentials(credential_manager)",
        "credentials_path = credential_manager /",
        "path = credential_manager /",
    ]

    errors = []
    for pattern in invalid_patterns:
        if pattern in cli_content:
            # Find line numbers
            lines = cli_content.split("\n")
            for i, line in enumerate(lines, 1):
                if pattern in line:
                    errors.append(f"Line {i}: Found invalid pattern: {pattern}")

    assert len(errors) == 0, "Found invalid credential_manager usage:\n" + "\n".join(
        errors
    )


if __name__ == "__main__":
    # Run all tests
    test_cli_credential_loading_fixed()
    test_all_admin_commands_have_cleanup()
    test_repos_api_client_cleanup()
    test_no_invalid_credential_manager_usage()
    print("✅ All validation tests passed!")
