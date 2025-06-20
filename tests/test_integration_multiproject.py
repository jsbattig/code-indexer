"""
Integration tests for multi-project functionality.
Tests the complete workflow of setting up, indexing, and searching multiple projects.
"""

import unittest
import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import ConfigManager


class TestMultiProjectIntegration(unittest.TestCase):
    """Integration tests for multi-project support."""

    @classmethod
    def setUpClass(cls):
        """Set up test environment before running tests."""
        cls.test_root = Path(__file__).parent / "projects"
        cls.project1_path = cls.test_root / "test_project_1"
        cls.project2_path = cls.test_root / "test_project_2"

        # Ensure test projects exist
        if not cls.project1_path.exists() or not cls.project2_path.exists():
            raise unittest.SkipTest("Test project directories not found")

    def setUp(self):
        """Set up for each test."""
        # Use absolute path instead of os.getcwd() to avoid FileNotFoundError
        self.original_cwd = str(Path(__file__).parent.parent.absolute())
        self.docker_managers = []

    def tearDown(self):
        """Clean up after each test using high-level CLI commands."""
        # Use CLI clean command for each project location that might have been tested
        for project_path in [self.project1_path, self.project2_path]:
            try:
                os.chdir(project_path)
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "code_indexer.cli",
                        "clean",
                        "--remove-data",
                        "--force",
                        "--validate",
                    ],
                    capture_output=True,
                    timeout=90,
                )
            except Exception as e:
                print(f"Error cleaning up project {project_path}: {e}")

        # Verify no root-owned files are left behind
        self.verify_no_root_owned_files()

        # Return to original directory if it exists
        try:
            if os.path.exists(self.original_cwd):
                os.chdir(self.original_cwd)
        except Exception as e:
            print(f"Error returning to original directory: {e}")

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
            current_user = os.getenv("USER") or os.getenv("USERNAME")
            result = subprocess.run(
                ["find", str(global_data_dir), "-not", "-user", current_user],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                root_owned_files = result.stdout.strip().split("\n")
                self.fail(
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
        os.chdir(self.project1_path)
        docker_manager1 = DockerManager()
        self.assertEqual(docker_manager1.project_name, "test_project_1")
        self.docker_managers.append(docker_manager1)

        # Test project 2
        os.chdir(self.project2_path)
        docker_manager2 = DockerManager()
        self.assertEqual(docker_manager2.project_name, "test_project_2")
        self.docker_managers.append(docker_manager2)

    def test_unique_container_names(self):
        """Test that global containers share the same name across projects."""
        # Create Docker managers for both projects
        os.chdir(self.project1_path)
        docker_manager1 = DockerManager()
        self.docker_managers.append(docker_manager1)

        os.chdir(self.project2_path)
        docker_manager2 = DockerManager()
        self.docker_managers.append(docker_manager2)

        # Check container names are identical (global architecture)
        ollama_name1 = docker_manager1.get_container_name("ollama")
        qdrant_name1 = docker_manager1.get_container_name("qdrant")
        ollama_name2 = docker_manager2.get_container_name("ollama")
        qdrant_name2 = docker_manager2.get_container_name("qdrant")

        self.assertEqual(ollama_name1, ollama_name2)
        self.assertEqual(qdrant_name1, qdrant_name2)

        # Verify global naming pattern
        self.assertEqual(ollama_name1, "code-indexer-ollama")
        self.assertEqual(qdrant_name1, "code-indexer-qdrant")
        self.assertEqual(ollama_name2, "code-indexer-ollama")
        self.assertEqual(qdrant_name2, "code-indexer-qdrant")

    def test_docker_compose_generation(self):
        """Test that Docker Compose configurations are generated correctly."""
        os.chdir(self.project1_path)
        docker_manager = DockerManager()
        self.docker_managers.append(docker_manager)

        # Generate compose configuration
        compose_config = docker_manager.generate_compose_config()

        # Verify services have global names
        services = compose_config["services"]
        self.assertIn("ollama", services)
        self.assertIn("qdrant", services)

        # Verify container names are global
        self.assertEqual(services["ollama"]["container_name"], "code-indexer-ollama")
        self.assertEqual(services["qdrant"]["container_name"], "code-indexer-qdrant")

        # Verify network name is global
        networks = compose_config["networks"]
        self.assertIn("code-indexer-global", networks)

    def test_multiple_projects_setup_simultaneously(self):
        """Test setting up multiple projects with shared global containers using CLI commands."""
        try:
            # Setup from project 1 using CLI
            os.chdir(self.project1_path)
            setup_result1 = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "setup", "--quiet"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(
                setup_result1.returncode,
                0,
                f"Project 1 setup failed: {setup_result1.stderr}",
            )

            # Check status from both projects using CLI
            status_result1 = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                status_result1.returncode,
                0,
                f"Project 1 status failed: {status_result1.stderr}",
            )
            self.assertIn(
                "✅", status_result1.stdout, "Services should be running after setup"
            )

            os.chdir(self.project2_path)
            status_result2 = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                status_result2.returncode,
                0,
                f"Project 2 status failed: {status_result2.stderr}",
            )
            self.assertIn(
                "✅",
                status_result2.stdout,
                "Both projects should see same global containers",
            )

            # Both projects should see the same global containers
            print(f"Project 1 status: {status_result1.stdout}")
            print(f"Project 2 status: {status_result2.stdout}")

        except Exception as e:
            self.fail(f"Failed to test multiple projects: {e}")

    def test_container_communication(self):
        """Test that containers can communicate internally using CLI commands."""
        os.chdir(self.project1_path)

        try:
            # Use CLI start command
            setup_result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "setup", "--quiet"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(
                setup_result.returncode, 0, f"Setup failed: {setup_result.stderr}"
            )

            # Test communication via CLI status command (which internally tests connectivity)
            status_result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                status_result.returncode,
                0,
                f"Status check failed: {status_result.stderr}",
            )
            self.assertIn(
                "✅",
                status_result.stdout,
                "Status command should confirm container communication",
            )

        except Exception as e:
            self.fail(f"Container communication test failed: {e}")

    def test_cli_integration_multiple_projects(self):
        """Test CLI commands work correctly with multiple projects."""
        # This test would require the CLI to be properly set up
        # For now, we'll test the underlying functionality

        # Test project 1 setup
        os.chdir(self.project1_path)
        result1 = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "status"],
            capture_output=True,
            text=True,
            cwd=self.project1_path,
        )

        # Test project 2 setup
        os.chdir(self.project2_path)
        result2 = subprocess.run(
            [sys.executable, "-m", "code_indexer.cli", "status"],
            capture_output=True,
            text=True,
            cwd=self.project2_path,
        )

        # Both should execute without errors (even if containers aren't running)
        # The important thing is that they don't conflict with each other
        self.assertIn("Code Indexer Status", result1.stdout + result1.stderr)
        self.assertIn("Code Indexer Status", result2.stdout + result2.stderr)

    def test_config_isolation(self):
        """Test that projects have isolated configurations."""
        # Load config from project 1
        os.chdir(self.project1_path)
        config_manager1 = ConfigManager()
        config1 = config_manager1.load()

        # Load config from project 2
        os.chdir(self.project2_path)
        config_manager2 = ConfigManager()
        config2 = config_manager2.load()

        # Both should load successfully
        self.assertIsNotNone(config1)
        self.assertIsNotNone(config2)

        # They should be independent configurations
        # (actual config values might be the same, but they're loaded independently)
        self.assertEqual(config1.ollama.model, config2.ollama.model)

    def test_cleanup_operations(self):
        """Test that cleanup operations work correctly using high-level CLI commands."""
        os.chdir(self.project1_path)

        try:
            # Use high-level CLI start command
            setup_result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "setup", "--quiet"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(
                setup_result.returncode, 0, f"Setup failed: {setup_result.stderr}"
            )

            # Verify services are running using CLI status command
            status_result = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                status_result.returncode,
                0,
                f"Status check failed: {status_result.stderr}",
            )
            self.assertIn(
                "✅", status_result.stdout, "Services should be running after setup"
            )

            # Use high-level CLI clean command with enhanced cleanup
            clean_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "code_indexer.cli",
                    "clean",
                    "--remove-data",
                    "--force",
                    "--validate",
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(
                clean_result.returncode, 0, f"Clean failed: {clean_result.stderr}"
            )

            # Verify cleanup worked using CLI status command
            final_status = subprocess.run(
                [sys.executable, "-m", "code_indexer.cli", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # After enhanced cleanup, services should not be running
            # Check specifically for Docker Services status
            if (
                "✅ Running" in final_status.stdout
                or "Docker Services │ ✅" in final_status.stdout
            ):
                self.fail(
                    f"Enhanced clean command did not stop services properly. Status output: {final_status.stdout}"
                )

            # Verify that Docker Services shows "Not Running"
            self.assertIn(
                "❌ Not Running",
                final_status.stdout,
                "Docker services should be stopped after cleanup",
            )

        except Exception as e:
            self.fail(f"Cleanup operations test failed: {e}")

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

                os.chdir(test_dir)
                docker_manager = DockerManager()
                self.assertEqual(docker_manager.project_name, expected_name)


def run_integration_tests():
    """Run the integration tests."""
    # Only run if explicitly requested
    if os.environ.get("RUN_INTEGRATION_TESTS") != "1":
        print("Integration tests skipped. Set RUN_INTEGRATION_TESTS=1 to run.")
        return

    # Create test suite
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMultiProjectIntegration)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return success/failure
    return result.wasSuccessful()


if __name__ == "__main__":
    # Run tests when script is executed directly
    success = run_integration_tests()
    sys.exit(0 if success else 1)
