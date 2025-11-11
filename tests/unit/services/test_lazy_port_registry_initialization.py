"""Test lazy port registry initialization for filesystem backend.

This test suite validates that when using filesystem backend:
1. No port registry code executes during initialization
2. DockerManager is only created when actually needed (Qdrant backend)
3. GlobalPortRegistry is only instantiated when containers are required
4. No /var/lib/code-indexer directory access occurs with filesystem backend

These tests ensure CIDX can run on any system without sudo setup or container
runtime when using --vector-store filesystem.
"""

from unittest.mock import Mock, patch
from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import Config, VectorStoreConfig


class TestDockerManagerOptionalPortRegistry:
    """Test DockerManager with optional port registry parameter."""

    @patch("code_indexer.services.docker_manager.GlobalPortRegistry")
    def test_init_without_port_registry_does_not_create_it(self, mock_registry_class):
        """DockerManager should NOT create GlobalPortRegistry when port_registry=None.

        This is the FIRST test - it validates the core requirement that DockerManager
        can be instantiated without triggering port registry initialization.
        This allows filesystem backend to avoid /var/lib/code-indexer access.
        """
        # WHEN: Creating DockerManager with port_registry=None
        manager = DockerManager(port_registry=None)

        # THEN: GlobalPortRegistry should NOT be instantiated in __init__
        mock_registry_class.assert_not_called()

    @patch("code_indexer.services.docker_manager.GlobalPortRegistry")
    def test_lazy_port_registry_property_creates_on_first_access(
        self, mock_registry_class
    ):
        """port_registry property should create GlobalPortRegistry lazily when not provided.

        This test validates that when port_registry is accessed (not during __init__),
        it gets created lazily only at that point.
        """
        # GIVEN: DockerManager created without port_registry
        mock_instance = Mock()
        mock_registry_class.return_value = mock_instance
        manager = DockerManager(port_registry=None)

        # Verify not created during __init__
        mock_registry_class.assert_not_called()

        # WHEN: Accessing port_registry property for the first time
        registry = manager.port_registry

        # THEN: GlobalPortRegistry should be created lazily
        mock_registry_class.assert_called_once()
        assert registry is mock_instance

    @patch("code_indexer.services.docker_manager.GlobalPortRegistry")
    def test_backward_compatibility_default_behavior(self, mock_registry_class):
        """DockerManager without port_registry parameter should work (backward compatibility).

        This ensures existing code that creates DockerManager() without parameters
        continues to work, creating port_registry lazily on first access.
        """
        # GIVEN: Existing code that doesn't pass port_registry
        mock_instance = Mock()
        mock_registry_class.return_value = mock_instance

        # WHEN: Creating DockerManager the old way (no port_registry parameter)
        manager = DockerManager()

        # THEN: Should not fail, and port_registry created lazily
        mock_registry_class.assert_not_called()  # Not during __init__

        # AND WHEN: Accessing port_registry
        registry = manager.port_registry

        # THEN: Should create it lazily
        mock_registry_class.assert_called_once()
        assert registry is mock_instance

    def test_port_registry_can_be_set_for_testing(self):
        """port_registry property should support assignment for test mocking.

        This ensures backward compatibility with existing tests that mock port_registry.
        """
        # GIVEN: DockerManager instance
        manager = DockerManager()

        # WHEN: Setting port_registry directly (common in tests)
        mock_registry = Mock()
        manager.port_registry = mock_registry

        # THEN: Should accept the assignment and return it
        assert manager.port_registry is mock_registry


class TestCLIBackendTypeChecking:
    """Test CLI commands only create DockerManager when backend requires it."""

    def test_needs_docker_manager_returns_false_for_filesystem(self, tmp_path):
        """_needs_docker_manager() should return False for filesystem backend."""
        # GIVEN: A config with filesystem backend
        from code_indexer.cli import _needs_docker_manager

        config = Config(
            codebase_dir=tmp_path, vector_store=VectorStoreConfig(provider="filesystem")
        )

        # WHEN: Checking if DockerManager is needed
        result = _needs_docker_manager(config)

        # THEN: Should return False
        assert result is False

    def test_needs_docker_manager_returns_true_for_qdrant(self, tmp_path):
        """_needs_docker_manager() should return True for qdrant backend."""
        # GIVEN: A config with qdrant backend
        from code_indexer.cli import _needs_docker_manager

        config = Config(
            codebase_dir=tmp_path, vector_store=VectorStoreConfig(provider="qdrant")
        )

        # WHEN: Checking if DockerManager is needed
        result = _needs_docker_manager(config)

        # THEN: Should return True
        assert result is True


class TestFilesystemBackendNoPortRegistryE2E:
    """E2E tests verifying filesystem backend never accesses port registry."""

    @patch("code_indexer.services.global_port_registry.GlobalPortRegistry")
    def test_filesystem_backend_never_touches_port_registry(
        self, mock_pr_class, tmp_path
    ):
        """Complete filesystem backend workflow should never access GlobalPortRegistry.

        This E2E test validates that using filesystem backend from config creation
        through initialization never triggers port registry code.
        """
        # GIVEN: A project using filesystem backend
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test-project"
        project_root.mkdir()

        # WHEN: Creating and using FilesystemBackend
        backend = FilesystemBackend(project_root)
        backend.initialize()
        status = backend.get_status()

        # THEN: GlobalPortRegistry should never be instantiated
        mock_pr_class.assert_not_called()
        assert status["provider"] == "filesystem"
