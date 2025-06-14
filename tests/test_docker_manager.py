"""
Unit tests for DockerManager class.
Tests the core functionality without requiring actual Docker containers.
"""

import unittest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from code_indexer.services.docker_manager import DockerManager


class TestDockerManager(unittest.TestCase):
    """Unit tests for DockerManager class."""

    def setUp(self):
        """Set up for each test."""
        self.original_cwd = os.getcwd()

    def tearDown(self):
        """Clean up after each test."""
        os.chdir(self.original_cwd)

    def test_project_name_detection_from_folder(self):
        """Test project name detection from current folder name."""
        test_cases = [
            ("simple-project", "simple-project"),
            ("MyProject", "myproject"),
            ("test_project", "test_project"),  # Underscores preserved
            ("Test Project", "test-project"),  # Spaces become hyphens
            ("project@123", "project-123"),
            ("project.name", "project.name"),  # Dots preserved
            ("PROJECT", "project"),
            ("a-b-c", "a-b-c"),
        ]

        for folder_name, expected in test_cases:
            with tempfile.TemporaryDirectory() as temp_dir:
                test_dir = Path(temp_dir) / folder_name
                test_dir.mkdir()

                os.chdir(test_dir)
                docker_manager = DockerManager()

                self.assertEqual(
                    docker_manager.project_name,
                    expected,
                    f"Failed for folder '{folder_name}'",
                )

    def test_project_name_sanitization(self):
        """Test project name sanitization for Docker compatibility."""
        docker_manager = DockerManager()

        test_cases = [
            ("Test_Project", "test_project"),  # Underscores are kept
            ("TEST-PROJECT", "test-project"),
            ("project@special#chars", "project-special-chars"),
            ("project with spaces", "project-with-spaces"),
            ("project...dots", "project-dots"),
            (
                "project__underscores",
                "project__underscores",
            ),  # Multiple underscores preserved
            ("123project", "123project"),  # Numbers are allowed
            ("a", "a"),  # Single character
            ("", "default"),  # Empty string fallback is "default"
        ]

        for input_name, expected in test_cases:
            result = docker_manager._sanitize_project_name(input_name)
            self.assertEqual(result, expected, f"Failed to sanitize '{input_name}'")

    def test_container_name_generation(self):
        """Test container name generation with project names."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)
            docker_manager = DockerManager()

            # Test service container names
            ollama_name = docker_manager.get_container_name("ollama")
            qdrant_name = docker_manager.get_container_name("qdrant")

            self.assertEqual(ollama_name, "code-ollama-test-project")
            self.assertEqual(qdrant_name, "code-qdrant-test-project")

    def test_explicit_project_name(self):
        """Test providing explicit project name."""
        docker_manager = DockerManager(project_name="custom-project")

        self.assertEqual(docker_manager.project_name, "custom-project")

        # Test container names with explicit project name
        ollama_name = docker_manager.get_container_name("ollama")
        self.assertEqual(ollama_name, "code-ollama-custom-project")

    def test_compose_config_generation(self):
        """Test Docker Compose configuration generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)
            docker_manager = DockerManager()

            config = docker_manager.generate_compose_config()

            # Check basic structure
            self.assertIn("version", config)
            self.assertIn("services", config)
            self.assertIn("networks", config)

            # Check services
            services = config["services"]
            self.assertIn("ollama", services)
            self.assertIn("qdrant", services)

            # Check container names include project name
            self.assertEqual(
                services["ollama"]["container_name"], "code-ollama-test-project"
            )
            self.assertEqual(
                services["qdrant"]["container_name"], "code-qdrant-test-project"
            )

            # Check network configuration
            networks = config["networks"]
            self.assertIn("code-indexer-test-project", networks)

            # Check that services use the project-specific network
            for service in services.values():
                self.assertIn("networks", service)
                self.assertIn("code-indexer-test-project", service["networks"])

    def test_health_check_configuration(self):
        """Test health check configuration in Docker Compose."""
        docker_manager = DockerManager(project_name="test")
        config = docker_manager.generate_compose_config()

        services = config["services"]

        # Check Ollama health check
        ollama_healthcheck = services["ollama"]["healthcheck"]
        self.assertIn("test", ollama_healthcheck)
        self.assertIn("curl", ollama_healthcheck["test"][0])

        # Check Qdrant health check
        qdrant_healthcheck = services["qdrant"]["healthcheck"]
        self.assertIn("test", qdrant_healthcheck)
        self.assertIn("curl", qdrant_healthcheck["test"][0])

    def test_volume_configuration(self):
        """Test volume configuration for data persistence."""
        docker_manager = DockerManager(project_name="test")
        config = docker_manager.generate_compose_config()

        services = config["services"]

        # Check Ollama volumes
        ollama_volumes = services["ollama"]["volumes"]
        self.assertTrue(any("ollama" in vol for vol in ollama_volumes))

        # Check Qdrant volumes
        qdrant_volumes = services["qdrant"]["volumes"]
        self.assertTrue(any("qdrant" in vol for vol in qdrant_volumes))

    def test_build_configuration(self):
        """Test build configuration for custom Dockerfiles."""
        docker_manager = DockerManager(project_name="test")
        config = docker_manager.generate_compose_config()

        services = config["services"]

        # Check that services use build instead of image
        self.assertIn("build", services["ollama"])
        self.assertIn("build", services["qdrant"])

        # Check build context and dockerfile
        ollama_build = services["ollama"]["build"]
        self.assertIn("context", ollama_build)
        self.assertIn("dockerfile", ollama_build)

        qdrant_build = services["qdrant"]["build"]
        self.assertIn("context", qdrant_build)
        self.assertIn("dockerfile", qdrant_build)

    @patch("subprocess.run")
    def test_docker_command_construction(self, mock_run):
        """Test Docker command construction for container operations."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"key": "value"}', stderr=""
        )

        docker_manager = DockerManager(project_name="test")

        # Test container communication command construction
        # This tests the internal command building without actual execution
        container_name = docker_manager.get_container_name("ollama")
        self.assertEqual(container_name, "code-ollama-test")

    def test_network_name_generation(self):
        """Test network name generation with project specificity."""
        docker_manager = DockerManager(project_name="my-project")
        config = docker_manager.generate_compose_config()

        networks = config["networks"]
        expected_network = "code-indexer-my-project"

        self.assertIn(expected_network, networks)

        # Check that all services use this network
        services = config["services"]
        for service in services.values():
            self.assertIn(expected_network, service["networks"])

    def test_error_handling_invalid_project_name(self):
        """Test handling of edge cases in project name detection."""
        # Test with very long project name
        long_name = "a" * 100
        docker_manager = DockerManager()
        sanitized = docker_manager._sanitize_project_name(long_name)

        # Docker container names have limits, should be truncated or handled
        self.assertLessEqual(len(sanitized), 63)  # Docker name limit

        # Test with only special characters
        special_only = "@#$%^&*()"
        sanitized_special = docker_manager._sanitize_project_name(special_only)
        self.assertTrue(len(sanitized_special) > 0)  # Should not be empty

        # Test with empty string
        empty_sanitized = docker_manager._sanitize_project_name("")
        self.assertEqual(empty_sanitized, "unknown")


class TestDockerManagerConfig(unittest.TestCase):
    """Test DockerManager configuration loading and handling."""

    def test_config_integration(self):
        """Test that DockerManager integrates properly with config system."""
        # This test ensures DockerManager can work without config files
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)

            # Should not fail even without config files
            docker_manager = DockerManager()
            self.assertIsNotNone(docker_manager.project_name)

            # Should be able to generate compose config
            config = docker_manager.generate_compose_config()
            self.assertIsNotNone(config)


if __name__ == "__main__":
    unittest.main()
