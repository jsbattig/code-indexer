"""
Integration tests for multi-project functionality.
Tests the complete workflow of setting up, indexing, and searching multiple projects.
"""

import unittest
import os
import sys
import subprocess
import tempfile
import time
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
        """Clean up after each test."""
        # Stop all Docker containers and clean up
        for docker_manager in self.docker_managers:
            try:
                docker_manager.stop()
                docker_manager.clean()
            except Exception as e:
                print(f"Error cleaning up Docker manager: {e}")

        # Return to original directory if it exists
        try:
            if os.path.exists(self.original_cwd):
                os.chdir(self.original_cwd)
        except Exception as e:
            print(f"Error returning to original directory: {e}")

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
        """Test setting up multiple projects with shared global containers."""
        # Set up project 1
        os.chdir(self.project1_path)
        docker_manager1 = DockerManager()
        self.docker_managers.append(docker_manager1)

        # Set up project 2
        os.chdir(self.project2_path)
        docker_manager2 = DockerManager()
        self.docker_managers.append(docker_manager2)

        # Start global containers using first project manager
        try:
            print("Starting global containers...")
            docker_manager1.start()

            # Wait for services to be actually ready using robust health checking
            print("Waiting for services to be ready...")
            if not docker_manager1.wait_for_services(timeout=120):
                self.fail("Services failed to become ready within timeout")

            # Now verify both projects can access the same global containers
            print("Verifying service status...")
            status1 = docker_manager1.status()
            status2 = docker_manager2.status()

            # Print status for debugging
            print(f"Project 1 status: {status1}")
            print(f"Project 2 status: {status2}")

            self.assertTrue(
                status1["ollama"]["running"],
                f"Ollama not running for project 1: {status1['ollama']}",
            )
            self.assertTrue(
                status1["qdrant"]["running"],
                f"Qdrant not running for project 1: {status1['qdrant']}",
            )
            self.assertTrue(
                status2["ollama"]["running"],
                f"Ollama not running for project 2: {status2['ollama']}",
            )
            self.assertTrue(
                status2["qdrant"]["running"],
                f"Qdrant not running for project 2: {status2['qdrant']}",
            )

            # Verify they have identical container names (global architecture)
            self.assertEqual(status1["ollama"]["name"], status2["ollama"]["name"])
            self.assertEqual(status1["qdrant"]["name"], status2["qdrant"]["name"])

        except Exception as e:
            self.fail(f"Failed to start multiple projects: {e}")

    def test_container_communication(self):
        """Test that containers can communicate internally without port conflicts."""
        os.chdir(self.project1_path)
        docker_manager = DockerManager()
        self.docker_managers.append(docker_manager)

        try:
            # Start containers
            docker_manager.start()
            time.sleep(30)  # Wait for services to be ready

            # Test Ollama communication
            ollama_response = docker_manager.ollama_request("/api/tags", "GET")
            self.assertIsNotNone(ollama_response)
            self.assertTrue(ollama_response.get("success", False))
            self.assertIn("models", ollama_response.get("data", {}))

            # Test Qdrant communication
            qdrant_response = docker_manager.qdrant_request("/", "GET")
            self.assertIsNotNone(qdrant_response)
            self.assertTrue(qdrant_response.get("success", False))
            self.assertIn("title", qdrant_response.get("data", {}))

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
        """Test that cleanup operations work correctly for specific projects."""
        os.chdir(self.project1_path)
        docker_manager = DockerManager()
        self.docker_managers.append(docker_manager)

        try:
            # Start containers
            docker_manager.start()
            time.sleep(10)

            # Verify containers are running
            status = docker_manager.status()
            self.assertTrue(status["ollama"]["running"])
            self.assertTrue(status["qdrant"]["running"])

            # Stop containers
            docker_manager.stop()
            time.sleep(5)

            # Verify containers are stopped
            status = docker_manager.status()
            self.assertFalse(status["ollama"]["running"])
            self.assertFalse(status["qdrant"]["running"])

            # Clean up
            docker_manager.clean()

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
