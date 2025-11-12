"""Unit tests verifying Qdrant backend still uses port registry when needed.

Ensures backward compatibility - Qdrant backend must continue to work
with port registry for existing projects.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from code_indexer.backends.qdrant_container_backend import QdrantContainerBackend
from code_indexer.services.docker_manager import DockerManager


class TestQdrantPortRegistryCompatibility(unittest.TestCase):
    """Test that Qdrant backend maintains port registry compatibility."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path("/tmp/test_qdrant_compatibility")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_qdrant_backend_requires_containers(self):
        """QdrantContainerBackend should indicate it requires containers."""
        backend = QdrantContainerBackend(project_root=self.temp_dir)

        # Get service info
        info = backend.get_service_info()

        # Should indicate containers are required
        self.assertTrue(info["requires_containers"])
        self.assertEqual(info["provider"], "qdrant")

    def test_docker_manager_accesses_port_registry_when_needed(self):
        """DockerManager should access port registry when container-related methods are called."""
        with patch(
            "code_indexer.services.docker_manager.GlobalPortRegistry"
        ) as mock_registry_class:
            mock_registry_instance = MagicMock()
            mock_registry_instance._calculate_project_hash.return_value = "test_hash"
            mock_registry_class.return_value = mock_registry_instance

            # Create DockerManager without initial port registry
            manager = DockerManager(
                project_name="test_project",
                force_docker=False,
                project_config_dir=self.temp_dir,
                port_registry=None,
            )

            # Port registry should not be created yet
            mock_registry_class.assert_not_called()

            # Call a method that needs port registry
            container_names = manager._generate_container_names(self.temp_dir)

            # Now port registry should have been accessed
            mock_registry_class.assert_called_once()
            self.assertEqual(container_names["project_hash"], "test_hash")


if __name__ == "__main__":
    unittest.main()
