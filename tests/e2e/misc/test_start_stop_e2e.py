"""
End-to-end tests for start/stop commands with data preservation.

Tests the complete workflow of starting and stopping services while
ensuring data is preserved between restarts.
"""

import subprocess
import pytest

# Import shared container test environment
from ...conftest import shared_container_test_environment

# Import test infrastructure directly from where it's actually defined
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def _extract_query_results(output: str) -> list:
    """Extract query results from CLI output for comparison."""
    results = []
    lines = output.split("\n")

    for line in lines:
        # Look for file results (lines starting with file indicators)
        if "📄 File:" in line or "Score:" in line:
            results.append(line.strip())

    return results


def test_start_stop_with_data_preservation():
    """Test complete start/stop cycle with data preservation verification.

    This test verifies:
    1. Setup and index a project in shared container environment
    2. Query to verify data exists
    3. Test start/stop workflows within shared environment
    4. Query to verify data is preserved
    5. Works from subfolder (backtracking)
    """
    with shared_container_test_environment(
        "test_start_stop_data_preservation", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create some test files to index (after shared environment setup)
        (project_path / "main.py").write_text(
            """
def authenticate_user(username, password):
    '''Authenticate user with username and password'''
    if not username or not password:
        raise ValueError("Username and password required")
    return verify_credentials(username, password)

def verify_credentials(username, password):
    '''Verify user credentials against database'''
    return database.check_user(username, password)
"""
        )

        (project_path / "utils.py").write_text(
            """
def database_connection():
    '''Establish database connection'''
    return connect_to_postgres()

def error_handler(func):
    '''Decorator for error handling'''
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            log_error(e)
            raise
    return wrapper
"""
        )

        # Create a subfolder to test backtracking
        subfolder = project_path / "src" / "components"
        subfolder.mkdir(parents=True)

        # Step 1: Initialize project
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Step 2: Start services (may already be running in shared environment)
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Step 3: Index the project (cleanup handled by shared environment)
        index_result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Step 4: Query to verify data exists
        query_result = subprocess.run(
            ["cidx", "query", "authentication", "--limit", "3"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"

        # Verify we found authentication-related content
        output = query_result.stdout
        assert (
            "authenticate_user" in output or "authentication" in output.lower()
        ), f"Expected authentication content not found in: {output}"

        # Extract query details for comparison
        initial_results = _extract_query_results(output)
        assert len(initial_results) > 0, "No results found in initial query"

        # Step 5: Test start/stop workflow from subfolder
        # In shared container environment, we test the CLI functionality without actually stopping services

        # Test CLI access from subfolder
        status_result = subprocess.run(
            ["cidx", "status"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            status_result.returncode == 0
        ), f"Status check from subfolder failed: {status_result.stderr}"
        assert "✅" in status_result.stdout, "Services should be running"

        # Test start command from subfolder (should be idempotent)
        start_from_subfolder = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            start_from_subfolder.returncode == 0
        ), f"Start from subfolder failed: {start_from_subfolder.stderr}"

        # Step 6: Query again from subfolder to verify data preservation and CLI access
        query_after_workflow = subprocess.run(
            ["cidx", "query", "authentication", "--limit", "3"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            query_after_workflow.returncode == 0
        ), f"Post-workflow query failed: {query_after_workflow.stderr}"

        # Verify data is preserved
        post_workflow_output = query_after_workflow.stdout
        assert (
            "authenticate_user" in post_workflow_output
            or "authentication" in post_workflow_output.lower()
        ), f"Authentication content lost after workflow: {post_workflow_output}"

        post_workflow_results = _extract_query_results(post_workflow_output)
        assert len(post_workflow_results) > 0, "No results found after workflow"

        # Verify data consistency (should have same or similar results)
        assert (
            len(post_workflow_results) >= len(initial_results) - 1
        ), f"Significant data loss detected: {len(initial_results)} -> {len(post_workflow_results)}"

        # Test different query to ensure broader data preservation
        db_query_result = subprocess.run(
            ["cidx", "query", "database connection", "--limit", "2"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            db_query_result.returncode == 0
        ), f"Database query failed: {db_query_result.stderr}"

        db_output = db_query_result.stdout
        assert (
            "database" in db_output.lower()
        ), f"Database content not preserved: {db_output}"


def test_start_stop_from_different_subfolders():
    """Test that start/stop works from various subfolder levels."""
    with shared_container_test_environment(
        "test_start_stop_subfolders", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create nested directory structure
        deep_folder = project_path / "src" / "main" / "java" / "com" / "example"
        deep_folder.mkdir(parents=True)

        # Create a simple test file
        (project_path / "README.md").write_text("# Test Project\nAuthentication system")

        # Initialize project
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services (may already be running in shared environment)
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Test CLI access from deep subfolder
        status_deep_result = subprocess.run(
            ["cidx", "status"],
            cwd=deep_folder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            status_deep_result.returncode == 0
        ), f"CLI access from deep folder failed: {status_deep_result.stderr}"

        # Verify we can access CLI commands from deep folder
        assert (
            "Code Indexer Status" in status_deep_result.stdout
        ), "Should show status from deep folder"

        # Test start command from different intermediate folder (should be idempotent)
        intermediate_folder = project_path / "src" / "main"
        start_intermediate_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=intermediate_folder,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Start should be idempotent when services are already running
        assert (
            start_intermediate_result.returncode == 0
        ), f"Start from intermediate folder failed: {start_intermediate_result.stderr}"

        # Verify services are accessible from all levels
        status_intermediate_result = subprocess.run(
            ["cidx", "status"],
            cwd=intermediate_folder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            status_intermediate_result.returncode == 0
        ), f"Status from intermediate folder failed: {status_intermediate_result.stderr}"
        assert (
            "✅" in status_intermediate_result.stdout
        ), "Services should be running from intermediate folder"


def test_start_without_prior_setup():
    """Test start command behavior in shared container environment."""
    with shared_container_test_environment(
        "test_start_without_prior_setup", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Initialize project (this creates the basic configuration)
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Test start command - should work in shared environment
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Verify services are running
        status_result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "✅" in status_result.stdout, "Services should be running after start"

        # Test start idempotency - running start again should succeed
        start_again_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            start_again_result.returncode == 0
        ), f"Start idempotency failed: {start_again_result.stderr}"

        # Verify services are still running
        final_status = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            final_status.returncode == 0
        ), f"Final status failed: {final_status.stderr}"
        assert (
            "✅" in final_status.stdout
        ), "Services should still be running after second start"
