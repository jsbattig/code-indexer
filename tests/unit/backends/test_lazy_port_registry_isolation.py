"""Unit tests for lazy port registry initialization.

Tests verify that:
1. FilesystemBackend never accesses GlobalPortRegistry
2. QdrantContainerBackend only accesses it when needed
3. DockerManager lazily initializes GlobalPortRegistry
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from code_indexer.backends.filesystem_backend import FilesystemBackend
from code_indexer.services.docker_manager import DockerManager


class TestLazyPortRegistryIsolation(unittest.TestCase):
    """Test that port registry is only accessed when needed."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path("/tmp/test_lazy_port_registry")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test environment."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_filesystem_backend_never_uses_port_registry(self):
        """FilesystemBackend should never access GlobalPortRegistry."""
        with patch(
            "code_indexer.services.docker_manager.GlobalPortRegistry"
        ) as mock_registry_class:
            # Make it fail if accessed
            mock_registry_class.side_effect = RuntimeError(
                "GlobalPortRegistry accessed in filesystem backend!"
            )

            # Create and use FilesystemBackend
            backend = FilesystemBackend(project_root=self.temp_dir)

            # Test all operations that should work without port registry
            backend.initialize()
            self.assertTrue(backend.start())
            self.assertTrue(backend.stop())
            status = backend.get_status()
            self.assertEqual(status["provider"], "filesystem")
            self.assertTrue(backend.health_check())
            info = backend.get_service_info()
            self.assertEqual(info["provider"], "filesystem")
            self.assertFalse(info["requires_containers"])

            # Verify port registry was never accessed
            mock_registry_class.assert_not_called()

    def test_docker_manager_lazy_initialization(self):
        """DockerManager should only create GlobalPortRegistry when accessed."""
        with patch(
            "code_indexer.services.docker_manager.GlobalPortRegistry"
        ) as mock_registry_class:
            # Mock the GlobalPortRegistry instance
            from unittest.mock import MagicMock
            mock_registry_instance = MagicMock()
            mock_registry_class.return_value = mock_registry_instance

            # Create DockerManager without port_registry
            manager = DockerManager(
                project_name="test_project",
                force_docker=False,
                project_config_dir=self.temp_dir,
                port_registry=None,  # Not provided initially
            )

            # Port registry should not be created yet
            mock_registry_class.assert_not_called()
            self.assertIsNone(manager._port_registry)

            # Access port_registry property - should trigger lazy init
            registry = manager.port_registry
            mock_registry_class.assert_called_once()
            self.assertEqual(registry, mock_registry_instance)
            self.assertEqual(manager._port_registry, mock_registry_instance)

            # Second access should reuse existing instance
            registry2 = manager.port_registry
            mock_registry_class.assert_called_once()  # Still only one call
            self.assertEqual(registry2, mock_registry_instance)


if __name__ == "__main__":
    unittest.main()