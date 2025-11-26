"""Tests for legacy configuration detection and rejection.

This module tests that deprecated configuration options (Filesystem, Voyage, containers)
are properly detected and rejected with clear migration messages.
"""

import pytest
from pathlib import Path
import json
from code_indexer.config import ConfigManager


class TestLegacyConfigDetection:
    """Test detection and rejection of legacy configuration options."""

    def test_reject_filesystem_config_in_json(self, tmp_path: Path):
        """Test that filesystem_config in JSON is rejected with clear error message."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy filesystem_config
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "filesystem_config": {
                "host": "localhost",
                "port": 6333,
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Attempt to load should fail with specific message
        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        assert "Filesystem" in error_message or "filesystem" in error_message.lower()
        assert (
            "removed" in error_message.lower()
            or "not supported" in error_message.lower()
        )
        assert "v8.0" in error_message or "8.0" in error_message
        assert "migration" in error_message.lower()

    def test_reject_voyage_config_in_json(self, tmp_path: Path):
        """Test that voyage_config in JSON is rejected with clear error message."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy voyage_config
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "voyage_config": {
                "model": "codellama",
                "base_url": "http://localhost:11434",
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Attempt to load should fail with specific message
        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        assert "Voyage" in error_message or "voyage" in error_message.lower()
        assert (
            "removed" in error_message.lower()
            or "not supported" in error_message.lower()
        )
        assert "v8.0" in error_message or "8.0" in error_message
        assert "VoyageAI" in error_message or "voyage" in error_message.lower()

    def test_reject_container_config_in_json(self, tmp_path: Path):
        """Test that project_containers config in JSON is rejected with clear error message."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy project_containers
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "project_containers": {
                "project_hash": "abc123",
                "data_cleaner_name": "cidx-cleaner-abc123",
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Attempt to load should fail with specific message
        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        assert "container" in error_message.lower()
        assert (
            "removed" in error_message.lower()
            or "not supported" in error_message.lower()
        )
        assert "v8.0" in error_message or "8.0" in error_message
        assert (
            "daemon" in error_message.lower() or "filesystem" in error_message.lower()
        )

    def test_reject_project_ports_config_in_json(self, tmp_path: Path):
        """Test that project_ports config in JSON is rejected with clear error message."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy project_ports
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "project_ports": {
                "data_cleaner_port": 6334,
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Attempt to load should fail with specific message
        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        assert "port" in error_message.lower()
        assert (
            "removed" in error_message.lower()
            or "not supported" in error_message.lower()
        )
        assert "v8.0" in error_message or "8.0" in error_message


    def test_reject_invalid_embedding_provider(self, tmp_path: Path):
        """Test that non-voyageai embedding providers are rejected."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with invalid provider
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage",
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Attempt to load should fail
        manager = ConfigManager(config_path)
        with pytest.raises((ValueError, TypeError)) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        assert "voyage" in error_message.lower() or "voyage" in error_message.lower()

    def test_accept_valid_filesystem_config(self, tmp_path: Path):
        """Test that valid filesystem + voyageai config is accepted."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create valid config
        config_data = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "vector_store": {
                "provider": "filesystem",
            },
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Should load successfully
        manager = ConfigManager(config_path)
        config = manager.load()

        assert config.embedding_provider == "voyage-ai"
        assert config.vector_store is not None
        assert config.vector_store.provider == "filesystem"

    def test_accept_minimal_valid_config(self, tmp_path: Path):
        """Test that minimal valid config (defaults) is accepted."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create minimal config (relies on defaults)
        config_data = {
            "codebase_dir": str(tmp_path),
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        # Should load successfully with defaults
        manager = ConfigManager(config_path)
        config = manager.load()

        assert config.embedding_provider == "voyage-ai"
        # vector_store can be None (defaults to filesystem)

    def test_migration_message_includes_guide_reference(self, tmp_path: Path):
        """Test that migration messages reference the migration guide."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with legacy filesystem_config
        config_data = {
            "codebase_dir": str(tmp_path),
            "filesystem_config": {"host": "localhost"},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        error_message = str(exc_info.value)
        # Should reference some form of migration documentation
        assert (
            "migration" in error_message.lower()
            or "docs/" in error_message.lower()
            or "see:" in error_message.lower()
        )

    def test_multiple_legacy_configs_all_reported(self, tmp_path: Path):
        """Test that multiple legacy configs are reported (not just first)."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True)

        # Create config with multiple legacy configs
        config_data = {
            "codebase_dir": str(tmp_path),
            "filesystem_config": {"host": "localhost"},
            "voyage_config": {"model": "codellama"},
            "project_containers": {"project_hash": "abc"},
        }

        with open(config_path, "w") as f:
            json.dump(config_data, f)

        manager = ConfigManager(config_path)
        with pytest.raises(ValueError) as exc_info:
            manager.load()

        # At minimum, should detect at least one of them
        error_message = str(exc_info.value)
        legacy_keywords = ["filesystem", "voyage", "container"]
        assert any(keyword in error_message.lower() for keyword in legacy_keywords)
