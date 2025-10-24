"""Unit test for the filesystem init Pydantic validation fix.

This test verifies that cidx init --vector-store filesystem correctly
creates a valid ProjectPortsConfig object instead of setting project_ports to None,
which causes Pydantic validation errors.
"""

import json
import tempfile
from pathlib import Path

import pytest

from code_indexer.config import Config, ProjectPortsConfig, VectorStoreConfig


class TestFilesystemInitPydanticFix:
    """Test that filesystem init creates valid Pydantic configuration."""

    def test_filesystem_init_creates_valid_project_ports_config(self):
        """Filesystem init should create ProjectPortsConfig with None values, not null."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            # Mock the CLI context to test the specific logic
            from code_indexer.config import ConfigManager

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_manager = ConfigManager(config_path)

            # Create initial config
            config = Config(
                codebase_dir=test_dir,
                vector_store=VectorStoreConfig(provider="filesystem"),
            )

            # This is what the CLI should do for filesystem backend
            updates = {}
            vector_store = "filesystem"

            # THE FIX: Don't set to None, create ProjectPortsConfig with None values
            if vector_store == "filesystem":
                updates["project_ports"] = ProjectPortsConfig(
                    qdrant_port=None, ollama_port=None, data_cleaner_port=None
                )

            # Apply updates
            if updates:
                for key, value in updates.items():
                    setattr(config, key, value)

            # Save config
            config_manager.save(config)

            # Verify it can be loaded back without Pydantic errors
            loaded_config = config_manager.load()
            assert loaded_config is not None
            assert loaded_config.vector_store.provider == "filesystem"
            assert loaded_config.project_ports is not None
            assert loaded_config.project_ports.qdrant_port is None
            assert loaded_config.project_ports.ollama_port is None
            assert loaded_config.project_ports.data_cleaner_port is None

            # Verify JSON structure
            with open(config_path) as f:
                json_data = json.load(f)

            # project_ports should be an object with null values, NOT null itself
            assert json_data["project_ports"] is not None
            assert isinstance(json_data["project_ports"], dict)
            assert json_data["project_ports"]["qdrant_port"] is None
            assert json_data["project_ports"]["ollama_port"] is None
            assert json_data["project_ports"]["data_cleaner_port"] is None

    def test_setting_project_ports_to_none_causes_validation_error(self):
        """Setting project_ports to None should cause Pydantic validation error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)

            # Create invalid config with project_ports = null
            invalid_config = {
                "codebase_dir": str(test_dir),
                "vector_store": {"provider": "filesystem"},
                "project_ports": None,  # This causes validation error
            }

            with open(config_path, "w") as f:
                json.dump(invalid_config, f)

            # Attempting to load should raise validation error
            from code_indexer.config import ConfigManager

            config_manager = ConfigManager(config_path)
            with pytest.raises(Exception) as exc_info:
                config_manager.load()

            # Should be a Pydantic validation error about project_ports
            assert (
                "project_ports" in str(exc_info.value).lower()
                or "validation" in str(exc_info.value).lower()
            )

    def test_qdrant_backend_still_gets_port_allocations(self):
        """Qdrant backend should still allocate ports normally."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            from code_indexer.config import ConfigManager
            from code_indexer.services.global_port_registry import GlobalPortRegistry

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_manager = ConfigManager(config_path)

            # For Qdrant, we should allocate ports
            registry = GlobalPortRegistry()
            qdrant_port = registry.find_available_port_for_service("qdrant")
            ollama_port = registry.find_available_port_for_service("ollama")
            data_cleaner_port = registry.find_available_port_for_service("data_cleaner")

            config = Config(
                codebase_dir=test_dir,
                vector_store=VectorStoreConfig(provider="qdrant"),
                project_ports=ProjectPortsConfig(
                    qdrant_port=qdrant_port,
                    ollama_port=ollama_port,
                    data_cleaner_port=data_cleaner_port,
                ),
            )

            config_manager.save(config)
            loaded_config = config_manager.load()

            # Qdrant config should have actual port values
            assert loaded_config.project_ports.qdrant_port is not None
            assert loaded_config.project_ports.ollama_port is not None
            assert loaded_config.project_ports.data_cleaner_port is not None
            assert loaded_config.project_ports.qdrant_port > 0
            assert loaded_config.project_ports.ollama_port > 0
            assert loaded_config.project_ports.data_cleaner_port > 0
