"""
Integration tests for multi-project functionality.
Tests the complete workflow of setting up, indexing, and searching multiple projects.

Refactored to use NEW STRATEGY with test infrastructure to eliminate code duplication.
"""

import os
import pytest
import tempfile
from pathlib import Path
from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import ConfigManager

# Import new test infrastructure to eliminate duplication
from .test_infrastructure import (
    create_integration_test_setup,
    DirectoryManager,
    EmbeddingProvider,
)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestMultiProjectIntegration:
    """Integration tests for multi-project support using NEW STRATEGY."""

    @pytest.fixture(autouse=True)
    def setup_test_environment(self):
        """Set up test environment using test infrastructure to eliminate duplication."""
        # NEW STRATEGY: Use test infrastructure instead of duplicated service management
        self.service_manager, self.cli_helper = create_integration_test_setup(
            EmbeddingProvider.VOYAGE_AI
        )
        self.dir_manager = DirectoryManager()

        # Define project paths
        self.test_root = Path(__file__).parent / "projects"
        self.project1_path = self.test_root / "test_project_1"
        self.project2_path = self.test_root / "test_project_2"

        # Ensure test projects exist
        if not self.project1_path.exists() or not self.project2_path.exists():
            pytest.skip("Test project directories not found")

        # NEW STRATEGY: Ensure services ready once, reuse for all tests
        services_ready = self.service_manager.ensure_services_ready()
        if not services_ready:
            pytest.skip("Could not start required services for integration testing")

        yield

        # NEW STRATEGY: Only clean project data, keep services running
        for project_path in [self.project1_path, self.project2_path]:
            try:
                with self.dir_manager.safe_chdir(project_path):
                    self.cli_helper.run_cli_command(
                        ["clean-data"], expect_success=False
                    )
            except Exception:
                pass

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

    def test_project_name_detection(self):
        """Test automatic project name detection based on folder name."""
        # Test project 1
        with self.dir_manager.safe_chdir(self.project1_path):
            docker_manager1 = DockerManager()
            assert docker_manager1.project_name == "test_project_1"

        # Test project 2
        with self.dir_manager.safe_chdir(self.project2_path):
            docker_manager2 = DockerManager()
            assert docker_manager2.project_name == "test_project_2"

    def test_unique_container_names(self):
        """Test that global containers share the same name across projects."""
        # Create Docker managers for both projects
        with self.dir_manager.safe_chdir(self.project1_path):
            docker_manager1 = DockerManager()
            qdrant_name1 = docker_manager1.get_container_name("qdrant")

        with self.dir_manager.safe_chdir(self.project2_path):
            docker_manager2 = DockerManager()
            qdrant_name2 = docker_manager2.get_container_name("qdrant")

        # Check container names are identical (global architecture)
        # VoyageAI is cloud-based, only need Qdrant locally
        assert qdrant_name1 == qdrant_name2

        # Verify global naming pattern
        assert qdrant_name1 == "code-indexer-qdrant"
        assert qdrant_name2 == "code-indexer-qdrant"

    def test_docker_compose_generation(self):
        """Test that Docker Compose configurations are generated correctly."""
        with self.dir_manager.safe_chdir(self.project1_path):
            docker_manager = DockerManager()

            # Generate compose configuration
            compose_config = docker_manager.generate_compose_config()

            # Verify services have global names
            # VoyageAI is cloud-based, only need Qdrant locally
            services = compose_config["services"]
            assert "qdrant" in services

            # Verify container names are global
            assert services["qdrant"]["container_name"] == "code-indexer-qdrant"

            # Verify network name is global
            networks = compose_config["networks"]
            assert "code-indexer-global" in networks

    def test_multiple_projects_setup_simultaneously(self):
        """Test setting up multiple projects with shared global containers using CLI commands."""
        try:
            # Setup from project 1 using CLI
            with self.dir_manager.safe_chdir(self.project1_path):
                # Initialize with VoyageAI provider first
                self.cli_helper.run_cli_command(
                    ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
                )

                self.cli_helper.run_cli_command(["start", "--quiet"], timeout=180)

            # Check status from both projects using CLI
            with self.dir_manager.safe_chdir(self.project1_path):
                status_result1 = self.cli_helper.run_cli_command(["status"], timeout=30)
                assert (
                    "✅" in status_result1.stdout
                ), "Services should be running after setup"

            with self.dir_manager.safe_chdir(self.project2_path):
                status_result2 = self.cli_helper.run_cli_command(["status"], timeout=30)
                assert (
                    "✅" in status_result2.stdout
                ), "Both projects should see same global containers"

            # Both projects should see the same global containers
            print(f"Project 1 status: {status_result1.stdout}")
            print(f"Project 2 status: {status_result2.stdout}")

        except Exception as e:
            pytest.fail(f"Failed to test multiple projects: {e}")

    def test_container_communication(self):
        """Test that containers can communicate internally using CLI commands."""
        with self.dir_manager.safe_chdir(self.project1_path):
            try:
                # Initialize with VoyageAI provider first
                self.cli_helper.run_cli_command(
                    ["init", "--force", "--embedding-provider", "voyage-ai"], timeout=30
                )

                # Use CLI start command
                self.cli_helper.run_cli_command(["start", "--quiet"], timeout=180)

                # Test communication via CLI status command (which internally tests connectivity)
                status_result = self.cli_helper.run_cli_command(["status"], timeout=30)
                assert (
                    "✅" in status_result.stdout
                ), "Status command should confirm container communication"

            except Exception as e:
                pytest.fail(f"Container communication test failed: {e}")

    def test_cli_integration_multiple_projects(self):
        """Test CLI commands work correctly with multiple projects."""
        # Test project 1 setup
        with self.dir_manager.safe_chdir(self.project1_path):
            result1 = self.cli_helper.run_cli_command(["status"], expect_success=False)

        # Test project 2 setup
        with self.dir_manager.safe_chdir(self.project2_path):
            result2 = self.cli_helper.run_cli_command(["status"], expect_success=False)

        # Both should execute without errors (even if containers aren't running)
        # The important thing is that they don't conflict with each other
        assert "Code Indexer Status" in (result1.stdout + result1.stderr)
        assert "Code Indexer Status" in (result2.stdout + result2.stderr)

    def test_config_isolation(self):
        """Test that projects have isolated configurations."""
        # Load config from project 1
        with self.dir_manager.safe_chdir(self.project1_path):
            config_manager1 = ConfigManager()
            config1 = config_manager1.load()

        # Load config from project 2
        with self.dir_manager.safe_chdir(self.project2_path):
            config_manager2 = ConfigManager()
            config2 = config_manager2.load()

        # Both should load successfully
        assert config1 is not None
        assert config2 is not None

        # They should be independent configurations
        # (actual config values might be the same, but they're loaded independently)
        assert config1.voyage_ai.model == config2.voyage_ai.model

    def test_cleanup_operations(self):
        """Test that project data cleanup works correctly using test infrastructure."""
        with self.dir_manager.safe_chdir(self.project1_path):
            # Services should already be running from fixture, just init this project
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"]
            )

            # Ensure services are running (should be fast since setUp started them)
            self.cli_helper.run_cli_command(["start", "--quiet"], timeout=60)

            # Verify services are running using CLI status command
            status_result = self.cli_helper.run_cli_command(["status"], timeout=30)
            assert (
                "✅" in status_result.stdout
            ), "Services should be running after setup"

            # Index some data first to test cleanup
            self.cli_helper.run_cli_command(["index"], timeout=60)

            # Use clean-data command (NEW STRATEGY: keep services running)
            self.cli_helper.run_cli_command(["clean-data"], timeout=30)

            # Verify services are STILL running after clean-data (NEW STRATEGY)
            final_status = self.cli_helper.run_cli_command(["status"], timeout=30)
            # Services should still be running after clean-data
            assert (
                "✅" in final_status.stdout
            ), "Services should still be running after clean-data (NEW STRATEGY)"

            # Test that we can immediately use services again (faster than full restart)
            self.cli_helper.run_cli_command(["query", "test"], timeout=30)

    def test_project_name_sanitization(self):
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
            with tempfile.TemporaryDirectory() as temp_dir:
                test_dir = Path(temp_dir) / folder_name
                test_dir.mkdir()

                with self.dir_manager.safe_chdir(test_dir):
                    docker_manager = DockerManager()
                    assert docker_manager.project_name == expected_name


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
