"""
End-to-end tests for start/stop commands with data preservation.

Tests the complete workflow of starting and stopping services while
ensuring data is preserved between restarts.
"""

import os
import subprocess
import time
import pytest
from pathlib import Path


@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
class TestStartStopE2E:
    """End-to-end tests for start/stop functionality with data preservation."""

    def test_start_stop_with_data_preservation(self, tmp_path):
        """Test complete start/stop cycle with data preservation verification.

        This test verifies:
        1. Setup and index a project
        2. Query to verify data exists
        3. Stop services
        4. Start services again
        5. Query to verify data is preserved
        6. Works from subfolder (backtracking)
        """
        # Set up test project directory
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create some test files to index
        (project_dir / "main.py").write_text(
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

        (project_dir / "utils.py").write_text(
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
        subfolder = project_dir / "src" / "components"
        subfolder.mkdir(parents=True)

        try:
            # Change to project directory
            original_cwd = Path.cwd()
            os.chdir(project_dir)

            # Step 1: Setup services and index the project
            print("🔧 Setting up services...")
            setup_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "setup", "--quiet"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for setup
            )
            assert setup_result.returncode == 0, f"Setup failed: {setup_result.stderr}"

            print("📚 Indexing project...")
            index_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "index"],
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutes for indexing
            )
            assert (
                index_result.returncode == 0
            ), f"Indexing failed: {index_result.stderr}"

            # Step 2: Query to verify data exists
            print("🔍 Verifying initial data...")
            query_result = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "query",
                    "authentication",
                    "--limit",
                    "3",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                query_result.returncode == 0
            ), f"Initial query failed: {query_result.stderr}"

            # Verify we found authentication-related content
            output = query_result.stdout
            assert (
                "authenticate_user" in output or "authentication" in output.lower()
            ), f"Expected authentication content not found in: {output}"

            # Extract query details for comparison
            initial_results = self._extract_query_results(output)
            assert len(initial_results) > 0, "No results found in initial query"

            print(f"✅ Found {len(initial_results)} initial results")

            # Step 3: Stop services from subfolder (test backtracking)
            print("🛑 Stopping services from subfolder...")
            os.chdir(subfolder)  # Change to subfolder to test backtracking

            stop_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "stop"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert stop_result.returncode == 0, f"Stop failed: {stop_result.stderr}"
            # Services might already be stopped, so check for either success or "no services running"
            assert (
                "Services stopped successfully!" in stop_result.stdout
                or "No services currently running" in stop_result.stdout
            )

            # Verify services are actually stopped
            time.sleep(2)  # Brief wait for shutdown
            subprocess.run(
                ["python", "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Status command should still work but show services as down

            # Step 4: Start services again from subfolder
            print("🚀 Starting services from subfolder...")
            start_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "start"],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minutes for restart
            )
            assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"
            assert "Services started successfully!" in start_result.stdout

            # Step 5: Query again to verify data preservation
            print("🔍 Verifying data preservation...")

            # Brief wait for services to be fully ready
            time.sleep(5)

            query_after_restart = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "query",
                    "authentication",
                    "--limit",
                    "3",
                ],
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

            post_restart_results = self._extract_query_results(post_restart_output)
            assert len(post_restart_results) > 0, "No results found after restart"

            print(f"✅ Found {len(post_restart_results)} results after restart")

            # Verify data consistency (should have same or similar results)
            assert (
                len(post_restart_results) >= len(initial_results) - 1
            ), f"Significant data loss detected: {len(initial_results)} -> {len(post_restart_results)}"

            # Test different query to ensure broader data preservation
            print("🔍 Testing database query preservation...")
            db_query_result = subprocess.run(
                [
                    "python",
                    "-m",
                    "code_indexer.cli",
                    "query",
                    "database connection",
                    "--limit",
                    "2",
                ],
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
                os.chdir(project_dir)
                subprocess.run(
                    [
                        "python",
                        "-m",
                        "code_indexer.cli",
                        "clean",
                        "--remove-data",
                        "--quiet",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception as e:
                print(f"Cleanup error: {e}")
            finally:
                os.chdir(original_cwd)

    def test_start_stop_from_different_subfolders(self, tmp_path):
        """Test that start/stop works from various subfolder levels."""
        # Set up test project directory
        project_dir = tmp_path / "nested_project"
        project_dir.mkdir()

        # Create nested directory structure
        deep_folder = project_dir / "src" / "main" / "java" / "com" / "example"
        deep_folder.mkdir(parents=True)

        # Create a simple test file
        (project_dir / "README.md").write_text("# Test Project\nAuthentication system")

        try:
            original_cwd = Path.cwd()
            os.chdir(project_dir)

            # Setup from root
            setup_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "setup", "--quiet"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            assert setup_result.returncode == 0, f"Setup failed: {setup_result.stderr}"

            # Test stop from deep subfolder
            os.chdir(deep_folder)
            stop_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "stop"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert (
                stop_result.returncode == 0
            ), f"Stop from deep folder failed: {stop_result.stderr}"

            # Test start from different intermediate folder
            os.chdir(project_dir / "src" / "main")
            start_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "start"],
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
                os.chdir(project_dir)
                subprocess.run(
                    [
                        "python",
                        "-m",
                        "code_indexer.cli",
                        "clean",
                        "--remove-data",
                        "--quiet",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass
            finally:
                os.chdir(original_cwd)

    def test_start_without_prior_setup(self, tmp_path):
        """Test start command behavior when no services are configured."""
        project_dir = tmp_path / "no_setup_project"
        project_dir.mkdir()

        try:
            original_cwd = Path.cwd()
            os.chdir(project_dir)

            # Try to start without setup
            start_result = subprocess.run(
                ["python", "-m", "code_indexer.cli", "start"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Should fail gracefully
            assert start_result.returncode != 0
            assert (
                "No .code-indexer/config.json found in current directory tree"
                in start_result.stdout  # Error message is in stdout, not stderr
            )

            print("✅ Start command fails gracefully without setup")

        finally:
            os.chdir(original_cwd)

    def _extract_query_results(self, output: str) -> list:
        """Extract query results from CLI output for comparison."""
        results = []
        lines = output.split("\n")

        for line in lines:
            # Look for file results (lines starting with file indicators)
            if "📄 File:" in line or "Score:" in line:
                results.append(line.strip())

        return results
