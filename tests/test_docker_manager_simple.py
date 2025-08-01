"""
Simplified unit tests for DockerManager class.
Tests only the methods that actually exist in the implementation.
"""

from .conftest import local_temporary_directory

import unittest
import os
import sys
from pathlib import Path

# Add the src directory to the path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from code_indexer.services.docker_manager import DockerManager


class TestDockerManager(unittest.TestCase):
    """Unit tests for DockerManager class."""

    def setUp(self):
        """Set up for each test."""
        # Use absolute path instead of os.getcwd() to avoid FileNotFoundError
        self.original_cwd = str(Path(__file__).parent.parent.absolute())

    def tearDown(self):
        """Clean up after each test."""
        # Return to original directory if it exists
        try:
            if os.path.exists(self.original_cwd):
                os.chdir(self.original_cwd)
        except Exception as e:
            print(f"Error returning to original directory: {e}")

    def test_project_name_detection_from_folder(self):
        """Test project name detection from current folder name."""
        test_cases = [
            (
                "simple-project",
                "simple_project",
            ),  # Hyphens become underscores for qdrant
            ("MyProject", "myproject"),
            ("test_project", "test_project"),  # Underscores preserved
            ("Test Project", "test_project"),  # Spaces become underscores
            ("project@123", "project_123"),  # Special chars become underscores
            ("project.name", "project_name"),  # Dots become underscores
            ("PROJECT", "project"),
            ("a-b-c", "a_b_c"),  # Hyphens become underscores
        ]

        for folder_name, expected in test_cases:
            with local_temporary_directory() as temp_dir:
                test_dir = Path(temp_dir) / folder_name
                test_dir.mkdir()

                os.chdir(test_dir)
                # Test automatic project name detection (no explicit project_name)
                docker_manager = DockerManager()

                self.assertEqual(
                    docker_manager.project_name,
                    expected,
                    f"Failed for folder '{folder_name}'",
                )

    def test_project_name_sanitization(self):
        """Test project name sanitization for Docker compatibility."""
        docker_manager = DockerManager(project_name="test_shared")

        test_cases = [
            ("Test_Project", "test_project"),  # Underscores preserved for qdrant
            ("TEST-PROJECT", "test_project"),  # Hyphens become underscores
            (
                "project@special#chars",
                "project_special_chars",
            ),  # Special chars become underscores
            ("project with spaces", "project_with_spaces"),  # Spaces become underscores
            ("project...dots", "project___dots"),  # Dots become underscores
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

    def test_explicit_project_name(self):
        """Test providing explicit project name."""
        docker_manager = DockerManager(project_name="custom-project")

        self.assertEqual(docker_manager.project_name, "custom-project")

    def test_compose_file_path(self):
        """Test that compose file path is set correctly."""
        docker_manager = DockerManager(
            project_name="test_shared", project_config_dir=Path(".code-indexer")
        )

        # The compose file should be in the project's .code-indexer directory
        expected_path = Path(".code-indexer") / "docker-compose.yml"
        self.assertEqual(docker_manager.compose_file, expected_path)

    def test_docker_availability_check(self):
        """Test Docker availability checking method exists."""
        docker_manager = DockerManager(project_name="test_shared")

        # Should not raise an exception
        result = docker_manager.is_docker_available()
        self.assertIsInstance(result, bool)

    def test_compose_availability_check(self):
        """Test Docker Compose availability checking method exists."""
        docker_manager = DockerManager(project_name="test_shared")

        # Should not raise an exception
        result = docker_manager.is_compose_available()
        self.assertIsInstance(result, bool)

    def test_get_compose_command(self):
        """Test get compose command method exists."""
        docker_manager = DockerManager(project_name="test_shared")

        # Should not raise an exception and return a list
        result = docker_manager.get_compose_command()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_error_handling_invalid_project_name(self):
        """Test handling of edge cases in project name detection."""
        docker_manager = DockerManager(project_name="test_shared")

        # Test with very long project name
        long_name = "a" * 100
        sanitized = docker_manager._sanitize_project_name(long_name)

        # Docker container names have limits, should be truncated or handled
        self.assertLessEqual(len(sanitized), 63)  # Docker name limit

        # Test with only special characters
        special_only = "@#$%^&*()"
        sanitized_special = docker_manager._sanitize_project_name(special_only)
        self.assertTrue(len(sanitized_special) > 0)  # Should not be empty

        # Test with empty string
        empty_sanitized = docker_manager._sanitize_project_name("")
        self.assertEqual(empty_sanitized, "default")


class TestDockerManagerConfig(unittest.TestCase):
    """Test DockerManager configuration loading and handling."""

    def test_config_integration(self):
        """Test that DockerManager integrates properly with config system."""
        # This test ensures DockerManager can work without config files
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)

            # Should not fail even without config files
            docker_manager = DockerManager(project_name="test_shared")
            self.assertIsNotNone(docker_manager.project_name)


if __name__ == "__main__":
    unittest.main()
