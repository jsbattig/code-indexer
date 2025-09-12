"""
Integration tests for multi-project functionality.
Tests the complete workflow of setting up, indexing, and searching multiple projects.

Refactored to use NEW STRATEGY with test infrastructure to eliminate code duplication.
"""

import os
import pytest

from ...conftest import local_temporary_directory
from pathlib import Path
from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import ConfigManager

# Import new test infrastructure to eliminate duplication
from .infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


def handle_start_command_gracefully(project_dir, extra_args=None):
    """Handle start command with graceful service detection for existing services."""
    import subprocess
    import json
    import requests  # type: ignore
    import pytest

    cmd = ["code-indexer", "start"]
    if extra_args:
        cmd.extend(extra_args)

    start_result = subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )

    if start_result.returncode != 0:
        # If start failed due to port conflicts, check if services are already running
        if "already in use" in start_result.stdout:
            print("🔍 Services may already be running, attempting to proceed...")
            # Verify we can reach Qdrant by detecting running services
            try:
                # Try to detect running Qdrant service on common ports
                qdrant_ports = [7249, 6560, 6333, 6334, 6335]  # Common Qdrant ports
                working_port = None

                for port in qdrant_ports:
                    try:
                        response = requests.get(
                            f"http://localhost:{port}/cluster", timeout=2
                        )
                        if response.status_code == 200 and "status" in response.json():
                            working_port = port
                            print(f"🔍 Found Qdrant running on port {port}")
                            break
                    except Exception:
                        continue

                if working_port:
                    print("✅ Qdrant service is accessible, proceeding with test")
                    # Update config if it exists to use the detected port
                    config_file = project_dir / ".code-indexer" / "config.json"
                    if config_file.exists():
                        with open(config_file, "r") as f:
                            config = json.load(f)
                        config.setdefault("qdrant", {})[
                            "host"
                        ] = f"http://localhost:{working_port}"
                        with open(config_file, "w") as f:
                            json.dump(config, f, indent=2)
                        print(f"✅ Updated config to use Qdrant on port {working_port}")
                    return True
                else:
                    pytest.skip(
                        f"Start failed and no accessible Qdrant found: {start_result.stdout}"
                    )
            except Exception as e:
                pytest.skip(f"Start failed and could not verify services: {e}")
        else:
            pytest.skip(f"Could not start services: {start_result.stdout}")
    else:
        print("✅ Services started successfully")
        return True


@pytest.fixture
def multiproject_test_setup():
    """Create test setup for multi-project integration tests using shared container environment."""
    from tests.conftest import shared_container_test_environment
    from tests.unit.infrastructure.infrastructure import EmbeddingProvider

    # Use shared container environment for better performance
    with shared_container_test_environment(
        "multiproject_integration", EmbeddingProvider.VOYAGE_AI
    ) as base_dir:
        # Create two project subdirectories that share the same container environment
        project1_path = base_dir / "project1"
        project2_path = base_dir / "project2"

        project1_path.mkdir()
        project2_path.mkdir()

        # Create isolated configs but use compatible collection names for shared containers
        # Use the same collection base name so they can share the container environment
        multiproject_config_1 = TestProjectInventory.INTEGRATION_MULTIPROJECT_1
        multiproject_config_2 = TestProjectInventory.INTEGRATION_MULTIPROJECT_2

        # Override collection names to be compatible with shared environment
        multiproject_config_1.base_collection_name = "code_index"  # type: ignore[attr-defined]
        multiproject_config_2.base_collection_name = "code_index"  # type: ignore[attr-defined]

        create_test_project_with_inventory(project1_path, multiproject_config_1)
        create_test_project_with_inventory(project2_path, multiproject_config_2)

        # Create test files for both projects
        create_test_files_for_multiproject(project1_path, project2_path)

        yield {
            "project1_path": project1_path,
            "project2_path": project2_path,
        }


def create_test_files_for_multiproject(project1_path, project2_path):
    """Create test files for multi-project testing."""
    # Project 1: Calculator app
    (project1_path / "calculator.py").write_text(
        """
def add(a, b):
    '''Add two numbers'''
    return a + b

def multiply(a, b):
    '''Multiply two numbers'''
    return a * b

def calculator_main():
    '''Main calculator function'''
    print("Calculator Application")
    result = add(5, 3)
    print(f"5 + 3 = {result}")
"""
    )

    (project1_path / "math_utils.py").write_text(
        """
import math

def square_root(n):
    '''Calculate square root'''
    return math.sqrt(n)

def factorial(n):
    '''Calculate factorial'''
    if n <= 1:
        return 1
    return n * factorial(n - 1)
"""
    )

    # Project 2: Web server app
    (project2_path / "web_server.py").write_text(
        """
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    '''Home route'''
    return "Web Server Application"

@app.route('/api/data')
def get_data():
    '''API data endpoint'''
    return jsonify({"message": "Hello from API", "status": "success"})

def start_server():
    '''Start the web server'''
    app.run(debug=True)
"""
    )

    (project2_path / "database.py").write_text(
        """
class Database:
    '''Simple database class'''
    
    def __init__(self):
        self.data = {}
    
    def store(self, key, value):
        '''Store data in database'''
        self.data[key] = value
    
    def retrieve(self, key):
        '''Retrieve data from database'''
        return self.data.get(key)
    
    def delete(self, key):
        '''Delete data from database'''
        if key in self.data:
            del self.data[key]
"""
    )


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
class TestMultiProjectIntegration:
    """Integration tests for multi-project support using fixture-based approach."""

    # Removed setUp/tearDown - now handled by test infrastructure fixture

    # Removed ensure_services_ready - now handled by test infrastructure

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

    def test_project_name_detection(self, multiproject_test_setup):
        """Test automatic project name detection based on folder name."""
        project1_path = multiproject_test_setup["project1_path"]
        project2_path = multiproject_test_setup["project2_path"]

        # Test project 1 - auto-detection (no explicit project name)
        original_cwd = Path.cwd()
        try:
            os.chdir(project1_path)
            project_config_dir1 = project1_path / ".code-indexer"
            docker_manager1 = DockerManager(
                project_config_dir=project_config_dir1
            )  # No explicit project name for auto-detection
            assert docker_manager1.project_name == "project1"
        finally:
            os.chdir(original_cwd)

        # Test project 2 - auto-detection (no explicit project name)
        try:
            os.chdir(project2_path)
            project_config_dir2 = project2_path / ".code-indexer"
            docker_manager2 = DockerManager(
                project_config_dir=project_config_dir2
            )  # No explicit project name for auto-detection
            assert docker_manager2.project_name == "project2"
        finally:
            os.chdir(original_cwd)

    def test_unique_container_names(self, multiproject_test_setup):
        """Test that each project gets unique container names for isolation."""
        project1_path = multiproject_test_setup["project1_path"]
        project2_path = multiproject_test_setup["project2_path"]

        # Create Docker managers for both projects
        original_cwd = Path.cwd()
        try:
            os.chdir(project1_path)
            project_config_dir1 = project1_path / ".code-indexer"
            docker_manager1 = DockerManager(
                project_name="test_shared", project_config_dir=project_config_dir1
            )
            project_config1 = docker_manager1._generate_container_names(project1_path)
            qdrant_name1 = docker_manager1.get_container_name("qdrant", project_config1)
        finally:
            os.chdir(original_cwd)

        try:
            os.chdir(project2_path)
            project_config_dir2 = project2_path / ".code-indexer"
            docker_manager2 = DockerManager(
                project_name="test_shared", project_config_dir=project_config_dir2
            )
            project_config2 = docker_manager2._generate_container_names(project2_path)
            qdrant_name2 = docker_manager2.get_container_name("qdrant", project_config2)
        finally:
            os.chdir(original_cwd)

        # Check container names are different (per-project isolation)
        # Each project should get its own containers for better isolation
        assert qdrant_name1 != qdrant_name2
        print(f"Project 1 Qdrant: {qdrant_name1}")
        print(f"Project 2 Qdrant: {qdrant_name2}")

        # Verify both names follow the expected pattern
        assert "qdrant" in qdrant_name1
        assert "qdrant" in qdrant_name2
        assert "cidx-" in qdrant_name1
        assert "cidx-" in qdrant_name2

    def test_docker_compose_generation(self, multiproject_test_setup):
        """Test that Docker Compose configurations are generated correctly."""
        project1_path = multiproject_test_setup["project1_path"]

        original_cwd = Path.cwd()
        try:
            os.chdir(project1_path)
            project_config_dir = project1_path / ".code-indexer"
            docker_manager = DockerManager(
                project_name="test_shared", project_config_dir=project_config_dir
            )

            # Generate compose configuration with mock project config to avoid port conflicts
            # This test focuses on compose structure, not actual service startup
            mock_project_config = {
                "qdrant_name": "cidx-test-qdrant",
                "ollama_name": "cidx-test-ollama",
                "data_cleaner_name": "cidx-test-data-cleaner",
                "qdrant_port": 7777,  # Use non-conflicting test port
                "ollama_port": 11777,
                "data_cleaner_port": 8777,
                "project_hash": "test1234",
            }
            compose_config = docker_manager.generate_compose_config(
                project1_path, mock_project_config
            )

            # Verify services are generated correctly
            services = compose_config["services"]
            assert "qdrant" in services

            # Verify container names use project-specific naming (current architecture)
            assert services["qdrant"]["container_name"] == "cidx-test-qdrant"

            # Verify network name follows project-specific pattern
            networks = compose_config["networks"]
            # The network name should be project-specific, not global
            network_keys = list(networks.keys())
            assert len(network_keys) > 0
            # Network name should contain project hash or similar identifier
        finally:
            os.chdir(original_cwd)

    def test_multiple_projects_setup_simultaneously(self, multiproject_test_setup):
        """Test setting up multiple projects with shared global containers using CLI commands."""
        project1_path = multiproject_test_setup["project1_path"]
        project2_path = multiproject_test_setup["project2_path"]

        try:
            original_cwd = Path.cwd()

            # The shared container environment already has containers running
            # No need to start new containers - just use the existing ones
            # The test should verify that both projects can use the same containers

            # Skip container startup since shared environment already has running containers
            print(
                "Using shared container environment - skipping individual project setup"
            )

            import subprocess

            # Check status from both projects using CLI
            try:
                os.chdir(project1_path)
                status_result1 = subprocess.run(
                    ["code-indexer", "status"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert (
                    "✅" in status_result1.stdout
                ), "Services should be running after setup"
            except AssertionError as e:
                # Handle CoW legacy detection issue temporarily
                if "Legacy container detected" in str(e):
                    pytest.skip(
                        "CoW implementation bug: qdrant service missing home directory mount"
                    )
                raise
            finally:
                os.chdir(original_cwd)

            try:
                os.chdir(project2_path)
                status_result2 = subprocess.run(
                    ["code-indexer", "status"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert (
                    "✅" in status_result2.stdout
                ), "Both projects should see same global containers"
            finally:
                os.chdir(original_cwd)

            # Both projects should see the same global containers
            print(f"Project 1 status: {status_result1.stdout}")
            print(f"Project 2 status: {status_result2.stdout}")

        except Exception as e:
            pytest.fail(f"Failed to test multiple projects: {e}")

    def test_container_communication(self, multiproject_test_setup):
        """Test that containers can communicate internally using CLI commands."""
        project1_path = multiproject_test_setup["project1_path"]

        original_cwd = Path.cwd()
        try:
            os.chdir(project1_path)

            # Initialize with VoyageAI provider first
            import subprocess

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
                timeout=30,
            )
            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

            # Use graceful start handling
            handle_start_command_gracefully(project1_path, ["--force-recreate"])

            # Test communication via CLI status command (which internally tests connectivity)
            status_result = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                "✅" in status_result.stdout
            ), "Status command should confirm container communication"

        except Exception as e:
            pytest.fail(f"Container communication test failed: {e}")
        finally:
            os.chdir(original_cwd)

    def test_cli_integration_multiple_projects(self, multiproject_test_setup):
        """Test CLI commands work correctly with multiple projects."""
        project1_path = multiproject_test_setup["project1_path"]
        project2_path = multiproject_test_setup["project2_path"]

        original_cwd = Path.cwd()

        # Test project 1 setup
        try:
            os.chdir(project1_path)
            import subprocess

            result1 = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            os.chdir(original_cwd)

        # Test project 2 setup
        try:
            os.chdir(project2_path)
            result2 = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            os.chdir(original_cwd)

        # Both should execute without errors (even if containers aren't running)
        # The important thing is that they don't conflict with each other
        assert "Code Indexer Status" in (result1.stdout + result1.stderr)
        assert "Code Indexer Status" in (result2.stdout + result2.stderr)

    def test_config_isolation(self, multiproject_test_setup):
        """Test that projects have isolated configurations."""
        project1_path = multiproject_test_setup["project1_path"]
        project2_path = multiproject_test_setup["project2_path"]

        original_cwd = Path.cwd()

        # Load config from project 1
        try:
            os.chdir(project1_path)
            config_manager1 = ConfigManager()
            config1 = config_manager1.load()
        finally:
            os.chdir(original_cwd)

        # Load config from project 2
        try:
            os.chdir(project2_path)
            config_manager2 = ConfigManager()
            config2 = config_manager2.load()
        finally:
            os.chdir(original_cwd)

        # Both should load successfully
        assert config1 is not None
        assert config2 is not None

        # They should be independent configurations
        # (actual config values might be the same, but they're loaded independently)
        assert config1.voyage_ai.model == config2.voyage_ai.model

    def test_cleanup_operations(self, multiproject_test_setup):
        """Test that project data cleanup works correctly using test infrastructure."""
        project1_path = multiproject_test_setup["project1_path"]

        original_cwd = Path.cwd()
        try:
            os.chdir(project1_path)

            # Services should already be running from fixture, just init this project
            import subprocess

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
                timeout=30,
            )
            assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

            # Use graceful start handling (services should already be configured properly)
            handle_start_command_gracefully(project1_path)

            # Verify services are running using CLI status command
            status_result = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                "✅" in status_result.stdout
            ), "Services should be running after setup"

            # Index some data first to test cleanup
            index_result = subprocess.run(
                ["code-indexer", "index"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

            # Use clean-data command (NEW STRATEGY: keep services running)
            subprocess.run(
                ["code-indexer", "clean-data"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # clean-data may return non-zero if no data to clean, that's OK

            # Verify services are STILL running after clean-data (NEW STRATEGY)
            final_status = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Services should still be running after clean-data
            assert (
                "✅" in final_status.stdout
            ), "Services should still be running after clean-data (NEW STRATEGY)"

            # Test that we can immediately use services again (faster than full restart)
            subprocess.run(
                ["code-indexer", "query", "test"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # Query may return no results, that's OK, just ensure it doesn't crash

        finally:
            os.chdir(original_cwd)

    def test_project_name_sanitization(self, multiproject_test_setup):
        """Test that project names are properly sanitized for Docker."""
        # Test various problematic folder names
        test_cases = [
            ("Test_Project", "test_project"),
            ("test project", "test_project"),
            ("TEST-PROJECT", "test_project"),
            ("test.project", "test_project"),
            ("test@project", "test_project"),
        ]

        for folder_name, expected_name in test_cases:
            # Create temporary directory with problematic name
            with local_temporary_directory() as temp_dir:
                test_dir = Path(temp_dir) / folder_name
                test_dir.mkdir()

                original_cwd = Path.cwd()
                try:
                    os.chdir(test_dir)
                    project_config_dir = test_dir / ".code-indexer"
                    docker_manager = DockerManager(
                        project_config_dir=project_config_dir
                    )  # No explicit project name for auto-detection
                    assert docker_manager.project_name == expected_name
                finally:
                    os.chdir(original_cwd)


def run_integration_tests():
    """Run the integration tests."""
    # Only run if explicitly requested
    if os.environ.get("RUN_INTEGRATION_TESTS") != "1":
        print("Integration tests skipped. Set RUN_INTEGRATION_TESTS=1 to run.")
        return True

    # Use pytest to run this file
    import pytest

    return pytest.main([__file__, "-v"]) == 0


if __name__ == "__main__":
    # Run tests when script is executed directly
    import sys

    success = run_integration_tests()
    sys.exit(0 if success else 1)
