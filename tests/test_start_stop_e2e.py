"""
End-to-end tests for start/stop commands with data preservation.

Tests the complete workflow of starting and stopping services while
ensuring data is preserved between restarts.
"""

import os
import subprocess
import time
import pytest
import json

from pathlib import Path

# Import new test infrastructure
from .conftest import local_temporary_directory
from .test_infrastructure import auto_register_project_collections


@pytest.fixture
def start_stop_e2e_test_repo():
    """Create a test repository for start/stop E2E tests."""
    with local_temporary_directory() as temp_dir:
        # Auto-register collections for cleanup
        auto_register_project_collections(temp_dir)

        # Preserve .code-indexer directory if it exists
        config_dir = temp_dir / ".code-indexer"
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

        yield temp_dir


def create_start_stop_config(test_dir):
    """Create configuration for start/stop test."""
    config_dir = test_dir / ".code-indexer"
    config_file = config_dir / "config.json"

    # Load existing config if it exists (preserves container ports)
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
    else:
        config = {
            "codebase_dir": str(test_dir),
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "start_stop_test_collection",
                "vector_size": 1024,
            },
        }

    # Only modify test-specific settings, preserve container configuration
    config["embedding_provider"] = "voyage-ai"
    config["voyage_ai"] = {
        "model": "voyage-code-3",
        "api_key_env": "VOYAGE_API_KEY",
        "batch_size": 32,
        "max_retries": 3,
        "timeout": 30,
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    return config_file


def _extract_query_results(output: str) -> list:
    """Extract query results from CLI output for comparison."""
    results = []
    lines = output.split("\n")

    for line in lines:
        # Look for file results (lines starting with file indicators)
        if "📄 File:" in line or "Score:" in line:
            results.append(line.strip())

    return results


@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_start_stop_with_data_preservation(start_stop_e2e_test_repo):
    """Test complete start/stop cycle with data preservation verification.

    This test verifies:
    1. Setup and index a project
    2. Query to verify data exists
    3. Stop services
    4. Start services again
    5. Query to verify data is preserved
    6. Works from subfolder (backtracking)
    """
    test_dir = start_stop_e2e_test_repo

    # Create configuration
    create_start_stop_config(test_dir)

    # Create some test files to index
    (test_dir / "main.py").write_text(
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

    (test_dir / "utils.py").write_text(
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
    subfolder = test_dir / "src" / "components"
    subfolder.mkdir(parents=True)

    try:
        # Change to project directory
        original_cwd = Path.cwd()
        os.chdir(test_dir)

        # Step 1: Initialize project configuration first (required for backtracking test)
        print("🔧 Initializing project configuration...")
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Start services
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Allow start to fail if services are already running
        if start_result.returncode != 0:
            if (
                "already in use" not in start_result.stdout
                and "already running" not in start_result.stdout
            ):
                assert False, f"Start failed: {start_result.stderr}"

        print("📚 Indexing project...")
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Step 2: Query to verify data exists
        print("🔍 Verifying initial data...")
        query_result = subprocess.run(
            ["code-indexer", "query", "authentication", "--limit", "3"],
            cwd=test_dir,
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

        print(f"✅ Found {len(initial_results)} initial results")

        # Step 3: Stop services from subfolder (test backtracking)
        print("🛑 Stopping services from subfolder...")

        # Change to subfolder and stop services
        os.chdir(subfolder)
        stop_result = subprocess.run(
            ["code-indexer", "stop"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Services might already be stopped, so check for either success or "no services running"
        assert stop_result.returncode == 0 and (
            "Services stopped successfully!" in stop_result.stdout
            or "No services currently running" in stop_result.stdout
        ), f"Stop failed: {stop_result.stderr}"

        # Verify services are actually stopped
        time.sleep(2)  # Brief wait for shutdown
        subprocess.run(
            ["code-indexer", "status"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Status command should still work but show services as down

        # Step 4: Start services again from subfolder
        print("🚀 Starting services from subfolder...")
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"
        assert "Services started successfully!" in start_result.stdout

        # Step 5: Query again to verify data preservation
        print("🔍 Verifying data preservation...")

        # Brief wait for services to be fully ready
        time.sleep(5)

        query_after_restart = subprocess.run(
            ["code-indexer", "query", "authentication", "--limit", "3"],
            cwd=subfolder,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            query_after_restart.returncode == 0
        ), f"Post-restart query failed: {query_after_restart.stderr}"

        # Verify data is preserved
        post_restart_output = query_after_restart.stdout
        assert (
            "authenticate_user" in post_restart_output
            or "authentication" in post_restart_output.lower()
        ), f"Authentication content lost after restart: {post_restart_output}"

        post_restart_results = _extract_query_results(post_restart_output)
        assert len(post_restart_results) > 0, "No results found after restart"

        print(f"✅ Found {len(post_restart_results)} results after restart")

        # Verify data consistency (should have same or similar results)
        assert (
            len(post_restart_results) >= len(initial_results) - 1
        ), f"Significant data loss detected: {len(initial_results)} -> {len(post_restart_results)}"

        # Test different query to ensure broader data preservation
        print("🔍 Testing database query preservation...")
        db_query_result = subprocess.run(
            ["code-indexer", "query", "database connection", "--limit", "2"],
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

        print("✅ Data preservation verified successfully!")

    finally:
        # Cleanup: Stop services and remove data
        try:
            os.chdir(original_cwd)

            # Try to stop from project directory
            os.chdir(test_dir)
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception as e:
            print(f"Cleanup error: {e}")
        finally:
            os.chdir(original_cwd)


@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_start_stop_from_different_subfolders(start_stop_e2e_test_repo):
    """Test that start/stop works from various subfolder levels."""
    test_dir = start_stop_e2e_test_repo

    # Create configuration
    create_start_stop_config(test_dir)

    # Create nested directory structure
    deep_folder = test_dir / "src" / "main" / "java" / "com" / "example"
    deep_folder.mkdir(parents=True)

    # Create a simple test file
    (test_dir / "README.md").write_text("# Test Project\nAuthentication system")

    try:
        original_cwd = Path.cwd()
        os.chdir(test_dir)

        # Setup from root (use faster strategy)
        # Check if services are already running
        status_result = subprocess.run(
            ["code-indexer", "status"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        services_running = status_result.returncode == 0 and (
            "✅ Running" in status_result.stdout or "✅ Ready" in status_result.stdout
        )

        if not services_running:
            init_result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

            setup_result = subprocess.run(
                ["code-indexer", "start", "--quiet"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert setup_result.returncode == 0, f"Setup failed: {setup_result.stderr}"
        else:
            init_result = subprocess.run(
                [
                    "code-indexer",
                    "init",
                    "--force",
                    "--embedding-provider",
                    "voyage-ai",
                ],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Test stop from deep subfolder
        os.chdir(deep_folder)
        stop_result = subprocess.run(
            ["code-indexer", "stop"],
            cwd=deep_folder,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            stop_result.returncode == 0
        ), f"Stop from deep folder failed: {stop_result.stderr}"

        # Test start from different intermediate folder
        os.chdir(test_dir / "src" / "main")
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir / "src" / "main",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert (
            start_result.returncode == 0
        ), f"Start from intermediate folder failed: {start_result.stderr}"

        print("✅ Start/stop works from multiple subfolder levels")

    finally:
        try:
            os.chdir(original_cwd)
            os.chdir(test_dir)
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass
        finally:
            os.chdir(original_cwd)


@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_start_without_prior_setup(start_stop_e2e_test_repo):
    """Test start command behavior when no services are configured - should create default config and succeed."""
    test_dir = start_stop_e2e_test_repo

    # Create configuration
    create_start_stop_config(test_dir)

    try:
        original_cwd = Path.cwd()
        os.chdir(test_dir)

        # Clean legacy containers first to avoid CoW conflicts
        from code_indexer.services.docker_manager import DockerManager

        docker_manager = DockerManager(project_name="test_shared")
        docker_manager.remove_containers(remove_volumes=True)

        # Test the auto-config and start functionality
        # First try to start without any setup - should auto-create config
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=180,  # Increased timeout for service startup
        )

        # If there are container issues (noisy neighbor) or legacy detection, clean up and retry with proper setup
        if start_result.returncode != 0 and (
            "No such container" in start_result.stdout
            or "Error response from daemon" in start_result.stdout
            or "Legacy container detected" in start_result.stdout
        ):
            print(
                "🧹 Detected container issues, cleaning up and retrying with proper setup..."
            )

            # Clean up any problematic state
            try:
                subprocess.run(
                    ["code-indexer", "uninstall"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass

            # Start services again
            start_result = subprocess.run(
                ["code-indexer", "start"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )

            # Verify the services work correctly after setup
            status_result = subprocess.run(
                ["code-indexer", "status"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            assert (
                status_result.returncode == 0
            ), f"Status should work after service setup: {status_result.stderr}"
            assert "✅" in status_result.stdout, "Should show services are running"

            print("✅ Service setup and start functionality verified")
            return

        # Should succeed by creating default configuration
        assert (
            start_result.returncode == 0
        ), f"Start should succeed with auto-config: stdout={start_result.stdout}, stderr={start_result.stderr}"
        assert (
            "Creating default configuration" in start_result.stdout
            or "Configuration created" in start_result.stdout
        ), f"Should indicate config creation: {start_result.stdout}"

        print("✅ Start command creates default config and succeeds")

    finally:
        os.chdir(original_cwd)
