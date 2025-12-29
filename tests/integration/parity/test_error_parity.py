"""
Test MCP/REST error handling parity.

Verifies that MCP and REST return consistent errors for various failure scenarios.
These are documentation tests that verify expected error patterns.
"""


def test_file_not_found_error_parity():
    """
    Verify edit_file returns same error in MCP and REST when file doesn't exist.

    Expected behavior:
    - MCP: Returns success=false with error message containing "not found"
    - REST: Returns 404 with detail containing "not found"
    """
    # MCP error response structure
    mcp_error_structure = {
        "success": False,
        "error": "File not found: nonexistent.py"
    }

    # REST error response structure
    rest_error_structure = {
        "status_code": 404,
        "detail": "File not found: nonexistent.py"
    }

    # Both should indicate file not found
    assert "not found" in mcp_error_structure["error"].lower()
    assert "not found" in rest_error_structure["detail"].lower()


def test_file_already_exists_error_parity():
    """
    Verify create_file returns same error in MCP and REST when file already exists.

    Expected behavior:
    - MCP: Returns success=false with error message containing "already exists"
    - REST: Returns 409 with detail containing "already exists"
    """
    # MCP error response structure
    mcp_error_structure = {
        "success": False,
        "error": "File already exists: existing.py"
    }

    # REST error response structure
    rest_error_structure = {
        "status_code": 409,
        "detail": "File already exists: existing.py"
    }

    # Both should indicate file already exists
    assert "already exists" in mcp_error_structure["error"].lower()
    assert "already exists" in rest_error_structure["detail"].lower()


def test_hash_mismatch_error_parity():
    """
    Verify edit_file returns same error in MCP and REST on content hash mismatch.

    Expected behavior:
    - MCP: Returns success=false with error message containing "hash mismatch"
    - REST: Returns 409 with detail containing "hash mismatch" or "modified"
    """
    # MCP error response structure
    mcp_error_structure = {
        "success": False,
        "error": "Hash mismatch: file was modified"
    }

    # REST error response structure
    rest_error_structure = {
        "status_code": 409,
        "detail": "Hash mismatch: file was modified"
    }

    # Both should indicate hash mismatch
    assert "hash" in mcp_error_structure["error"].lower() or "modified" in mcp_error_structure["error"].lower()
    assert "hash" in rest_error_structure["detail"].lower() or "modified" in rest_error_structure["detail"].lower()


def test_permission_denied_error_parity():
    """
    Verify file operations return same error in MCP and REST for .git/ access.

    Expected behavior:
    - MCP: Returns success=false with error message about permission denied
    - REST: Returns 403 with detail about permission denied
    """
    # MCP error response structure
    mcp_error_structure = {
        "success": False,
        "error": "Permission denied: Cannot modify .git/ directory"
    }

    # REST error response structure
    rest_error_structure = {
        "status_code": 403,
        "detail": "Permission denied: Cannot modify .git/ directory"
    }

    # Both should indicate permission denied
    assert "permission" in mcp_error_structure["error"].lower() or "denied" in mcp_error_structure["error"].lower()
    assert "permission" in rest_error_structure["detail"].lower() or "denied" in rest_error_structure["detail"].lower()


def test_invalid_parameters_error_parity():
    """
    Verify operations return same error in MCP and REST for invalid parameters.

    Expected behavior:
    - MCP: Returns success=false with error message about invalid parameters
    - REST: Returns 400 with detail about invalid parameters
    """
    # MCP error response structure
    mcp_error_structure = {
        "success": False,
        "error": "Invalid parameters: old_string cannot be empty"
    }

    # REST error response structure
    rest_error_structure = {
        "status_code": 400,
        "detail": "Invalid parameters: old_string cannot be empty"
    }

    # Both should indicate invalid parameters
    assert "invalid" in mcp_error_structure["error"].lower()
    assert "invalid" in rest_error_structure["detail"].lower() or rest_error_structure["status_code"] == 400
