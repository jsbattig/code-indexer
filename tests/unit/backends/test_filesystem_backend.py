"""Unit tests for FilesystemBackend vector storage backend.

Tests follow strict TDD methodology with real filesystem operations (no mocking).
Uses tmp_path fixtures for isolated test environments.
"""

import pytest
from pathlib import Path


class TestVectorStoreBackendInterface:
    """Test that VectorStoreBackend abstract interface is properly defined."""

    def test_vector_store_backend_interface_exists(self):
        """VectorStoreBackend ABC should exist with required abstract methods."""
        from code_indexer.backends.vector_store_backend import VectorStoreBackend

        # Verify it's an ABC
        from abc import ABC

        assert issubclass(VectorStoreBackend, ABC)

        # Verify required abstract methods exist
        required_methods = [
            "initialize",
            "start",
            "stop",
            "get_status",
            "cleanup",
            "get_vector_store_client",
            "health_check",
            "get_service_info",
        ]

        for method_name in required_methods:
            assert hasattr(
                VectorStoreBackend, method_name
            ), f"Missing method: {method_name}"


class TestFilesystemBackendInitialization:
    """Test FilesystemBackend initialization and directory structure creation."""

    def test_initialize_creates_directory_structure(self, tmp_path: Path):
        """FilesystemBackend.initialize() should create .code-indexer/index/ directory."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        index_dir = project_root / ".code-indexer" / "index"
        assert index_dir.exists(), "index directory should be created"
        assert index_dir.is_dir(), "index should be a directory"

    def test_start_returns_true_immediately(self, tmp_path: Path):
        """FilesystemBackend.start() should return True immediately (no-op)."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        result = backend.start()
        assert result is True, "start() should return True for filesystem backend"

    def test_stop_returns_true_immediately(self, tmp_path: Path):
        """FilesystemBackend.stop() should return True immediately (no-op)."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        result = backend.stop()
        assert result is True, "stop() should return True for filesystem backend"

    def test_health_check_validates_write_access(self, tmp_path: Path):
        """FilesystemBackend.health_check() should verify write access to index directory."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        health_status = backend.health_check()
        assert (
            health_status is True
        ), "health_check should return True when index directory is writable"

    def test_cleanup_removes_vectors_directory(self, tmp_path: Path):
        """FilesystemBackend.cleanup() should remove the index directory."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        index_dir = project_root / ".code-indexer" / "index"
        assert index_dir.exists(), "Precondition: index directory should exist"

        backend.cleanup()
        assert not index_dir.exists(), "cleanup() should remove index directory"

    def test_get_status_before_initialization(self, tmp_path: Path):
        """FilesystemBackend.get_status() should return not_initialized before init."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        status = backend.get_status()

        assert status["provider"] == "filesystem"
        assert status["status"] == "not_initialized"
        assert status["writable"] is False

    def test_get_status_after_initialization(self, tmp_path: Path):
        """FilesystemBackend.get_status() should return ready after init."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()
        status = backend.get_status()

        assert status["provider"] == "filesystem"
        assert status["status"] == "ready"
        assert status["writable"] is True

    def test_get_service_info(self, tmp_path: Path):
        """FilesystemBackend.get_service_info() should return provider details."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()
        service_info = backend.get_service_info()

        assert service_info["provider"] == "filesystem"
        assert service_info["requires_containers"] is False
        assert "vectors_dir" in service_info

    def test_get_vector_store_client_returns_filesystem_store(self, tmp_path: Path):
        """FilesystemBackend.get_vector_store_client() should return FilesystemVectorStore."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()
        client = backend.get_vector_store_client()

        assert (
            client is not None
        ), "get_vector_store_client should return FilesystemVectorStore"
        assert isinstance(
            client, FilesystemVectorStore
        ), "Should return FilesystemVectorStore instance"

    def test_health_check_fails_when_not_initialized(self, tmp_path: Path):
        """FilesystemBackend.health_check() should return False when not initialized."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        # Don't call initialize()
        health_status = backend.health_check()

        assert (
            health_status is False
        ), "health_check should return False when not initialized"

    def test_initialize_error_handling(self, tmp_path: Path):
        """FilesystemBackend.initialize() should raise RuntimeError on failure."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        # Create a file where the directory should be
        project_root = tmp_path / "test_project"
        project_root.mkdir()
        index_path = project_root / ".code-indexer" / "index"
        index_path.parent.mkdir(exist_ok=True)
        index_path.touch()  # Create as file instead of directory

        backend = FilesystemBackend(project_root=project_root)

        with pytest.raises(
            RuntimeError, match="Failed to initialize filesystem backend"
        ):
            backend.initialize()


class TestBackendFactory:
    """Test BackendFactory creates appropriate backend from configuration."""

    def test_programmatic_config_without_vector_store_defaults_to_qdrant(
        self, tmp_path: Path
    ):
        """BackendFactory should create QdrantContainerBackend when no vector_store config (backward compat)."""
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.backends.qdrant_container_backend import (
            QdrantContainerBackend,
        )
        from code_indexer.config import Config

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Create config without vector_store field (backward compatibility scenario)
        config = Config(codebase_dir=project_root)

        backend = BackendFactory.create(config=config, project_root=project_root)
        assert isinstance(
            backend, QdrantContainerBackend
        ), "Config without vector_store should default to Qdrant (backward compatibility)"

    def test_explicit_filesystem_same_as_default(self, tmp_path: Path):
        """BackendFactory should create FilesystemBackend when vector_store.provider='filesystem'."""
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.backends.filesystem_backend import FilesystemBackend
        from code_indexer.config import Config, VectorStoreConfig

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Create config with explicit filesystem provider
        config = Config(
            codebase_dir=project_root,
            vector_store=VectorStoreConfig(provider="filesystem"),
        )

        backend = BackendFactory.create(config=config, project_root=project_root)
        assert isinstance(
            backend, FilesystemBackend
        ), "Explicit filesystem should create FilesystemBackend"

    def test_qdrant_provider_creates_qdrant_backend(self, tmp_path: Path):
        """BackendFactory should create QdrantContainerBackend when vector_store.provider='qdrant'."""
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.backends.qdrant_container_backend import (
            QdrantContainerBackend,
        )
        from code_indexer.config import Config, VectorStoreConfig

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Create config with qdrant provider
        config = Config(
            codebase_dir=project_root, vector_store=VectorStoreConfig(provider="qdrant")
        )

        backend = BackendFactory.create(config=config, project_root=project_root)
        assert isinstance(
            backend, QdrantContainerBackend
        ), "Qdrant provider should create QdrantContainerBackend"

    def test_legacy_config_without_provider_defaults_to_qdrant(self, tmp_path: Path):
        """BackendFactory should create QdrantBackend for legacy configs without vector_store field."""
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.backends.qdrant_container_backend import (
            QdrantContainerBackend,
        )
        import json

        project_root = tmp_path / "test_project"
        project_root.mkdir()
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()

        # Create legacy config file without vector_store field
        legacy_config = {
            "codebase_dir": str(project_root),
            "embedding_provider": "ollama",
            # No vector_store field - simulating legacy config
        }

        config_path = config_dir / "config.json"
        with open(config_path, "w") as f:
            json.dump(legacy_config, f)

        # Load config from file
        from code_indexer.config import ConfigManager

        config_manager = ConfigManager(config_path)
        config = config_manager.load()

        # Factory should detect legacy config and default to Qdrant for backward compatibility
        backend = BackendFactory.create_from_legacy_config(
            config=config, project_root=project_root
        )
        assert isinstance(
            backend, QdrantContainerBackend
        ), "Legacy config should default to Qdrant for backward compatibility"

    def test_unsupported_provider_raises_error(self, tmp_path: Path):
        """BackendFactory should raise ValueError for unsupported providers."""
        from code_indexer.backends.backend_factory import BackendFactory
        from code_indexer.config import Config, VectorStoreConfig

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # Create config with invalid provider (hack the provider value for testing)
        config = Config(codebase_dir=project_root)
        # Manually set an invalid provider to test error handling
        config.vector_store = VectorStoreConfig(provider="filesystem")
        config.vector_store.provider = "invalid_provider"  # type: ignore

        with pytest.raises(ValueError, match="Unsupported vector store provider"):
            BackendFactory.create(config=config, project_root=project_root)

    def test_filesystem_config_has_no_ports(self, tmp_path: Path):
        """Filesystem backend configuration should not allocate ports."""
        from code_indexer.config import Config, VectorStoreConfig, ConfigManager

        project_root = tmp_path / "test_project"
        project_root.mkdir()
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()

        # Create filesystem config
        config = Config(
            codebase_dir=project_root,
            vector_store=VectorStoreConfig(provider="filesystem"),
        )

        # Save and reload to verify persistence
        config_path = config_dir / "config.json"
        manager = ConfigManager(config_path)
        manager.save(config)
        loaded_config = manager.load()

        # Verify no port allocations
        assert loaded_config.project_ports is None or all(
            port is None
            for port in [
                loaded_config.project_ports.qdrant_port,
                loaded_config.project_ports.ollama_port,
                loaded_config.project_ports.data_cleaner_port,
            ]
        ), "Filesystem config should not have port allocations"

    def test_qdrant_config_has_ports(self, tmp_path: Path):
        """Qdrant backend configuration should allocate ports."""
        from code_indexer.config import (
            Config,
            VectorStoreConfig,
            ConfigManager,
            ProjectPortsConfig,
        )
        from code_indexer.services.global_port_registry import GlobalPortRegistry

        project_root = tmp_path / "test_project"
        project_root.mkdir()
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()

        # Create qdrant config with port allocation
        registry = GlobalPortRegistry()
        qdrant_port = registry.find_available_port_for_service("qdrant")
        ollama_port = registry.find_available_port_for_service("ollama")
        data_cleaner_port = registry.find_available_port_for_service("data_cleaner")

        config = Config(
            codebase_dir=project_root,
            vector_store=VectorStoreConfig(provider="qdrant"),
            project_ports=ProjectPortsConfig(
                qdrant_port=qdrant_port,
                ollama_port=ollama_port,
                data_cleaner_port=data_cleaner_port,
            ),
        )

        # Save and reload
        config_path = config_dir / "config.json"
        manager = ConfigManager(config_path)
        manager.save(config)
        loaded_config = manager.load()

        # Verify port allocations exist
        assert loaded_config.project_ports is not None
        assert loaded_config.project_ports.qdrant_port is not None
        assert loaded_config.project_ports.ollama_port is not None
        assert loaded_config.project_ports.data_cleaner_port is not None


class TestCommandBehaviorMatrix:
    """Test that command behavior differs correctly between filesystem and Qdrant backends."""

    def test_filesystem_optimize_is_noop(self, tmp_path: Path):
        """FilesystemBackend.optimize() should return True immediately (no-op)."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        result = backend.optimize()
        assert (
            result is True
        ), "optimize() should return True (no-op) for filesystem backend"

    def test_filesystem_force_flush_is_noop(self, tmp_path: Path):
        """FilesystemBackend.force_flush() should return True immediately (no-op)."""
        from code_indexer.backends.filesystem_backend import FilesystemBackend

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        backend = FilesystemBackend(project_root=project_root)
        backend.initialize()

        result = backend.force_flush()
        assert (
            result is True
        ), "force_flush() should return True (no-op) for filesystem backend"
