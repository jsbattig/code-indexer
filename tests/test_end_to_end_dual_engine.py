#!/usr/bin/env python3
"""
End-to-end tests using ONLY user-level CLI orchestration.
Tests the actual user experience by running the same commands users would run.

This test suite exposes application flaws by trusting CLI commands to work properly.
If tests fail, it indicates real issues in the application code that need fixing.
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestEndToEndDualEngine:
    """Test CLI commands with both Podman (default) and Docker (--force-docker)"""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test environment using only user-level commands"""
        # Create a temporary test project directory
        self.test_dir = Path(tempfile.mkdtemp(prefix="code_indexer_test_"))
        try:
            self.original_cwd = Path.cwd()
        except (FileNotFoundError, OSError):
            # If current directory doesn't exist, use the test file's parent directory
            self.original_cwd = Path(__file__).parent.absolute()

        # Create some test files in the project
        self.create_test_project()

        # Change to test directory
        os.chdir(self.test_dir)

        # NEW STRATEGY: Ensure services are running (comprehensive setup)
        self.ensure_services_ready()

        yield

        # NEW STRATEGY: Keep services running, just clean project data if needed
        try:
            os.chdir(self.test_dir)
            # Use clean-data to remove only project-specific data, keep services running
            subprocess.run(
                ["code-indexer", "clean-data"],
                capture_output=True,
                timeout=30,  # Much faster than full cleanup
            )
        except Exception:
            # Ignore cleanup errors - services will be reused by next test
            pass
        finally:
            # Return to original directory
            os.chdir(self.original_cwd)
            # Services stay running for next test (faster overall execution)

    def ensure_services_ready(self):
        """Ensure services are running using new strategy (keep services running)"""
        try:
            # Check if services are already running to avoid unnecessary startup time
            status_result = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            services_running = status_result.returncode == 0 and (
                "✅ Running" in status_result.stdout
                or "✅ Ready" in status_result.stdout
            )

            if not services_running:
                # Services not running, start them with VoyageAI for CI stability
                print("Starting services for test...")
                init_result = subprocess.run(
                    [
                        "code-indexer",
                        "init",
                        "--force",
                        "--embedding-provider",
                        "voyage-ai",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if init_result.returncode != 0:
                    print(f"Init failed: {init_result.stderr}")

                start_result = subprocess.run(
                    ["code-indexer", "start", "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if start_result.returncode != 0:
                    print(f"Start failed: {start_result.stderr}")
            else:
                # Services running, just ensure this project is properly initialized
                subprocess.run(
                    [
                        "code-indexer",
                        "init",
                        "--force",
                        "--embedding-provider",
                        "voyage-ai",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
        except Exception as e:
            print(f"Service setup error: {e}")
            # Don't fail the test, let it proceed and fail properly if needed

    def create_test_project(self):
        """Create a simple test project with some code files"""
        # Create a basic Python project structure
        (self.test_dir / "src").mkdir()

        # Create test Python files
        (self.test_dir / "src" / "main.py").write_text(
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

        (self.test_dir / "src" / "api.py").write_text(
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

        (self.test_dir / "tests").mkdir()
        (self.test_dir / "tests" / "test_auth.py").write_text(
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

    def run_cli_command(self, args, timeout=120, expect_success=True):
        """Run code-indexer CLI command using high-level application functions"""
        import sys

        cmd_str = " ".join(["code-indexer"] + args)
        print(f"Running: {cmd_str}")

        # Use subprocess to call the actual CLI command exactly as a user would
        result = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli"] + args,
            capture_output=True,
            text=True,
            cwd=self.test_dir,
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
    def test_full_user_workflow(self, force_docker):
        """Test complete user workflow: init → setup → index → query → clean"""
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing full user workflow with {engine_name} ===")

        # Step 1: User initializes project with VoyageAI for CI stability
        # Note: Using --force since setup may have already initialized
        self.run_cli_command(["init", "--force", "--embedding-provider", "voyage-ai"])

        # Verify expected outcome: config file exists
        config_file = self.test_dir / ".code-indexer" / "config.json"
        assert config_file.exists(), "init should create config file"

        # Step 2: User starts services
        setup_args = ["start", "--quiet"]
        if force_docker:
            setup_args.append("--force-docker")
        self.run_cli_command(setup_args, timeout=180)

        # Step 3: User indexes their code
        self.run_cli_command(["index"], timeout=120)

        # Step 4: User searches their code
        result = self.run_cli_command(["query", "authentication function"], timeout=60)
        assert (
            "authenticate_user" in result.stdout
        ), "Should find authentication function"

        result = self.run_cli_command(["query", "REST API endpoint"], timeout=60)
        assert "login_endpoint" in result.stdout, "Should find API endpoint"

        # Step 5: User checks system status
        status_args = ["status"]
        if force_docker:
            status_args.append("--force-docker")
        result = self.run_cli_command(status_args)
        assert "✅" in result.stdout, "Status should show healthy system"

        # Step 6: User cleans up their project data (keeping services for other projects)
        clean_args = ["clean-data"]
        if force_docker:
            clean_args.append("--force-docker")
        self.run_cli_command(clean_args, timeout=90)

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_clean_command_effectiveness(self, force_docker):
        """Test that clean command actually cleans up properly"""
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing clean command effectiveness with {engine_name} ===")

        # User starts services
        setup_args = ["start", "--quiet"]
        if force_docker:
            setup_args.append("--force-docker")
        self.run_cli_command(setup_args, timeout=180)

        # Verify services are running
        status_args = ["status"]
        if force_docker:
            status_args.append("--force-docker")
        result = self.run_cli_command(status_args)
        assert "✅" in result.stdout, "Services should be running after setup"

        # User cleans project data using clean-data command
        clean_args = ["clean-data"]
        if force_docker:
            clean_args.append("--force-docker")
        self.run_cli_command(clean_args, timeout=90)

        # Verify cleanup worked by checking status - services should remain running but data should be cleared
        result = self.run_cli_command(status_args)
        # After clean-data, services should still be running (containers preserved) but index should be cleared
        assert (
            "✅" in result.stdout
        ), "Services should still be running after clean-data"
        assert (
            "❌ Not Found" in result.stdout or "Not Found" in result.stdout
        ), f"Index should be cleared after clean-data: {result.stdout}"

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_service_engine_isolation(self, force_docker):
        """Test that different engines don't interfere with each other"""
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

        # User starts services with specific engine
        setup_args = ["start", "--quiet"]
        if force_docker:
            setup_args.append("--force-docker")
        self.run_cli_command(setup_args, timeout=180)

        # Check that services are working
        status_args = ["status"]
        if force_docker:
            status_args.append("--force-docker")
        result = self.run_cli_command(status_args)

        # Verify expected components are present
        assert "Qdrant" in result.stdout, "Status should show Qdrant"

        # Clean up project data after test to prevent state leakage
        clean_args = ["clean-data"]
        if force_docker:
            clean_args.append("--force-docker")
        self.run_cli_command(clean_args, timeout=90)

    @pytest.mark.parametrize("force_docker", [False, True])
    def test_performance_configuration(self, force_docker):
        """Test setup with custom performance settings"""
        engine_name = "Docker" if force_docker else "Podman"
        print(f"\n=== Testing performance configuration with {engine_name} ===")

        # Initialize with VoyageAI provider first
        self.run_cli_command(["init", "--force", "--embedding-provider", "voyage-ai"])

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

        self.run_cli_command(setup_args, timeout=180)

        # Verify setup succeeded with custom config
        status_args = ["status"]
        if force_docker:
            status_args.append("--force-docker")
        result = self.run_cli_command(status_args)

        assert "✅" in result.stdout, "Setup with custom performance config should work"
        assert "Ready" in result.stdout, "Services should be ready"

        # Clean up project data after test to prevent state leakage
        clean_args = ["clean-data"]
        if force_docker:
            clean_args.append("--force-docker")
        self.run_cli_command(clean_args, timeout=90)

    def test_sequential_engine_usage(self):
        """Test that both engines can be used sequentially without conflicts"""
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

        # Test Podman first
        print("Testing Podman...")
        self.run_cli_command(["start", "--quiet"], timeout=180)
        podman_status = self.run_cli_command(["status"])
        assert "✅" in podman_status.stdout, "Podman setup should work"

        # Clean project data from Podman test
        self.run_cli_command(["clean-data"], timeout=90)

        # Test Docker second
        print("Testing Docker...")
        self.run_cli_command(["start", "--force-docker", "--quiet"], timeout=180)
        docker_status = self.run_cli_command(["status", "--force-docker"])
        assert "✅" in docker_status.stdout, "Docker setup should work"

        # Clean project data from Docker test
        self.run_cli_command(["clean-data", "--force-docker"], timeout=90)
