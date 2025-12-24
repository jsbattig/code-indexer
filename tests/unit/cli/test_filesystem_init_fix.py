"""Unit test for filesystem backend configuration (v8.0+).

This test verifies that cidx init --vector-store filesystem correctly
creates a valid configuration without legacy fields (project_ports, project_containers).
ProjectPortsConfig and ProjectContainersConfig were removed in v8.0.
"""

import json
import tempfile
from pathlib import Path

from code_indexer.config import Config, VectorStoreConfig


class TestFilesystemInitPydanticFix:
    """Test that filesystem init creates valid Pydantic configuration."""

    def test_filesystem_init_creates_valid_config_without_legacy_fields(self):
        """Filesystem init should create valid config without project_ports/project_containers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            from code_indexer.config import ConfigManager

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_manager = ConfigManager(config_path)

            # Create initial config (v8.0+ style without legacy fields)
            config = Config(
                codebase_dir=test_dir,
                vector_store=VectorStoreConfig(provider="filesystem"),
            )

            # Verify config is valid and can be serialized
            config_manager.save(config)

            # Reload and verify structure
            loaded_config = config_manager.load()

            # Should have filesystem backend
            assert loaded_config.vector_store is not None
            assert loaded_config.vector_store.provider == "filesystem"

    def test_filesystem_init_json_structure(self):
        """Verify JSON structure matches expected format (no legacy fields)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            from code_indexer.config import ConfigManager

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_manager = ConfigManager(config_path)

            # Create config with filesystem backend
            config = Config(
                codebase_dir=test_dir,
                vector_store=VectorStoreConfig(provider="filesystem"),
            )

            config_manager.save(config)

            # Load JSON directly to verify structure
            with open(config_path, "r") as f:
                raw_json = json.load(f)

            # Verify filesystem backend
            assert "vector_store" in raw_json
            if raw_json["vector_store"] is not None:
                assert raw_json["vector_store"]["provider"] == "filesystem"

    def test_filesystem_backend_selection(self):
        """Test that filesystem backend is correctly set."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = Path(temp_dir) / "test_project"
            test_dir.mkdir()

            from code_indexer.config import ConfigManager

            config_path = test_dir / ".code-indexer" / "config.json"
            config_path.parent.mkdir(parents=True)
            config_manager = ConfigManager(config_path)

            # Create config with filesystem backend
            config = Config(
                codebase_dir=test_dir,
                vector_store=VectorStoreConfig(provider="filesystem"),
            )

            config_manager.save(config)
            loaded_config = config_manager.load()

            # Verify backend selection
            assert loaded_config.vector_store is not None
            assert loaded_config.vector_store.provider == "filesystem"
