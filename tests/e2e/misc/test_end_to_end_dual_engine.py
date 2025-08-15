#!/usr/bin/env python3
"""
End-to-end tests using ONLY user-level CLI orchestration.
Tests the actual user experience by running the same commands users would run.

This test suite exposes application flaws by trusting CLI commands to work properly.
If tests fail, it indicates real issues in the application code that need fixing.
"""

import os
import subprocess
from pathlib import Path
import pytest

from ...conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def dual_engine_test_repo(request):
    """Create a test repository for dual engine tests."""
    # Get force_docker parameter from the test's parametrization
    force_docker = False

    # For parametrized tests, get the parameter value from the test method
    if hasattr(request, "node") and hasattr(request.node, "callspec"):
        # Extract force_docker from the test's parametrization
        force_docker = request.node.callspec.params.get("force_docker", False)

    with local_temporary_directory(force_docker=force_docker) as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.END_TO_END_DUAL_ENGINE
        )

        yield temp_dir


def create_dual_engine_test_project(test_dir):
    """Create a simple test project with some code files"""
    # Create a basic Python project structure
    (test_dir / "src").mkdir(parents=True, exist_ok=True)

    # Create test Python files
    (test_dir / "src" / "main.py").write_text(
        '''
def authenticate_user(username, password):
    """User authentication function"""
    if username and password:
        return True
    return False

class DatabaseConnection:
    """Database connection handler"""
    def __init__(self, host, port):
        self.host = host
        self.port = port
    
    def connect(self):
        """Connect to database"""
        pass
'''
    )

    (test_dir / "src" / "api.py").write_text(
        '''
from fastapi import FastAPI
app = FastAPI()

@app.post("/login")
async def login_endpoint(username: str, password: str):
    """REST API login endpoint"""
    return {"status": "success"}

@app.get("/users")
async def get_users():
    """Get all users endpoint"""
    return {"users": []}
'''
    )

    (test_dir / "tests").mkdir()
    (test_dir / "tests" / "test_auth.py").write_text(
        '''
import unittest
from unittest.mock import Mock

class TestAuthentication(unittest.TestCase):
    """Unit tests for authentication"""
    
    def test_login_with_mock(self):
        """Test login with mocked dependencies"""
        mock_db = Mock()
        mock_db.authenticate.return_value = True
        assert mock_db.authenticate("user", "pass")
'''
    )

    # Initialize git repository so CLI can detect project root
    subprocess.run(["git", "init"], cwd=test_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=test_dir,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=test_dir,
        capture_output=True,
        check=True,
    )

    # Create .gitignore to prevent committing .code-indexer directory
    (test_dir / ".gitignore").write_text(
        """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
    )

    subprocess.run(["git", "add", "."], cwd=test_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=test_dir,
        capture_output=True,
        check=True,
    )


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
class TestEndToEndDualEngine:
    """Test CLI commands with both Podman (default) and Docker (--force-docker)"""

    def run_cli_command(self, args, test_dir, timeout=120, expect_success=True):
        """Run code-indexer CLI command using high-level application functions"""
        import sys

        cmd_str = " ".join(["code-indexer"] + args)
        print(f"Running: {cmd_str}")

        # Use subprocess to call the actual CLI command exactly as a user would
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli"] + args,
            capture_output=True,
            text=True,
            cwd=test_dir,
            timeout=timeout,
        )

        print(f"Return code: {result.returncode}")
        if result.stdout:
            print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")

        if expect_success and result.returncode != 0:
            pytest.fail(
                f"Command failed: {cmd_str}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
            )

        return result

    def verify_no_root_owned_files(self):
        """Verify that no root-owned files are left in the data directory after cleanup.

        This method provides immediate feedback when cleanup fails to remove root-owned files,
        which cause Qdrant startup failures in subsequent tests.
        """
        import subprocess
        import os

        try:
            # Check for root-owned files in the global data directory
            global_data_dir = Path.home() / ".code-indexer-data"
            if not global_data_dir.exists():
                return  # No data directory means no files to check

            # Use find command to locate files not owned by current user
            current_user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
            result = subprocess.run(
                ["find", str(global_data_dir), "-not", "-user", current_user],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                root_owned_files = result.stdout.strip().split("\n")
                pytest.fail(
                    f"CLEANUP VERIFICATION FAILED: Found {len(root_owned_files)} root-owned files after cleanup!\n"
                    f"These files will cause Qdrant permission errors in subsequent tests:\n"
                    + "\n".join(
                        f"  - {file}" for file in root_owned_files[:10]
                    )  # Show first 10 files
                    + (
                        f"\n  ... and {len(root_owned_files) - 10} more files"
                        if len(root_owned_files) > 10
                        else ""
                    )
                    + f"\n\nTo fix manually: sudo rm -rf {global_data_dir}/qdrant/collections"
                )

        except Exception as e:
            # Don't fail the test for verification errors, but warn
            print(f"Warning: Could not verify root-owned file cleanup: {e}")

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_full_user_workflow(self, dual_engine_test_repo, force_docker):
        """Test complete user workflow: init → setup → index → query → clean"""
        test_dir = dual_engine_test_repo
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing full user workflow with {engine_name} ===")

        # Create test project
        create_dual_engine_test_project(test_dir)

        try:
            original_cwd = Path.cwd()
            os.chdir(test_dir)

            # Step 1: User initializes project with VoyageAI for CI stability
            # Note: Using --force since setup may have already initialized
            self.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], test_dir
            )

            # Verify expected outcome: config file exists
            # Note: CLI currently creates config in home directory, not project directory
            config_file_project = test_dir / ".code-indexer" / "config.json"
            config_file_home = Path.home() / ".code-indexer" / "config.json"

            # Check both locations due to CLI behavior
            config_exists = config_file_project.exists() or config_file_home.exists()
            assert (
                config_exists
            ), f"init should create config file (checked {config_file_project} and {config_file_home})"

            # Step 2: User starts services
            setup_args = ["start", "--quiet"]
            if force_docker:
                setup_args.append("--force-docker")
            self.run_cli_command(setup_args, test_dir, timeout=180)

            # Step 3: User indexes their code
            self.run_cli_command(["index"], test_dir, timeout=120)

            # Step 4: User searches their code
            result = self.run_cli_command(
                ["query", "authentication function"], test_dir, timeout=60
            )
            assert (
                "authenticate_user" in result.stdout
            ), "Should find authentication function"

            result = self.run_cli_command(
                ["query", "REST API endpoint"], test_dir, timeout=60
            )
            assert "login_endpoint" in result.stdout, "Should find API endpoint"

            # Step 5: User checks system status
            status_args = ["status"]
            if force_docker:
                status_args.append("--force-docker")
            result = self.run_cli_command(status_args, test_dir)
            assert "✅" in result.stdout, "Status should show healthy system"

            # Step 6: User cleans up their project data (keeping services for other projects)
            clean_args = ["clean-data"]
            if force_docker:
                clean_args.append("--force-docker")
            self.run_cli_command(clean_args, test_dir, timeout=90)

        finally:
            try:
                os.chdir(original_cwd)
                # Clean up
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_clean_command_effectiveness(self, dual_engine_test_repo, force_docker):
        """Test that clean command actually cleans up properly"""
        test_dir = dual_engine_test_repo
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing clean command effectiveness with {engine_name} ===")

        # Create test project
        create_dual_engine_test_project(test_dir)

        try:
            original_cwd = Path.cwd()
            os.chdir(test_dir)

            # User starts services
            setup_args = ["start", "--quiet"]
            if force_docker:
                setup_args.append("--force-docker")
            self.run_cli_command(setup_args, test_dir, timeout=180)

            # Verify services are running
            status_args = ["status"]
            if force_docker:
                status_args.append("--force-docker")
            result = self.run_cli_command(status_args, test_dir)
            assert "✅" in result.stdout, "Services should be running after setup"

            # User cleans project data using clean-data command
            clean_args = ["clean-data"]
            if force_docker:
                clean_args.append("--force-docker")
            self.run_cli_command(clean_args, test_dir, timeout=90)

            # Verify cleanup worked by checking status - services should remain running but data should be cleared
            result = self.run_cli_command(status_args, test_dir)
            # After clean-data, services should still be running (containers preserved) but index should be cleared
            assert (
                "✅" in result.stdout
            ), "Services should still be running after clean-data"
            # The collection still exists but with 0 documents after clean-data
            assert (
                "Points: 0" in result.stdout
                or "0 docs" in result.stdout
                or "0 points" in result.stdout.lower()
            ), f"Index should show 0 documents after clean-data: {result.stdout}"

        finally:
            try:
                os.chdir(original_cwd)
                # Clean up
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_service_engine_isolation(self, dual_engine_test_repo, force_docker):
        """Test that different engines don't interfere with each other"""
        test_dir = dual_engine_test_repo
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing service isolation with {engine_name} ===")

        # Check if container engine is available
        engine_cmd = "docker" if force_docker else "podman"
        try:
            check_result = subprocess.run(
                [engine_cmd, "--version"], capture_output=True, timeout=5
            )
            if check_result.returncode != 0:
                pytest.skip(f"{engine_name} not available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip(f"{engine_name} not available")

        # Create test project
        create_dual_engine_test_project(test_dir)

        try:
            original_cwd = Path.cwd()
            os.chdir(test_dir)

            # User starts services with specific engine
            setup_args = ["start", "--quiet"]
            if force_docker:
                setup_args.append("--force-docker")
            self.run_cli_command(setup_args, test_dir, timeout=180)

            # Check that services are working
            status_args = ["status"]
            if force_docker:
                status_args.append("--force-docker")
            result = self.run_cli_command(status_args, test_dir)

            # Verify expected components are present
            assert "Qdrant" in result.stdout, "Status should show Qdrant"

            # Clean up project data after test to prevent state leakage
            clean_args = ["clean-data"]
            if force_docker:
                clean_args.append("--force-docker")
            self.run_cli_command(clean_args, test_dir, timeout=90)

        finally:
            try:
                os.chdir(original_cwd)
                # Clean up
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_performance_configuration(self, dual_engine_test_repo, force_docker):
        """Test setup with custom performance settings"""
        test_dir = dual_engine_test_repo
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing performance configuration with {engine_name} ===")

        # Create test project
        create_dual_engine_test_project(test_dir)

        try:
            original_cwd = Path.cwd()
            os.chdir(test_dir)

            # Initialize with VoyageAI provider first
            self.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"], test_dir
            )

            # User configures performance settings
            setup_args = [
                "start",
                "--parallel-requests",
                "2",
                "--max-models",
                "1",
                "--queue-size",
                "1024",
                "--quiet",
            ]
            if force_docker:
                setup_args.append("--force-docker")

            self.run_cli_command(setup_args, test_dir, timeout=180)

            # Verify setup succeeded with custom config
            status_args = ["status"]
            if force_docker:
                status_args.append("--force-docker")
            result = self.run_cli_command(status_args, test_dir)

            assert (
                "✅" in result.stdout
            ), "Setup with custom performance config should work"
            assert "Ready" in result.stdout, "Services should be ready"

            # Clean up project data after test to prevent state leakage
            clean_args = ["clean-data"]
            if force_docker:
                clean_args.append("--force-docker")
            self.run_cli_command(clean_args, test_dir, timeout=90)

        finally:
            try:
                os.chdir(original_cwd)
                # Clean up
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass

    def test_sequential_engine_usage(self, dual_engine_test_repo):
        """Test that both engines can be used sequentially without conflicts"""
        test_dir = dual_engine_test_repo
        print("\n=== Testing sequential engine usage ===")

        # Check if both engines are available
        try:
            podman_check = subprocess.run(
                ["podman", "--version"], capture_output=True, timeout=5
            )
            docker_check = subprocess.run(
                ["docker", "--version"], capture_output=True, timeout=5
            )

            if podman_check.returncode != 0 or docker_check.returncode != 0:
                pytest.skip("Both Podman and Docker required for this test")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pytest.skip("Both Podman and Docker required for this test")

        # Create test project
        create_dual_engine_test_project(test_dir)

        try:
            original_cwd = Path.cwd()
            os.chdir(test_dir)

            # Test Podman first
            print("Testing Podman...")
            self.run_cli_command(["start", "--quiet"], test_dir, timeout=180)
            podman_status = self.run_cli_command(["status"], test_dir)
            assert "✅" in podman_status.stdout, "Podman setup should work"

            # Clean project data from Podman test
            self.run_cli_command(["clean-data"], test_dir, timeout=90)

            # Stop Podman services before testing Docker
            self.run_cli_command(["stop"], test_dir, timeout=90)

            # Test Docker second
            print("Testing Docker...")
            self.run_cli_command(
                ["start", "--force-docker", "--quiet"], test_dir, timeout=180
            )
            docker_status = self.run_cli_command(["status", "--force-docker"], test_dir)
            assert "✅" in docker_status.stdout, "Docker setup should work"

            # Clean project data from Docker test
            self.run_cli_command(["clean-data", "--force-docker"], test_dir, timeout=90)

        finally:
            try:
                os.chdir(original_cwd)
                # Clean up
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=test_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                pass
