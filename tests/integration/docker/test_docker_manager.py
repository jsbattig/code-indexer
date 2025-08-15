"""
Unit tests for DockerManager class.
Tests the core functionality without requiring actual Docker containers.
"""

from ...conftest import local_temporary_directory

import unittest
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
                docker_manager = (
                    DockerManager()
                )  # Don't set project_name to auto-detect from folder

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

    def test_container_name_generation(self):
        """Test container name generation with project names."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)
            docker_manager = DockerManager(project_name="test_shared")

            # Generate project config required for new API
            project_config = docker_manager._generate_container_names(test_dir)

            # Test service container names
            ollama_name = docker_manager.get_container_name("ollama", project_config)
            qdrant_name = docker_manager.get_container_name("qdrant", project_config)

            # Names should include project hash now
            self.assertTrue(ollama_name.startswith("cidx-"))
            self.assertTrue(ollama_name.endswith("-ollama"))
            self.assertTrue(qdrant_name.startswith("cidx-"))
            self.assertTrue(qdrant_name.endswith("-qdrant"))

    def test_explicit_project_name(self):
        """Test providing explicit project name."""
        docker_manager = DockerManager(project_name="custom-project")

        self.assertEqual(docker_manager.project_name, "custom-project")

        # Test container names (project-specific architecture)
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()
            project_config = docker_manager._generate_container_names(test_dir)

            ollama_name = docker_manager.get_container_name("ollama", project_config)
            self.assertTrue(ollama_name.startswith("cidx-"))
            self.assertTrue(ollama_name.endswith("-ollama"))

    def test_compose_config_generation(self):
        """Test Docker Compose configuration generation."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            os.chdir(test_dir)

            # Create config file for embedding provider
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_data = {
                "codebase_dir": str(test_dir),
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "test_collection",
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                    "num_parallel": 1,
                    "max_loaded_models": 1,
                    "max_queue": 512,
                },
                "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_data, f, indent=2)

            docker_manager = DockerManager(project_name="test_shared")

            # Generate project config with proper port allocation
            container_names = docker_manager._generate_container_names(test_dir)

            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }

            config = docker_manager.generate_compose_config(test_dir, project_config)

            # Check basic structure (version field is deprecated in Docker Compose v2+)
            self.assertIn("services", config)
            self.assertIn("networks", config)
            self.assertNotIn("version", config)  # Should not have version field

            # Check services
            services = config["services"]
            self.assertIn("ollama", services)
            self.assertIn("qdrant", services)

            # Check container names are project-specific
            ollama_container = services["ollama"]["container_name"]
            qdrant_container = services["qdrant"]["container_name"]
            self.assertTrue(ollama_container.startswith("cidx-"))
            self.assertTrue(ollama_container.endswith("-ollama"))
            self.assertTrue(qdrant_container.startswith("cidx-"))
            self.assertTrue(qdrant_container.endswith("-qdrant"))

            # Check network configuration is project-specific
            networks = config["networks"]
            # Should have project-specific network
            network_names = list(networks.keys())
            self.assertEqual(len(network_names), 1)
            network_name = network_names[0]
            self.assertTrue(network_name.startswith("cidx-"))
            self.assertTrue(network_name.endswith("-network"))

            # Check that services use the project network
            for service in services.values():
                self.assertIn("networks", service)
                self.assertIn(network_name, service["networks"])

    def test_health_check_configuration(self):
        """Test health check configuration in Docker Compose."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            # Create config file for embedding provider
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_data = {
                "codebase_dir": str(test_dir),
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "test_collection",
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                    "num_parallel": 1,
                    "max_loaded_models": 1,
                    "max_queue": 512,
                },
                "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_data, f, indent=2)

            os.chdir(test_dir)
            docker_manager = DockerManager(project_name="test_shared")
            container_names = docker_manager._generate_container_names(test_dir)
            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }
            config = docker_manager.generate_compose_config(test_dir, project_config)

        services = config["services"]

        # Check Ollama health check
        ollama_healthcheck = services["ollama"]["healthcheck"]
        self.assertIn("test", ollama_healthcheck)
        self.assertEqual(ollama_healthcheck["test"][0], "CMD")
        self.assertIn("curl", ollama_healthcheck["test"][1])

        # Check Qdrant health check
        qdrant_healthcheck = services["qdrant"]["healthcheck"]
        self.assertIn("test", qdrant_healthcheck)
        self.assertEqual(qdrant_healthcheck["test"][0], "CMD")
        self.assertIn("curl", qdrant_healthcheck["test"][1])

    def test_volume_configuration(self):
        """Test volume configuration for data persistence."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            # Create config file for embedding provider
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_data = {
                "codebase_dir": str(test_dir),
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "test_collection",
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                    "num_parallel": 1,
                    "max_loaded_models": 1,
                    "max_queue": 512,
                },
                "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_data, f, indent=2)

            os.chdir(test_dir)
            docker_manager = DockerManager(project_name="test_shared")
            container_names = docker_manager._generate_container_names(test_dir)
            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }
            config = docker_manager.generate_compose_config(test_dir, project_config)

        services = config["services"]

        # Check Ollama volumes
        ollama_volumes = services["ollama"]["volumes"]
        self.assertTrue(any("ollama" in vol for vol in ollama_volumes))

        # Check Qdrant volumes
        qdrant_volumes = services["qdrant"]["volumes"]
        self.assertTrue(any("qdrant" in vol for vol in qdrant_volumes))

    def test_build_configuration(self):
        """Test build configuration for custom Dockerfiles."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            # Create config file for embedding provider
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_data = {
                "codebase_dir": str(test_dir),
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "test_collection",
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                    "num_parallel": 1,
                    "max_loaded_models": 1,
                    "max_queue": 512,
                },
                "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_data, f, indent=2)

            os.chdir(test_dir)
            docker_manager = DockerManager(project_name="test_shared")
            container_names = docker_manager._generate_container_names(test_dir)
            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }
            config = docker_manager.generate_compose_config(test_dir, project_config)

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

        docker_manager = DockerManager(project_name="test_shared")

        # Test container communication command construction
        # This tests the internal command building without actual execution
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()
            project_config = docker_manager._generate_container_names(test_dir)
            container_name = docker_manager.get_container_name("ollama", project_config)
            self.assertTrue(container_name.startswith("cidx-"))
            self.assertTrue(container_name.endswith("-ollama"))

    def test_network_name_generation(self):
        """Test network name generation - now uses project-specific network."""
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()

            docker_manager = DockerManager(project_name="test_shared")
            container_names = docker_manager._generate_container_names(test_dir)
            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }
            config = docker_manager.generate_compose_config(test_dir, project_config)

            networks = config["networks"]
            network_names = list(networks.keys())
            self.assertEqual(len(network_names), 1)
            network_name = network_names[0]
            self.assertTrue(network_name.startswith("cidx-"))
            self.assertTrue(network_name.endswith("-network"))

            # Check that all services use the project network
            services = config["services"]
            for service in services.values():
                self.assertIn(network_name, service["networks"])

    def test_error_handling_invalid_project_name(self):
        """Test handling of edge cases in project name detection."""
        # Test with very long project name
        long_name = "a" * 100
        docker_manager = DockerManager(project_name="test_shared")
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

            # Create config file for embedding provider
            config_dir = test_dir / ".code-indexer"
            config_dir.mkdir(exist_ok=True)

            config_data = {
                "codebase_dir": str(test_dir),
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "test_collection",
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                    "num_parallel": 1,
                    "max_loaded_models": 1,
                    "max_queue": 512,
                },
                "exclude_patterns": ["*.git*", "__pycache__", "node_modules"],
            }

            import json

            with open(config_dir / "config.json", "w") as f:
                json.dump(config_data, f, indent=2)

            # Should not fail even without config files
            docker_manager = DockerManager(project_name="test_shared")
            self.assertIsNotNone(docker_manager.project_name)

            # Should be able to generate compose config with proper port allocation
            container_names = docker_manager._generate_container_names(test_dir)

            ports = docker_manager._allocate_free_ports()
            project_config = {
                **container_names,
                "qdrant_port": str(ports["qdrant_port"]),
                "ollama_port": str(ports["ollama_port"]),
                "data_cleaner_port": str(ports["data_cleaner_port"]),
            }
            config = docker_manager.generate_compose_config(test_dir, project_config)
            self.assertIsNotNone(config)


if __name__ == "__main__":
    unittest.main()
